import bpy
from contextlib import contextmanager
from bpy.types import Gizmo, GizmoGroup
from mathutils import Matrix, Vector
from bpy.props import FloatVectorProperty
from gpu import state, shader as sh
from gpu_extras.batch import batch_for_shader
from ..ilumetric.pick_util import (
    PickDataCache,
    pick_element,
    pick_bone_element,
    element_frame,
    materialize,
)
from ..ilumetric.tool_utils import is_tool_active
from ..utils.utils import set_pivot_location, set_pivot_rotation


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Pick radius in pixels for the element under the cursor.
_PICK_RADIUS_PX = 15
# Large negative select bias so the Flow gizmo never steals the cursor from
# other (interactive) gizmos – lower value = lower priority.
_SELECT_BIAS = -100
# Degenerate-length threshold for direction vectors.
_EPS = 1e-6

# Highlight colours (RGBA).
_COL_VERT = (0.36, 0.72, 1.0, 1.0)
_COL_EDGE = (0.65, 0.67, 1.0, 1.0)
_COL_FACE = (0.38, 0.33, 0.96, 0.2)
_COL_AXIS_X = (1.0, 0.13, 0.24)
_COL_AXIS_Y = (0.545, 0.8, 0.0)
_COL_AXIS_Z = (0.0, 0.4, 1.0)


# ---------------------------------------------------------------------------
# Drawing helpers (shader built once)
# ---------------------------------------------------------------------------

_UNIFORM_COLOR_SHADER = None


def _uniform_color_shader():
    global _UNIFORM_COLOR_SHADER
    if _UNIFORM_COLOR_SHADER is None:
        _UNIFORM_COLOR_SHADER = sh.from_builtin('UNIFORM_COLOR')
    return _UNIFORM_COLOR_SHADER


def _draw_primitive(prim_type, coords, color):
    shader = _uniform_color_shader()
    batch = batch_for_shader(shader, prim_type, {'pos': coords})
    shader.bind()
    shader.uniform_float('color', color)
    batch.draw(shader)


def draw_vertex(coords, color, size=20):
    state.point_size_set(size)
    _draw_primitive('POINTS', coords, color)


def draw_edge(coords, color):
    _draw_primitive('LINES', coords, color)


def draw_poly(coords, color):
    _draw_primitive('TRI_FAN', coords, color)


# ---------------------------------------------------------------------------
# Context manager for ACTIVE-only scope (operator)
# ---------------------------------------------------------------------------

@contextmanager
def _flow_active_only_scope(context):
    """Isolate selection to the active object for ACTIVE target.

    Enters OBJECT mode once for the whole scope so the inner pivot setters do
    not toggle the mode a second time, then restores selection + mode.
    """
    settings = context.scene.pivot_transform
    if settings.target != 'ACTIVE' or context.active_object is None:
        yield
        return

    active = context.active_object
    view_layer = context.view_layer
    selected_before = list(context.selected_objects)
    object_mode_before = active.mode

    try:
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for obj in list(context.selected_objects):
            obj.select_set(False)

        active.select_set(True)
        view_layer.objects.active = active
        yield
    finally:
        for obj in list(context.selected_objects):
            obj.select_set(False)

        for obj in selected_before:
            if obj and obj.name in bpy.data.objects:
                obj.select_set(True)

        if active and active.name in bpy.data.objects:
            view_layer.objects.active = active

        if object_mode_before != 'OBJECT' and context.active_object is not None:
            try:
                bpy.ops.object.mode_set(mode=object_mode_before)
            except RuntimeError:
                pass


# ---------------------------------------------------------------------------
# Orientation math
# ---------------------------------------------------------------------------

def _matrix_from_frame(frame):
    """4x4 world matrix from an (origin, tangent, bitangent, normal) frame.

    Columns are (tangent=X, bitangent=Y, normal=Z, origin) – the normal is the
    Z axis. Used by both draw() and invoke_prepare() so the highlighted axes and
    the applied orientation are guaranteed identical.
    """
    origin, tangent, bitangent, normal = frame
    return Matrix((tangent, bitangent, normal, origin)).to_4x4().transposed()


def _align_x_euler(pivot_pos, target_pos):
    """Euler (XYZ) so local +X points from *pivot_pos* toward *target_pos*.

    Uses ``Vector.to_track_quat`` which always yields a right-handed,
    orthonormal basis (no risk of a mirrored matrix).
    """
    direction = Vector(target_pos) - Vector(pivot_pos)
    if direction.length < _EPS:
        direction = Vector((1.0, 0.0, 0.0))
    quat = direction.to_track_quat('X', 'Z')
    eul = quat.to_euler('XYZ')
    return (eul.x, eul.y, eul.z)


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class OBJECT_OT_pt_flow_set_pivot(bpy.types.Operator):
    """Set Pivot or 3D Cursor from picked element (Pivot Flow)

    Click behaviour:
    • LMB              – position + orientation
    • Shift + LMB  – position only
    • Ctrl  + LMB  – orientation only
    • Shift + Ctrl + LMB – rotate pivot so +X points at element
    """

    bl_idname = 'object.pt_flow_set_pivot'
    bl_label = 'Pivot Transform: Set Pivot/Cursor'
    bl_options = {'UNDO', 'INTERNAL'}
    bl_description = 'Click: position and orientation\nShift: position only\nCtrl: orientation only\nShift+Ctrl: align +X'

    location: FloatVectorProperty(name='Location', size=3, subtype='TRANSLATION')
    rotation: FloatVectorProperty(name='Rotation', size=3, subtype='EULER')

    def invoke(self, context, event):
        self._shift = event.shift
        self._ctrl = event.ctrl
        return self.execute(context)

    def execute(self, context):
        if not context.selected_objects:
            return {'CANCELLED'}

        shift = getattr(self, '_shift', False)
        ctrl = getattr(self, '_ctrl', False)

        target_cursor = False

        loc_needed = rot_needed = True
        align_x = False
        if shift and ctrl:
            loc_needed, rot_needed, align_x = False, True, True
        elif shift:
            loc_needed, rot_needed = True, False
        elif ctrl:
            loc_needed, rot_needed = False, True

        with _flow_active_only_scope(context):
            if loc_needed:
                set_pivot_location(
                    context,
                    location=self.location,
                    cursor=target_cursor,
                    undoPush=True,
                    message='Pivot Flow – Location',
                )

            if rot_needed:
                if align_x:
                    if target_cursor:
                        pivot_pos = context.scene.cursor.location
                    elif context.active_object is not None:
                        pivot_pos = context.active_object.location
                    else:
                        return {'FINISHED'}
                    rot = _align_x_euler(pivot_pos, self.location)
                else:
                    rot = tuple(self.rotation)

                set_pivot_rotation(
                    context,
                    rotation=rot,
                    cursor=target_cursor,
                    undoPush=True,
                    message='Pivot Flow – Rotation',
                )

        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Preselect Gizmo
# ---------------------------------------------------------------------------

class PIVOTTRANSFORM_GT_preselect(Gizmo):
    bl_idname = 'PIVOTTRANSFORM_GT_preselect'

    __slots__ = (
        'elem',
        'shape_x',
        'shape_y',
        'shape_z',
        'pick_cache',
        'get_targets',
    )

    def setup(self):
        self.elem = None
        self.get_targets = None
        self.alpha = 0
        self.alpha_highlight = 1
        self.line_width = 3
        self.use_draw_modal = False
        self.select_bias = _SELECT_BIAS

        self.color = (0.38, 0.33, 0.96)

        size = 0.5
        self.shape_x = self.new_custom_shape('LINES', [(0.0, 0.0, 0.0), (size, 0.0, 0.0)])
        self.shape_y = self.new_custom_shape('LINES', [(0.0, 0.0, 0.0), (0.0, size, 0.0)])
        self.shape_z = self.new_custom_shape('LINES', [(0.0, 0.0, 0.0), (0.0, 0.0, size)])

    def test_select(self, context, location):
        settings = context.scene.pivot_transform
        cache = getattr(self, 'pick_cache', None)

        if context.mode == 'EDIT_ARMATURE':
            # Pick bone head/tail (VERT) or the bone body (EDGE) – the frame is
            # baked from the bone's own roll-aware matrix.
            result = pick_bone_element(
                context, location,
                radius_px=_PICK_RADIUS_PX,
                edge_midpoint=settings.flow_edge_midpoint,
            )
            if result is None or result.is_empty:
                self.elem = None
                return -1
            self.elem = materialize(result)
            if self.elem.is_empty:
                self.elem = None
                return -1
            return 0

        targets = self.get_targets() if self.get_targets is not None else None
        if not targets:
            self.elem = None
            return -1

        bfc = settings.flow_backface_culling

        # pick_element does its own scene ray_cast pre-filter for multi-object
        # lists (narrows mesh candidates, keeps non-mesh objects).
        result = pick_element(
            context, targets, location,
            radius_px=_PICK_RADIUS_PX,
            elements=('VERT', 'EDGE', 'FACE'),
            backface_culling=bfc,
            edge_midpoint=settings.flow_edge_midpoint,
            cache=cache,
            use_modifiers=settings.flow_use_modifiers,
            occlusion=bfc,
        )

        if result is None or result.is_empty:
            self.elem = None
            return -1

        # Snap to edge midpoint / face centre before materializing.
        if result.element is not None:
            try:
                if result.type == 'EDGE' and settings.flow_edge_midpoint:
                    v1, v2 = result.element.verts
                    result.hitpos = result.obj.matrix_world @ (
                        (v1.co + v2.co) * 0.5)
                elif result.type == 'FACE' and settings.flow_face_center:
                    result.hitpos = (
                        result.obj.matrix_world
                        @ result.element.calc_center_median())
            except (ReferenceError, AttributeError):
                self.elem = None
                return -1

        # Detach from the live BMesh: keep only numbers across frames.
        self.elem = materialize(result)
        if self.elem.is_empty:
            self.elem = None
            return -1
        return 0

    def draw(self, context):
        elem = self.elem
        if elem is None or elem.is_empty or not self.is_highlight:
            return

        try:
            frame = element_frame(elem)
        except (ValueError, ReferenceError, AttributeError):
            return

        coords = elem._draw_coords

        state.blend_set('ALPHA')
        state.line_width_set(self.line_width)
        try:
            if elem.type == 'VERT':
                draw_vertex([frame[0]], _COL_VERT)
            elif elem.type == 'EDGE' and coords:
                draw_edge(coords, _COL_EDGE)
            elif elem.type == 'FACE' and coords:
                draw_poly(coords, _COL_FACE)

            # Orientation axes
            self.matrix_basis = _matrix_from_frame(frame)

            self.color = self.color_highlight = _COL_AXIS_X
            self.draw_custom_shape(self.shape_x)
            self.color = self.color_highlight = _COL_AXIS_Y
            self.draw_custom_shape(self.shape_y)
            self.color = self.color_highlight = _COL_AXIS_Z
            self.draw_custom_shape(self.shape_z)
        finally:
            state.point_size_set(1.0)
            state.line_width_set(1.0)
            state.blend_set('NONE')


# ---------------------------------------------------------------------------
# Gizmo Group
# ---------------------------------------------------------------------------

class PIVOTTRANSFORM_GGT_preselect(GizmoGroup):
    bl_idname = 'PIVOTTRANSFORM_GGT_preselect'
    bl_label = 'Preselect'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'VR_REDRAWS'}

    @classmethod
    def poll(cls, context):
        if is_tool_active(context, 'pivot.transform'):
            return bool(context.selected_objects)
        return False

    @classmethod
    def setup_keymap(cls, keyconfig):
        km = keyconfig.keymaps.new(name='Pivot Transform: Click', space_type='VIEW_3D')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK', ctrl=True)
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK', shift=True)
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK', ctrl=True, shift=True)
        return km

    def setup(self, context):
        self._pick_cache = PickDataCache()
        self._targets = []
        self._refresh_targets(context)
        self.preselect = self.gizmos.new('PIVOTTRANSFORM_GT_preselect')
        self.preselect.pick_cache = self._pick_cache
        self.preselect.get_targets = lambda: self._targets

    def _refresh_targets(self, context):
        """Recompute the candidate object list.

        All visible objects are candidates – Flow can pick elements on any
        object under the cursor, not just the selected ones.  For mesh objects
        ``pick_element`` narrows them to the scene.ray_cast hit; non-mesh
        objects (curves, empties, lights) are invisible to ray_cast so they are
        all kept.  Computed here (on refresh) rather than per mouse-move.
        """
        self._targets = list(context.visible_objects)

    def refresh(self, context):
        # NOTE: the geometry cache is invalidated by the depsgraph handler
        # (see _on_depsgraph_update), NOT here – refresh() fires on
        # selection-type changes, not on geometry edits. We only refresh the
        # (cheap) candidate target list, which DOES need to follow selection.
        self._refresh_targets(context)

    def invoke_prepare(self, context, gizmo):
        op = gizmo.target_set_operator('object.pt_flow_set_pivot')
        # Read position + orientation straight from the picked element's frame,
        # NOT from gizmo.matrix_basis. matrix_basis is only written in draw(),
        # which may not have run for the current pick (no highlight / early
        # return), leaving a stale matrix for the click.
        elem = getattr(gizmo, 'elem', None)
        if elem is not None and not elem.is_empty:
            try:
                frame = element_frame(elem)
            except (ValueError, ReferenceError, AttributeError):
                frame = None
        else:
            frame = None

        if frame is not None:
            mat = _matrix_from_frame(frame)
            op.location = mat.translation
            op.rotation = mat.to_euler()
        else:
            op.location = gizmo.matrix_basis.translation
            op.rotation = gizmo.matrix_basis.to_euler()


classes = [
    OBJECT_OT_pt_flow_set_pivot,
    PIVOTTRANSFORM_GT_preselect,
    PIVOTTRANSFORM_GGT_preselect,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
