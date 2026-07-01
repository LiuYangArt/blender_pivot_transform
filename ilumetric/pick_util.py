from __future__ import annotations

"""pick_util – Fast element picking under cursor for Blender 3D viewport.

Uses BVH ray-cast + local neighborhood search for O(log N) performance
instead of iterating all vertices/edges (O(V+E)).

For multi-object scenes, scene.ray_cast() narrows to one candidate object.
"""

import bmesh
import bpy
from dataclasses import dataclass, field
from typing import Sequence

from bpy_extras import view3d_utils
from mathutils import Vector
from mathutils.bvhtree import BVHTree


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

# Registry of live caches so a depsgraph handler can invalidate them when the
# scene geometry changes (GizmoGroup.refresh fires on selection-type changes,
# NOT on geometry edits, modifier re-eval, or frame changes – those must be
# caught here, otherwise picking would use a stale BMesh copy).
import weakref

_LIVE_CACHES: "weakref.WeakSet" = weakref.WeakSet()


def invalidate_object(obj_ptr):
    """Drop cached data for a single object (by ``as_pointer()``) everywhere."""
    for cache in list(_LIVE_CACHES):
        cache.invalidate(obj_ptr)


def invalidate_all_caches():
    """Drop all cached BMesh/BVH data in every live cache."""
    for cache in list(_LIVE_CACHES):
        cache.clear()


class PickDataCache:
    """BMesh + BVH cache with validity checks.

    Stores one (BMesh, BVHTree) pair per object pointer.  Automatically
    rebuilds entries whose BMesh has been freed or invalidated.
    """

    __slots__ = ('_map', '__weakref__')

    def __init__(self):
        self._map: dict = {}
        _LIVE_CACHES.add(self)

    def clear(self):
        """Drop all cached data.  Does NOT free BMeshes – they stay alive
        as long as any PickResult._bm_ref keeps a reference."""
        self._map.clear()

    def invalidate(self, obj_ptr):
        """Drop cached entries for a single object pointer (both modifier
        variants)."""
        for key in [k for k in self._map if k[0] == obj_ptr]:
            del self._map[key]

    def get(self, obj: bpy.types.Object, use_modifiers: bool = False,
            depsgraph=None):
        """Return *(bmesh, bvhtree)* for *obj*.  Rebuilds if stale.

        Returns ``(None, None)`` for non-mesh objects without *use_modifiers*.
        """
        key = (obj.as_pointer(), use_modifiers)

        # Edit-mode – live BMesh, always rebuild BVH
        if _in_edit_mode(obj):
            if obj.type != 'MESH':
                return None, None
            bm = bmesh.from_edit_mesh(obj.data)
            bm.normal_update()  # vert/face normals may be stale mid-edit
            _ensure_tables(bm)
            return bm, BVHTree.FromBMesh(bm)

        # Cached entry still valid?
        rec = self._map.get(key)
        if rec is not None:
            bm, bvh = rec
            if bm is not None and bm.is_valid:
                if bvh is not None:
                    return bm, bvh
                bvh = BVHTree.FromBMesh(bm)
                self._map[key] = (bm, bvh)
                return bm, bvh

        # Build fresh
        if use_modifiers and depsgraph is not None:
            try:
                bm = _bmesh_from_evaluated(obj, depsgraph)
            except (RuntimeError, TypeError):
                return None, None
            if len(bm.faces) == 0 and len(bm.verts) == 0:
                return None, None
        elif obj.type == 'MESH':
            bm = _bmesh_from_object(obj)
        else:
            return None, None

        bvh = BVHTree.FromBMesh(bm)
        self._map[key] = (bm, bvh)
        return bm, bvh


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _in_edit_mode(obj: bpy.types.Object) -> bool:
    return obj.mode == 'EDIT' or getattr(obj.data, 'is_editmode', False)


def _ensure_tables(bm: bmesh.types.BMesh):
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()


def _bmesh_from_object(obj: bpy.types.Object) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()  # ensure face/vert normals are current
    _ensure_tables(bm)
    return bm


def _bmesh_from_evaluated(obj: bpy.types.Object, depsgraph) -> bmesh.types.BMesh:
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    try:
        bm = bmesh.new()
        bm.from_mesh(eval_mesh)
        bm.normal_update()  # ensure face/vert normals are current
        _ensure_tables(bm)
        return bm
    finally:
        eval_obj.to_mesh_clear()


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class PickResult:
    """Result of picking a mesh or curve element."""
    type: str = 'NONE'                                 # 'VERT' | 'EDGE' | 'FACE' | 'NONE'
    element: object = None                             # BMVert / BMEdge / BMFace or None
    hitpos: Vector = None                              # world-space position
    obj: bpy.types.Object = None
    _bm_ref: object = field(default=None, repr=False)  # prevent BMesh GC
    _frame: tuple = field(default=None, repr=False)    # pre-computed (origin, tan, bitan, normal)
    _draw_coords: list = field(default=None, repr=False)  # world-space coords for drawing

    @property
    def is_empty(self) -> bool:
        return self.type == 'NONE' or (self.element is None and self._frame is None)

    @property
    def isNotEmpty(self) -> bool:  # legacy alias
        return not self.is_empty

    def __bool__(self):
        return not self.is_empty


def _empty(obj=None):
    return PickResult(obj=obj)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _ray_from_region(context, coord):
    region = context.region
    rv3d = context.region_data
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    return origin, direction.normalized()


def _world_to_screen(context, co):
    """Project world-space point to viewport pixel coords."""
    return _make_projector(context)(co)


def _make_projector(context):
    """Build a fast world->screen projector with the perspective matrix and
    half-extents captured once (avoids repeated RNA access in hot loops)."""
    rv3d = context.region_data
    region = context.region
    persp = rv3d.perspective_matrix
    hw = region.width * 0.5
    hh = region.height * 0.5

    def project(co):
        v4 = persp @ Vector((co[0], co[1], co[2], 1.0))
        w = v4.w
        if w <= 0.0:
            return None
        return Vector((hw + hw * v4.x / w, hh + hh * v4.y / w))

    return project


def _dist_point_seg_2d(p, a, b):
    """Minimum distance from point *p* to segment *ab* in 2D."""
    ab = b - a
    ls = ab.length_squared
    if ls < 1e-12:
        return (p - a).length
    t = max(0.0, min(1.0, (p - a).dot(ab) / ls))
    return (p - (a + t * ab)).length


def _closest_on_segment(seg_a, seg_b, ray_o, ray_d):
    """Closest point on segment to an infinite ray (clamped to segment)."""
    u = seg_b - seg_a
    a = u.dot(u)
    if a <= 1e-12:
        return seg_a.copy()
    b = u.dot(ray_d)
    c = ray_d.dot(ray_d)
    d = u.dot(seg_a - ray_o)
    e = ray_d.dot(seg_a - ray_o)
    denom = a * c - b * b
    if abs(denom) <= 1e-12:
        s = 0.0
    else:
        s = (b * e - c * d) / denom
    return seg_a + u * max(0.0, min(1.0, s))


# ---------------------------------------------------------------------------
# Occlusion test
# ---------------------------------------------------------------------------

def _is_occluded(bvh, origin_l, point_l, tolerance=1e-3):
    """Return True if *point_l* (local space) is hidden behind closer geometry."""
    direction = point_l - origin_l
    dist_to_point = direction.length
    if dist_to_point < tolerance:
        return False
    direction = direction / dist_to_point  # normalize
    _loc, _nrm, _idx, hit_dist = bvh.ray_cast(origin_l, direction)
    if _loc is None:
        return False
    return hit_dist < dist_to_point - tolerance


# ---------------------------------------------------------------------------
# Core: BVH ray-cast → local neighborhood search
# ---------------------------------------------------------------------------

def _pick_on_object(context, obj, coord, radius_px, elements_set,
                    backface_culling, face_center, cache, use_modifiers,
                    depsgraph, occlusion=True):
    """Pick nearest element on a single object.

    1. BVH ray-cast to find the face under cursor  → O(log F)
    2. Gather 1-ring neighbourhood of that face
    3. Project only those local elements to screen → O(k)
    """
    try:
        if cache is not None:
            bm, bvh = cache.get(obj, use_modifiers, depsgraph)
            if bm is None:
                return _empty(obj)
        else:
            if obj.type != 'MESH':
                return _empty(obj)
            bm = _bmesh_from_object(obj)
            bvh = BVHTree.FromBMesh(bm)
    except (ReferenceError, RuntimeError, ValueError):
        return _empty(obj)

    # --- BVH ray-cast in local space ----------------------------------
    origin_w, dir_w = _ray_from_region(context, coord)
    try:
        mat_inv = obj.matrix_world.inverted()
    except ValueError:
        return _empty(obj)

    origin_l = mat_inv @ origin_w
    dir_l = (mat_inv.to_3x3() @ dir_w).normalized()

    loc, _normal, index, _dist = bvh.ray_cast(origin_l, dir_l)
    if index is None:
        return _empty(obj)

    try:
        face = bm.faces[index]
    except (IndexError, ReferenceError):
        return _empty(obj)

    if face.hide:
        return _empty(obj)
    if backface_culling and face.normal.dot(dir_l) >= 0.0:
        return _empty(obj)

    mat = obj.matrix_world
    hit_world = mat @ loc
    screen = Vector(coord)
    bm_ref = bm if not _in_edit_mode(obj) else None
    project = _make_projector(context)

    # Occlusion: check visibility
    do_occlusion = occlusion

    # --- Vertex: 1-ring around hit face --------------------------------
    if 'VERT' in elements_set:
        best_d, best_v = radius_px, None
        seen = set()
        for v in face.verts:
            seen.add(v.index)
            for lf in v.link_faces:
                for v2 in lf.verts:
                    seen.add(v2.index)
        for vi in seen:
            try:
                v = bm.verts[vi]
            except (IndexError, ReferenceError):
                continue
            if v.hide:
                continue
            if do_occlusion and _is_occluded(bvh, origin_l, v.co):
                continue
            sp = project(mat @ v.co)
            if sp is None:
                continue
            d = (screen - sp).length
            if d < best_d:
                best_d, best_v = d, v
        if best_v is not None:
            return PickResult('VERT', best_v, mat @ best_v.co, obj, bm_ref)

    # --- Edge: only edges belonging to the hit face ---------------------
    if 'EDGE' in elements_set:
        best_d, best_e, best_hit = radius_px, None, None
        # Only consider edges of the hit face and its immediate neighbours
        hit_face_set = {face.index}
        for v in face.verts:
            for lf in v.link_faces:
                hit_face_set.add(lf.index)
        local_edges = set()
        for v in face.verts:
            for e in v.link_edges:
                local_edges.add(e)
        for e in local_edges:
            if e.hide:
                continue
            # Skip edges that don't belong to any visible (front-facing) face
            if do_occlusion:
                edge_face_indices = {f.index for f in e.link_faces}
                if not edge_face_indices.intersection(hit_face_set):
                    continue
                # Check midpoint occlusion
                mid_l = (e.verts[0].co + e.verts[1].co) * 0.5
                if _is_occluded(bvh, origin_l, mid_l):
                    continue
            w1 = mat @ e.verts[0].co
            w2 = mat @ e.verts[1].co
            sp1 = project(w1)
            sp2 = project(w2)
            if sp1 is None or sp2 is None:
                continue
            d = _dist_point_seg_2d(screen, sp1, sp2)
            if d < best_d:
                best_d, best_e = d, e
                best_hit = _closest_on_segment(w1, w2, origin_w, dir_w)
        if best_e is not None:
            return PickResult('EDGE', best_e, best_hit, obj, bm_ref)

    # --- Face -----------------------------------------------------------
    if 'FACE' in elements_set:
        if face_center:
            hit_world = mat @ face.calc_center_median()
        return PickResult('FACE', face, hit_world, obj, bm_ref)

    return _empty(obj)


# ---------------------------------------------------------------------------
# Curve picking
# ---------------------------------------------------------------------------

def _frame_from_tangent(origin, tangent):
    """Build *(origin, tangent, bitangent, normal)* from a tangent vector."""
    up = Vector((0, 0, 1))
    if abs(up.dot(tangent)) > 0.9:
        up = Vector((0, 1, 0))
    normal = _safe_normalized(tangent.cross(up), Vector((0, 0, 1)))
    bitangent = _safe_normalized(normal.cross(tangent), Vector((0, 1, 0)))
    tangent = _safe_normalized(bitangent.cross(normal), Vector((1, 0, 0)))
    return (origin, tangent, bitangent, normal)


def _sample_spline(spline, resolution):
    """Return list of Vector positions sampled along *spline*."""
    samples = []
    if spline.type == 'BEZIER':
        bps = spline.bezier_points
        if len(bps) == 0:
            return samples
        if len(bps) == 1:
            return [bps[0].co.copy()]
        n_seg = max(resolution, 2)
        for i in range(len(bps) - 1):
            p0, hr = bps[i].co, bps[i].handle_right
            hl, p1 = bps[i + 1].handle_left, bps[i + 1].co
            for j in range(n_seg):
                t = j / n_seg
                u = 1.0 - t
                samples.append(u*u*u*p0 + 3*u*u*t*hr + 3*u*t*t*hl + t*t*t*p1)
        samples.append(bps[-1].co.copy())
        if spline.use_cyclic_u and len(bps) >= 2:
            p0, hr = bps[-1].co, bps[-1].handle_right
            hl, p1 = bps[0].handle_left, bps[0].co
            for j in range(1, n_seg):
                t = j / n_seg
                u = 1.0 - t
                samples.append(u*u*u*p0 + 3*u*u*t*hr + 3*u*t*t*hl + t*t*t*p1)
            samples.append(bps[0].co.copy())
    else:  # NURBS / POLY
        for pt in spline.points:
            samples.append(Vector(pt.co[:3]))
        if spline.use_cyclic_u and len(samples) > 1:
            samples.append(samples[0].copy())
    return samples


def _pick_on_curve(context, obj, coord, radius_px, elements_set,
                   use_modifiers, depsgraph, occlusion, cache=None):
    """Pick nearest element on a curve object.

    Priority: control points (VERT) > spline body (EDGE) > evaluated mesh (FACE).
    """
    mat = obj.matrix_world
    mat3 = mat.to_3x3()
    screen = Vector(coord)
    best = _empty(obj)
    best_d = radius_px

    curve_data = obj.data
    if curve_data is None:
        return _empty(obj)

    # --- Control points (VERT) ----------------------------------------
    if 'VERT' in elements_set:
        for spline in curve_data.splines:
            if spline.type == 'BEZIER':
                for bp in spline.bezier_points:
                    world_pos = mat @ bp.co
                    sp = _world_to_screen(context, world_pos)
                    if sp is None:
                        continue
                    d = (screen - sp).length
                    if d >= best_d:
                        continue
                    tan_l = bp.handle_right - bp.handle_left
                    tangent = _safe_normalized(mat3 @ tan_l, Vector((1, 0, 0)))
                    best_d = d
                    best = PickResult(
                        'VERT', None, world_pos, obj,
                        _frame=_frame_from_tangent(world_pos, tangent))
            else:  # NURBS / POLY
                pts = spline.points
                n = len(pts)
                for i, pt in enumerate(pts):
                    co = Vector(pt.co[:3])
                    world_pos = mat @ co
                    sp = _world_to_screen(context, world_pos)
                    if sp is None:
                        continue
                    d = (screen - sp).length
                    if d >= best_d:
                        continue
                    if n > 1:
                        nxt = i + 1 if i < n - 1 else i - 1
                        tan_l = Vector(pts[nxt].co[:3]) - co
                        if nxt < i:
                            tan_l = -tan_l
                    else:
                        tan_l = Vector((1, 0, 0))
                    tangent = _safe_normalized(mat3 @ tan_l, Vector((1, 0, 0)))
                    best_d = d
                    best = PickResult(
                        'VERT', None, world_pos, obj,
                        _frame=_frame_from_tangent(world_pos, tangent))
        if not best.is_empty:
            return best

    # --- Spline segments (EDGE) ----------------------------------------
    if 'EDGE' in elements_set:
        resolution = max(getattr(curve_data, 'resolution_u', 12), 2)
        for spline in curve_data.splines:
            samples = _sample_spline(spline, resolution)
            for si in range(len(samples) - 1):
                w0 = mat @ samples[si]
                w1 = mat @ samples[si + 1]
                sp0 = _world_to_screen(context, w0)
                sp1 = _world_to_screen(context, w1)
                if sp0 is None or sp1 is None:
                    continue
                d = _dist_point_seg_2d(screen, sp0, sp1)
                if d >= best_d:
                    continue
                ab = sp1 - sp0
                ls = ab.length_squared
                t = max(0.0, min(1.0, (screen - sp0).dot(ab) / ls)) if ls > 1e-12 else 0.5
                hit_w = w0.lerp(w1, t)
                tangent = _safe_normalized(w1 - w0, Vector((1, 0, 0)))
                best_d = d
                best = PickResult(
                    'EDGE', None, hit_w, obj,
                    _frame=_frame_from_tangent(hit_w, tangent),
                    _draw_coords=[w0, w1])
        if not best.is_empty:
            return best

    # --- Evaluated mesh (beveled / extruded / modifiers) ---------------
    if use_modifiers and depsgraph is not None:
        mesh_res = _pick_on_object(
            context, obj, coord, radius_px, elements_set,
            True, False, cache, True, depsgraph, occlusion)
        if not mesh_res.is_empty:
            return mesh_res

    return _empty(obj)


# ---------------------------------------------------------------------------
# Generic object picking (unsupported types fallback)
# ---------------------------------------------------------------------------

def _frame_from_matrix(obj):
    """Extract *(origin, tangent, bitangent, normal)* from object matrix."""
    mat = obj.matrix_world
    origin = mat.translation.copy()
    tangent = _safe_normalized(Vector(mat.col[0][:3]), Vector((1, 0, 0)))
    bitangent = _safe_normalized(Vector(mat.col[1][:3]), Vector((0, 1, 0)))
    normal = _safe_normalized(Vector(mat.col[2][:3]), Vector((0, 0, 1)))
    return (origin, tangent, bitangent, normal)


def _pick_as_object(context, obj, coord, radius_px):
    """Pick an unsupported object by its origin in screen space."""
    origin_w = obj.matrix_world.translation
    sp = _world_to_screen(context, origin_w)
    if sp is None:
        return _empty(obj)
    screen = Vector(coord)
    d = (screen - sp).length
    if d >= radius_px:
        return _empty(obj)
    return PickResult(
        'VERT', None, origin_w.copy(), obj,
        _frame=_frame_from_matrix(obj))


# ---------------------------------------------------------------------------
# Target helpers
# ---------------------------------------------------------------------------

def _resolve_targets(context, obj_or_objs):
    if obj_or_objs is None:
        return [o for o in context.selected_objects
                if isinstance(o, bpy.types.Object)]
    if isinstance(obj_or_objs, bpy.types.Object):
        return [obj_or_objs]
    return [o for o in obj_or_objs if isinstance(o, bpy.types.Object)]


def _prefilter_with_scene_raycast(context, objs, coord, depsgraph):
    """Narrow mesh targets to the ray_cast hit; keep all non-mesh objects.

    scene.ray_cast sees mesh geometry only.  Whatever mesh it hits is the one
    relevant mesh candidate – every other mesh is occluded or missed and can be
    skipped.  Non-mesh objects (curves, empties, lights) are invisible to
    ray_cast, so they are always kept for screen-space picking.
    """
    non_mesh = [o for o in objs if o.type != 'MESH']
    origin, direction = _ray_from_region(context, coord)
    try:
        if depsgraph is None:
            depsgraph = context.evaluated_depsgraph_get()
        hit, _loc, _nrm, _idx, hit_obj, _mat = context.scene.ray_cast(
            depsgraph, origin, direction)
    except Exception:
        return objs  # ray_cast unavailable – fall back to the full list

    if hit and hit_obj is not None:
        orig = hit_obj.original
        ptrs = {o.as_pointer() for o in objs}
        if orig.as_pointer() in ptrs:
            return [orig] + [o for o in non_mesh
                             if o.as_pointer() != orig.as_pointer()]
        # Hit a mesh outside our candidate set – no mesh of ours is in front.
        return non_mesh

    # Ray missed all mesh geometry – only non-mesh objects can still be picked.
    return non_mesh


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pick_element(
    context,
    obj_or_objs,
    coord,
    radius_px: float = 15.0,
    elements: Sequence[str] = ('VERT', 'EDGE', 'FACE'),
    backface_culling: bool = True,
    *,
    face_center: bool = False,
    edge_midpoint: bool = False,
    cache: PickDataCache | None = None,
    use_modifiers: bool = False,
    occlusion: bool = True,
) -> PickResult:
    """Pick the nearest mesh/curve/armature element under cursor.

    Performance: O(log F + k) per object via BVH ray-cast + local search,
    where *k* is the 1-ring neighbourhood size (~10-30 elements).
    For multiple objects, *scene.ray_cast()* narrows to one candidate.

    Armature objects (Object/Pose mode) are picked bone-by-bone via pose
    bones – head/tail behave like VERT picks, the bone body like an EDGE pick.
    """
    coord_t = (float(coord[0]), float(coord[1]))
    objs = _resolve_targets(context, obj_or_objs)
    if not objs:
        return _empty()

    depsgraph = None
    if use_modifiers:
        try:
            depsgraph = context.evaluated_depsgraph_get()
        except Exception:
            pass

    # Pre-filter for multi-object lists
    if len(objs) > 1:
        objs = _prefilter_with_scene_raycast(
            context, objs, coord_t, depsgraph)

    elements_set = frozenset(e.upper() for e in elements)
    perspective = context.region_data.perspective_matrix
    best = None
    best_depth = None

    for obj in objs:
        try:
            if obj.type in {'CURVE', 'SURFACE'}:
                # SURFACE splines are NURBS – their control points live in
                # ``spline.points`` exactly like POLY/NURBS curves, so the same
                # picker handles both (the BEZIER branch is simply never taken).
                res = _pick_on_curve(
                    context, obj, coord_t, radius_px, elements_set,
                    use_modifiers, depsgraph, occlusion, cache)
            elif obj.type == 'MESH':
                res = _pick_on_object(
                    context, obj, coord_t, radius_px, elements_set,
                    backface_culling, face_center, cache, use_modifiers,
                    depsgraph, occlusion=occlusion,
                )
            elif obj.type == 'ARMATURE':
                res = _pick_on_armature(
                    context, obj, coord_t, radius_px, elements_set,
                    edge_midpoint=edge_midpoint)
            else:
                res = _pick_as_object(
                    context, obj, coord_t, radius_px)
        except Exception:
            continue
        if res.is_empty:
            continue
        v4 = perspective @ Vector((*res.hitpos, 1.0))
        depth = v4.z / max(v4.w, 1e-6)
        if best is None or depth < best_depth:
            best, best_depth = res, depth

    return best or _empty()


# ---------------------------------------------------------------------------
# Armature bone picking (Edit Armature)
# ---------------------------------------------------------------------------

def _edit_armatures(context):
    """Armatures currently in Edit mode (multi-armature edit is supported)."""
    return [o for o in context.objects_in_mode_unique_data
            if o.type == 'ARMATURE']


def _pick_bones(context, bone_data, coord, radius_px, elements_set,
                edge_midpoint):
    """Screen-space pick over a list of world-space bone segments.

    *bone_data* is an iterable of ``(head_w, tail_w, ax, ay, az)`` tuples –
    world-space head/tail points plus the bone's roll-aware world X/Y/Z axes
    (Y = head->tail). A head/tail within *radius_px* behaves like a VERT pick
    and always wins over the bone body (EDGE), which snaps to the closest point
    on the segment, or its midpoint when *edge_midpoint* is set.

    Returns ``(ptype, origin_w, frame, draw_coords)`` for the nearest element,
    or ``None`` when nothing is within range.
    """
    coord_s = Vector((float(coord[0]), float(coord[1])))
    project = _make_projector(context)
    ray_o, ray_d = _ray_from_region(context, coord)

    want_vert = 'VERT' in elements_set
    want_edge = 'EDGE' in elements_set

    best_vert = None  # (dist, origin_w, frame, draw_coords)
    best_edge = None

    for head_w, tail_w, ax, ay, az in bone_data:
        # --- head / tail (VERT-like) --------------------------------------
        if want_vert:
            for point_w in (head_w, tail_w):
                sp = project(point_w)
                if sp is None:
                    continue
                d = (coord_s - sp).length
                if d < radius_px and (best_vert is None or d < best_vert[0]):
                    best_vert = (d, point_w.copy(),
                                 (point_w.copy(), ax, ay, az),
                                 [point_w.copy()])

        # --- bone body (EDGE-like) ----------------------------------------
        if want_edge:
            sp_h = project(head_w)
            sp_t = project(tail_w)
            if sp_h is None or sp_t is None:
                continue
            d = _dist_point_seg_2d(coord_s, sp_h, sp_t)
            if d < radius_px and (best_edge is None or d < best_edge[0]):
                if edge_midpoint:
                    hit_w = (head_w + tail_w) * 0.5
                else:
                    hit_w = _closest_on_segment(head_w, tail_w, ray_o, ray_d)
                best_edge = (d, hit_w.copy(),
                             (hit_w.copy(), ax, ay, az),
                             [head_w.copy(), tail_w.copy()])

    # VERT always beats EDGE (matches the mesh picker priority).
    chosen = best_vert if best_vert is not None else best_edge
    if chosen is None:
        return None
    ptype = 'VERT' if best_vert is not None else 'EDGE'
    _d, origin_w, frame, draw_coords = chosen
    return ptype, origin_w, frame, draw_coords


def _bone_axes(world_matrix):
    """World-space X/Y/Z axes from a bone's roll-aware world matrix."""
    return (
        _safe_normalized(world_matrix.col[0].to_3d(), Vector((1, 0, 0))),
        _safe_normalized(world_matrix.col[1].to_3d(), Vector((0, 1, 0))),
        _safe_normalized(world_matrix.col[2].to_3d(), Vector((0, 0, 1))),
    )


def pick_bone_element(context, coord, radius_px: float = 15.0, *,
                      edge_midpoint: bool = False) -> PickResult:
    """Pick the nearest edit-bone element (head/tail point or bone body).

    Mirrors :func:`pick_element` for meshes: a head/tail within *radius_px*
    behaves like a VERT pick and always wins over the bone body, which behaves
    like an EDGE pick (snapped to the closest point on the segment, or its
    midpoint when *edge_midpoint* is set).

    The orientation frame is the bone's own world matrix (roll-aware,
    Y = head->tail), so the resulting pivot aligns to the bone. Returns an
    already-materialized result (no live bone references) – the frame and
    draw-coords are baked in exactly like :func:`materialize`.
    """
    bone_data = []
    for obj in _edit_armatures(context):
        mw = obj.matrix_world
        for eb in obj.data.edit_bones:
            if eb.hide:
                continue
            # Bone world orientation (roll-aware); col[1] is head->tail (Y).
            ax, ay, az = _bone_axes(mw @ eb.matrix)
            bone_data.append((mw @ eb.head, mw @ eb.tail, ax, ay, az))

    chosen = _pick_bones(context, bone_data, coord, radius_px,
                         frozenset(('VERT', 'EDGE')), edge_midpoint)
    if chosen is None:
        return _empty()

    ptype, origin_w, frame, draw_coords = chosen
    return PickResult(
        type=ptype,
        element=None,
        hitpos=origin_w,
        obj=None,
        _bm_ref=None,
        _frame=frame,
        _draw_coords=draw_coords,
    )


def _pick_on_armature(context, obj, coord, radius_px, elements_set, *,
                      edge_midpoint: bool = False) -> PickResult:
    """Pick the nearest pose-bone element on an armature in Object/Pose mode.

    ``edit_bones`` only exist while the armature is in Edit mode; in Object and
    Pose mode the bones drawn in the viewport are the *posed* bones, so this
    reads ``obj.pose.bones`` (head/tail/matrix in armature space → world). The
    picking and orientation rules mirror :func:`pick_bone_element` so Flow
    behaves identically to Edit Armature mode.
    """
    pose = getattr(obj, 'pose', None)
    if pose is None:
        return _empty(obj)

    mw = obj.matrix_world
    bone_data = []
    for pb in pose.bones:
        bone = pb.bone
        if bone is None or bone.hide:
            continue
        ax, ay, az = _bone_axes(mw @ pb.matrix)
        bone_data.append((mw @ pb.head, mw @ pb.tail, ax, ay, az))

    chosen = _pick_bones(context, bone_data, coord, radius_px,
                         elements_set & frozenset(('VERT', 'EDGE')),
                         edge_midpoint)
    if chosen is None:
        return _empty(obj)

    ptype, origin_w, frame, draw_coords = chosen
    return PickResult(
        type=ptype,
        element=None,
        hitpos=origin_w,
        obj=obj,
        _bm_ref=None,
        _frame=frame,
        _draw_coords=draw_coords,
    )


# ---------------------------------------------------------------------------
# Element frame (position + orientation)
# ---------------------------------------------------------------------------

def _safe_normalized(v, fallback=None):
    """Normalize vector, return *fallback* if zero-length."""
    ls = v.length_squared
    if ls < 1e-12:
        return fallback if fallback is not None else Vector((0, 0, 1))
    return v / ls ** 0.5


def _normal_matrix(obj):
    """3x3 matrix that correctly transforms *normals* to world space.

    Normals must be transformed by the inverse-transpose of the upper-left 3x3,
    NOT the matrix itself – otherwise any non-uniform scale skews the normal.
    """
    return obj.matrix_world.to_3x3().inverted_safe().transposed()


def _fallback_normal_from_tangent(tangent_w):
    """Pick an arbitrary normal perpendicular to *tangent_w*."""
    up = Vector((0, 0, 1))
    if abs(up.dot(tangent_w)) > 0.9:
        up = Vector((0, 1, 0))
    return _safe_normalized(tangent_w.cross(up), Vector((0, 0, 1)))


def element_frame(result: PickResult):
    """Return *(origin, tangent, bitangent, normal)* in world space.

    Build a 4x4 matrix:
        ``Matrix((tangent, bitangent, normal, origin)).to_4x4().transposed()``
    """
    if result.is_empty:
        raise ValueError('PickResult is empty')

    # Pre-computed frame (curves and other non-BMesh picks)
    if result._frame is not None:
        return result._frame

    obj = result.obj
    mat = obj.matrix_world
    mat3 = mat.to_3x3()            # directions along the surface (tangents)
    nmat = _normal_matrix(obj)     # normals (inverse-transpose)
    elem = result.element

    if result.type == 'FACE':
        normal_w = _safe_normalized(nmat @ elem.normal, Vector((0, 0, 1)))
        edge_vec = elem.verts[1].co - elem.verts[0].co
        tangent_w = _safe_normalized(mat3 @ edge_vec, Vector((1, 0, 0)))

    elif result.type == 'EDGE':
        tangent_w = _safe_normalized(
            mat @ elem.verts[1].co - mat @ elem.verts[0].co,
            Vector((1, 0, 0)))
        # Average of the (already correct) per-face normals, area-weighted by
        # using the raw (un-normalized) face normals so big faces dominate –
        # this matches Blender's own "Normal" orientation behaviour.
        if elem.link_faces:
            acc = Vector()
            for f in elem.link_faces:
                acc += nmat @ f.normal
            normal_w = _safe_normalized(acc, None)
            if normal_w is None:
                normal_w = _fallback_normal_from_tangent(tangent_w)
        else:
            normal_w = _fallback_normal_from_tangent(tangent_w)

    else:  # VERT
        # Use the vertex normal computed by Blender's kernel – it is already a
        # correct, area/angle-weighted average. Manual face averaging here was
        # the source of normals snapping to Z on sharp/concave verts.
        normal_w = _safe_normalized(nmat @ elem.normal, None)

        if elem.link_edges:
            other = elem.link_edges[0].other_vert(elem)
            tangent_w = _safe_normalized(
                mat @ other.co - mat @ elem.co,
                Vector((1, 0, 0)))
        else:
            tangent_w = Vector((1, 0, 0))

        if normal_w is None:
            normal_w = _fallback_normal_from_tangent(tangent_w)

    # Normal is the authoritative axis (Z). Re-orthogonalize the tangent into
    # the plane perpendicular to it. If the tangent is (nearly) parallel to the
    # normal the cross product is unstable – pick an arbitrary perpendicular.
    if abs(normal_w.dot(tangent_w)) > 0.999:
        tangent_w = _fallback_normal_from_tangent(normal_w)
    bitangent_w = _safe_normalized(normal_w.cross(tangent_w), Vector((0, 1, 0)))
    tangent_w = _safe_normalized(bitangent_w.cross(normal_w), Vector((1, 0, 0)))

    # Origin – always prefer the stored hitpos
    if result.hitpos is not None:
        origin = result.hitpos
    elif result.type == 'VERT':
        origin = mat @ elem.co
    elif result.type == 'EDGE':
        origin = mat @ ((elem.verts[0].co + elem.verts[1].co) * 0.5)
    else:
        origin = mat @ elem.calc_center_median()

    return origin, tangent_w, bitangent_w, normal_w


def _draw_coords_for(result: PickResult):
    """World-space coords used to highlight the picked element.

    VERT -> [point], EDGE -> [v0, v1], FACE -> [v0, v1, ... vn].
    Returns ``None`` if it cannot be computed (e.g. stale element).
    """
    if result._draw_coords is not None:
        return result._draw_coords

    elem = result.element
    if elem is None:
        # Non-mesh pick (curve control point, object origin): single point.
        return [result.hitpos] if result.hitpos is not None else None

    mat = result.obj.matrix_world
    if result.type == 'VERT':
        return [mat @ elem.co]
    if result.type == 'EDGE':
        v0, v1 = elem.verts
        return [mat @ v0.co, mat @ v1.co]
    # FACE
    return [mat @ v.co for v in elem.verts]


def materialize(result: PickResult) -> PickResult:
    """Return a copy of *result* with frame + draw coords pre-computed and all
    live BMesh references dropped.

    The Flow gizmo stores a pick between ``test_select`` (frame N) and
    ``draw``/``invoke`` (frame N+1).  Holding live ``BMVert``/``BMEdge``/
    ``BMFace`` handles across frames is unsafe – the user can edit the mesh and
    invalidate them, which raises ``ReferenceError`` (or crashes).  We therefore
    extract everything we need now, while the element is guaranteed valid, and
    keep only plain numbers afterwards.
    """
    if result is None or result.is_empty:
        return result

    try:
        frame = element_frame(result)
        draw_coords = _draw_coords_for(result)
    except (ReferenceError, AttributeError, ValueError, IndexError):
        return _empty(result.obj)

    return PickResult(
        type=result.type,
        element=None,
        hitpos=frame[0].copy(),
        obj=result.obj,
        _bm_ref=None,
        _frame=frame,
        _draw_coords=draw_coords,
    )


__all__ = [
    'PickDataCache',
    'PickResult',
    'pick_element',
    'pick_bone_element',
    'element_frame',
    'materialize',
    'invalidate_object',
    'invalidate_all_caches',
]
