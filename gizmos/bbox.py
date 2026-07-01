import bpy
import bmesh
import gpu
from itertools import product

from bpy.types import Operator, Gizmo, GizmoGroup
from bpy.props import FloatVectorProperty, StringProperty
from mathutils import Vector, Matrix
from gpu import state

from ..utils.utils import set_pivot_location
from ..utils.matrix import get_orientation
from ..ilumetric.tool_utils import is_tool_active
from ..ilumetric.custom_math.bcurve import get_selected_curve_points
from ..ilumetric.custom_math.bbone import get_selected_bone_points


# ---------------------------------------------------------------------------
# Параметры
# ---------------------------------------------------------------------------

# Относительный порог вырожденности оси: ось считается «нулевой», если её
# размер меньше, чем `bbox_size * _DEGENERATE_REL` (с абсолютным минимумом).
_DEGENERATE_REL = 1e-4
_DEGENERATE_ABS = 1e-7


# ---------------------------------------------------------------------------
# Инвалидация кеша геометрии
# ---------------------------------------------------------------------------
#
# GizmoGroup.refresh() срабатывает на изменение ВЫДЕЛЕНИЯ, но не на правки
# геометрии (G-move в эдите, пересчёт модификаторов, смена кадра). Поэтому
# собранные мировые точки нужно инвалидировать из depsgraph_update_post
# (см. __init__._on_depsgraph_update). Используем generation-счётчик, чтобы
# несколько вьюпортов одновременно обновлялись корректно (а не «кто первый
# сбросил флаг»).

_GEOMETRY_GEN = 0


def mark_dirty():
    """Пометить кеш геометрии bbox как устаревший (дёргается из depsgraph)."""
    global _GEOMETRY_GEN
    _GEOMETRY_GEN += 1


# ---------------------------------------------------------------------------
# Сбор мировых точек по режимам
# ---------------------------------------------------------------------------

def _object_bound_points(objects):
    """Углы bound_box объектов в мировых координатах (8 точек на объект).

    bound_box поддерживается самим Blender, поэтому это во много раз быстрее
    перебора всех вершин и является стандартным «bounding box» объекта."""
    pts = []
    for ob in objects:
        mw = ob.matrix_world
        pts.extend(mw @ Vector(corner) for corner in ob.bound_box)
    return pts


def gather_world_points(context):
    """Мировые точки текущего выделения в зависимости от режима.

    OBJECT      — bound_box выбранных объектов (быстро).
    EDIT_MESH   — выбранные вершины bmesh.
    EDIT_CURVE/SURFACE — выбранные контрольные точки/ручки.
    EDIT_ARMATURE/POSE — головы/хвосты выбранных костей.
    EDIT_LATTICE       — выбранные точки решётки.
    """
    mode = context.mode

    if mode == 'OBJECT':
        return _object_bound_points(context.selected_objects)

    if mode == 'EDIT_MESH':
        pts = []
        for ob in context.objects_in_mode_unique_data:
            if ob.type != 'MESH' or ob.data.total_vert_sel == 0:
                continue
            mw = ob.matrix_world
            bm = bmesh.from_edit_mesh(ob.data)
            pts.extend(mw @ v.co for v in bm.verts if v.select)
        return pts

    if mode in {'EDIT_CURVE', 'EDIT_SURFACE'}:
        return get_selected_curve_points()

    if mode in {'EDIT_ARMATURE', 'POSE'}:
        return get_selected_bone_points()

    if mode == 'EDIT_LATTICE':
        pts = []
        for ob in context.objects_in_mode_unique_data:
            if ob.type != 'LATTICE':
                continue
            mw = ob.matrix_world
            pts.extend(mw @ p.co_deform for p in ob.data.points
                       if getattr(p, 'select', False))
        return pts

    # Прочие режимы — запасной вариант через bound_box.
    return _object_bound_points(context.selected_objects)


def has_selection(context):
    """Лёгкая проверка наличия выделения для poll() (без сбора координат)."""
    mode = context.mode

    if mode == 'OBJECT':
        return len(context.selected_objects) > 0

    if mode == 'EDIT_MESH':
        return any(ob.type == 'MESH' and ob.data.total_vert_sel > 0
                   for ob in context.objects_in_mode_unique_data)

    if mode in {'EDIT_CURVE', 'EDIT_SURFACE'}:
        return len(get_selected_curve_points()) > 0

    if mode in {'EDIT_ARMATURE', 'POSE'}:
        return len(get_selected_bone_points()) > 0

    if mode == 'EDIT_LATTICE':
        return any(getattr(p, 'select', False)
                   for ob in context.objects_in_mode_unique_data
                   if ob.type == 'LATTICE' for p in ob.data.points)

    return False


# ---------------------------------------------------------------------------
# Геометрия bbox: проекция в ориентацию + определение размерности
# ---------------------------------------------------------------------------

class BBoxData:
    """Результат расчёта bounding box в системе ориентации.

    Хранит мировые точки углов/рёбер/граней, центр, локальный каркас (для
    отрисовки) и размерность (0..3)."""

    __slots__ = ('corners', 'edges', 'faces', 'center',
                 'line_coords', 'shape_key', 'ndim')

    def __init__(self):
        self.corners = []       # мировые позиции углов (2**ndim)
        self.edges = []         # мировые середины рёбер
        self.faces = []         # мировые центры граней (только 3D)
        self.center = Vector()  # мировой центр bbox
        self.line_coords = []   # координаты каркаса в локальном пространстве
        self.shape_key = None   # ключ для кеширования GPU-батча каркаса
        self.ndim = 0


def compute_bbox(world_points, rot):
    """Построить BBoxData из мировых точек и матрицы ориентации (3x3).

    Возвращает None, если точек нет."""
    if not world_points:
        return None

    rot_inv = rot.transposed()

    # min/max в системе ориентации
    inf = float('inf')
    min_x = min_y = min_z = inf
    max_x = max_y = max_z = -inf
    for p in world_points:
        f = rot_inv @ p
        x, y, z = f.x, f.y, f.z
        if x < min_x: min_x = x
        if x > max_x: max_x = x
        if y < min_y: min_y = y
        if y > max_y: max_y = y
        if z < min_z: min_z = z
        if z > max_z: max_z = z

    lo = (min_x, min_y, min_z)
    hi = (max_x, max_y, max_z)
    mid = ((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (min_z + max_z) * 0.5)
    dims = (max_x - min_x, max_y - min_y, max_z - min_z)

    # --- определение размерности ---------------------------------------
    size = max(dims)
    eps = max(size * _DEGENERATE_REL, _DEGENERATE_ABS)
    active = tuple(i for i in range(3) if dims[i] > eps)
    ndim = len(active)

    data = BBoxData()
    data.ndim = ndim
    mid_v = Vector(mid)
    data.center = rot @ mid_v

    if ndim == 0:
        # одна точка — только центр
        return data

    # --- углы (в системе ориентации) -----------------------------------
    # Для вырожденных осей координата фиксируется в середине.
    axis_choices = [(0, 1) if i in active else (None,) for i in range(3)]
    combos = list(product(*axis_choices))

    corners_frame = []
    for combo in combos:
        vals = []
        for i in range(3):
            c = combo[i]
            if c is None:
                vals.append(mid[i])
            else:
                vals.append(lo[i] if c == 0 else hi[i])
        corners_frame.append(Vector(vals))

    corners_world = [rot @ c for c in corners_frame]

    # --- рёбра: пары углов, отличающиеся ровно по одной оси -------------
    edge_pairs = []
    n = len(combos)
    for a in range(n):
        ca = combos[a]
        for b in range(a + 1, n):
            cb = combos[b]
            if sum(1 for i in range(3) if ca[i] != cb[i]) == 1:
                edge_pairs.append((a, b))

    # --- каркас (локальные координаты относительно центра) -------------
    line_coords = []
    for a, b in edge_pairs:
        line_coords.append(tuple(corners_frame[a] - mid_v))
        line_coords.append(tuple(corners_frame[b] - mid_v))
    data.line_coords = line_coords
    data.shape_key = (active, round(dims[0], 5), round(dims[1], 5), round(dims[2], 5))

    # --- интерактивные ручки по размерности ----------------------------
    # 1D: только 2 конца. 2D: 4 угла + 4 середины рёбер. 3D: + 6 центров граней.
    data.corners = corners_world

    if ndim >= 2:
        data.edges = [(corners_world[a] + corners_world[b]) * 0.5
                      for a, b in edge_pairs]

    if ndim == 3:
        faces_frame = []
        for i in range(3):
            for val in (lo[i], hi[i]):
                f = Vector(mid)
                f[i] = val
                faces_frame.append(f)
        data.faces = [rot @ f for f in faces_frame]

    return data


# ---------------------------------------------------------------------------
# Оператор установки Pivot по позиции (TODO: вынести в operators/)
# ---------------------------------------------------------------------------

class OBJECT_OT_pt_set_pivot_location(Operator):
    bl_idname = 'object.pt_set_pivot_location'
    bl_label = 'Pivot To Location'
    bl_description = 'Move the pivot to a specified location'
    bl_options = {'UNDO', 'INTERNAL'}

    location: FloatVectorProperty(name='Location', size=3, subtype='TRANSLATION')
    custom_description: StringProperty(name='Custom Description', default='Move pivot to bounding-box point')

    @classmethod
    def description(self, context, properties):
        return properties.custom_description or self.bl_description

    def invoke(self, context, event):
        if event.ctrl:
            set_pivot_location(context, location=self.location, cursor=True)
        else:
            set_pivot_location(context, location=self.location, undoPush=True, message='Pivot To BBox')
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Каркас bbox (некликабельная гизмо-обёртка LINES)
# ---------------------------------------------------------------------------

class PIVOTTRANSFORM_GT_cage3d(Gizmo):
    bl_idname = 'PIVOTTRANSFORM_GT_cage3d'

    __slots__ = (
        'custom_shape',   # (batch, shader) каркаса или None
        '_shape_key',     # ключ кеша, чтобы не пересобирать батч каждый кадр
    )

    def setup(self):
        self.line_width = 2
        self.color = (0, 0.52, 0.46)
        self.alpha = 0.5
        # не масштабируем по расстоянию до камеры
        self.use_draw_scale = False
        self.custom_shape = None
        self._shape_key = None

    def set_edges(self, coords, key):
        """Обновить каркас, пересобирая GPU-батч только при смене формы."""
        if key == self._shape_key:
            return
        self._shape_key = key
        self.custom_shape = self.new_custom_shape('LINES', coords) if coords else None

    def draw(self, context):
        shape = self.custom_shape
        if shape is None:
            return

        batch, shader = shape
        color = (*self.color, self.alpha)

        shader.bind()
        shader.uniform_float('color', color)

        state.blend_set('ALPHA')
        state.line_width_set(self.line_width)
        state.depth_test_set('LESS_EQUAL')

        with gpu.matrix.push_pop():
            gpu.matrix.multiply_matrix(self.matrix_world)
            batch.draw(shader)

        state.line_width_set(1.0)
        state.depth_test_set('NONE')
        state.blend_set('NONE')


# ---------------------------------------------------------------------------
# Группа гизмо bbox
# ---------------------------------------------------------------------------

class PIVOTTRANSFORM_GGT_bbox(GizmoGroup):
    bl_idname = 'pivottransform.bbox'
    bl_label = 'BBox'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    # Режимы, в которых инструмент собирает bbox под-элементов.
    _SUPPORTED_MODES = {
        'OBJECT', 'EDIT_MESH', 'EDIT_CURVE', 'EDIT_SURFACE',
        'EDIT_ARMATURE', 'POSE', 'EDIT_LATTICE',
    }

    # Была ли группа видимой на прошлом poll() (для детекта возврата на тул).
    _was_visible = False

    @classmethod
    def poll(cls, context):
        visible = (
            is_tool_active(context, 'pivot.bbox')
            and context.mode in cls._SUPPORTED_MODES
            and bool(has_selection(context))
        )
        # Группа PERSISTENT: при возврате на инструмент Blender не зовёт
        # refresh()/setup(), а смена выделения на чужом туле не бампит
        # _GEOMETRY_GEN. Помечаем кеш устаревшим, чтобы draw_prepare() пересобрал
        # мировые точки под текущее выделение/ориентацию.
        if visible and not cls._was_visible:
            mark_dirty()
        cls._was_visible = visible
        return visible

    @classmethod
    def setup_keymap(cls, keyconfig):
        km = keyconfig.keymaps.new(name='Pivot Transform: Click', space_type='VIEW_3D')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK')
        return km

    def setup(self, context):
        def _make_points(count, scale):
            lst = []
            for _ in range(count):
                g = self.gizmos.new('GIZMO_GT_move_3d')
                g.draw_options = {'FILL', 'FILL_SELECT', 'ALIGN_VIEW'}
                g.scale_basis = scale
                g.color_highlight = (0, 0, 0)
                g.use_tooltip = False
                g.hide = True
                lst.append(g)
            return lst

        self.gizmos_vertex = _make_points(8, 0.05)
        self.gizmos_edge = _make_points(12, 0.025)
        self.gizmos_face = _make_points(6, 0.025)

        self.cage = self.gizmos.new('PIVOTTRANSFORM_GT_cage3d')

        # Центр bounding box
        self.gizmo_center = self.gizmos.new('GIZMO_GT_move_3d')
        self.gizmo_center.draw_options = {'FILL', 'FILL_SELECT', 'ALIGN_VIEW'}
        self.gizmo_center.draw_style = 'CROSS_2D'
        self.gizmo_center.scale_basis = 0.08
        self.gizmo_center.alpha = 0.9
        self.gizmo_center.alpha_highlight = 1.0
        self.gizmo_center.color = (1, 0.84, 0)
        self.gizmo_center.color_highlight = (0, 0, 0)
        self.gizmo_center.use_tooltip = True
        self.gizmo_center.line_width = 3
        self.gizmo_center.hide = True

        self._world_points = []
        self._seen_gen = -1

    # --- сбор/построение ---------------------------------------------------

    def _gather(self, context):
        self._world_points = gather_world_points(context)

    @staticmethod
    def _place(pool, points):
        """Расставить точки по гизмо-пулу, лишние — спрятать."""
        count = len(points)
        for i, g in enumerate(pool):
            if i < count:
                g.hide = False
                g.matrix_basis.translation = points[i]
            else:
                g.hide = True

    def _hide_all(self):
        for g in self.gizmos_vertex:
            g.hide = True
        for g in self.gizmos_edge:
            g.hide = True
        for g in self.gizmos_face:
            g.hide = True
        self.gizmo_center.hide = True
        self.cage.set_edges([], None)

    def _rebuild(self, context):
        rot = get_orientation(context)[2].to_matrix()
        data = compute_bbox(self._world_points, rot)

        if data is None:
            self._hide_all()
            return

        # Каркас
        cage_mat = rot.to_4x4()
        cage_mat.translation = data.center
        self.cage.matrix_basis = cage_mat
        self.cage.set_edges(data.line_coords, data.shape_key)

        # Ручки
        self._place(self.gizmos_vertex, data.corners)
        self._place(self.gizmos_edge, data.edges)
        self._place(self.gizmos_face, data.faces)

        # Центр
        self.gizmo_center.hide = False
        self.gizmo_center.matrix_basis.translation = data.center

    # --- колбэки Blender ---------------------------------------------------

    def invoke_prepare(self, context, gizmo):
        op = gizmo.target_set_operator('object.pt_set_pivot_location')
        if op is None:
            return
        op.location = gizmo.matrix_basis.translation.copy()

    def refresh(self, context):
        # refresh() фиксирует смену выделения: пересобираем точки и геометрию.
        self._seen_gen = _GEOMETRY_GEN
        self._gather(context)
        self._rebuild(context)

    def draw_prepare(self, context):
        need_rebuild = False

        # Геометрия изменилась (depsgraph) — пересобрать мировые точки.
        if self._seen_gen != _GEOMETRY_GEN:
            self._seen_gen = _GEOMETRY_GEN
            self._gather(context)
            need_rebuild = True

        # Ориентация VIEW: bbox следует за камерой — репроекция каждый кадр
        # (без повторного сбора точек, только пересчёт из кеша).
        if context.window.scene.transform_orientation_slots[0].type == 'VIEW':
            need_rebuild = True

        if need_rebuild:
            self._rebuild(context)

        self._shade(context)

    # --- визуальное затухание по расстоянию --------------------------------

    def _shade(self, context):
        min_alpha, max_alpha = 0.3, 0.9
        min_scale, max_scale = 0.02, 0.09
        min_color_intensity = 0.9

        vertex_color = (0, 0.85, 0.76)
        edge_color = (0, 0.52, 0.46)
        face_color = (0, 0.85, 0.76)

        cam_pos = context.region_data.view_matrix.inverted().translation

        verts = [g for g in self.gizmos_vertex if not g.hide]
        edges = [g for g in self.gizmos_edge if not g.hide]
        faces = [g for g in self.gizmos_face if not g.hide]
        handles = verts + edges + faces
        if not handles:
            return

        distances = [(g.matrix_basis.translation - cam_pos).length for g in handles]
        if not self.gizmo_center.hide:
            distances.append((self.gizmo_center.matrix_basis.translation - cam_pos).length)

        min_d, max_d = min(distances), max(distances)
        span = max_d - min_d

        vset = set(verts)
        eset = set(edges)
        for g, dist in zip(handles, distances):
            norm = (dist - min_d) / span if span > 1e-6 else 0.0
            g.alpha = max_alpha - norm * (max_alpha - min_alpha)
            g.scale_basis = max_scale - norm * (max_scale - min_scale)

            intensity = max(1.0 - norm * (1.0 - min_color_intensity), min_color_intensity)
            if g in vset:
                base = vertex_color
            elif g in eset:
                base = edge_color
            else:
                base = face_color
            g.color = tuple(c * intensity for c in base)


classes = [
    OBJECT_OT_pt_set_pivot_location,
    PIVOTTRANSFORM_GT_cage3d,
    PIVOTTRANSFORM_GGT_bbox,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
