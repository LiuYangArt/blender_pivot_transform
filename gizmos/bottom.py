import bpy
from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector, Matrix
from gpu import state
from ..ilumetric.tool_utils import is_tool_active


def get_circle(position, radius, segments=60):  # TODO перенести в utils
    from math import cos, sin, tau
    start = -tau / 4  # начинаем с нижней точки

    if len(position) == 2:
        mx, my = position
        step = tau / segments
        return [(radius * cos(start + i * step) + mx,
                 radius * sin(start + i * step) + my)
                for i in range(segments + 1)]

    elif len(position) == 3:
        mx, my, mz = position
        step = tau / segments
        return [(radius * cos(start + i * step) + mx,
                 radius * sin(start + i * step) + my,
                 mz)
                for i in range(segments + 1)]

    else:
        raise ValueError("Position must be a 2D or 3D Vector")


class PIVOTTRANSFORM_GT_circle_bottom(Gizmo):
    bl_idname = 'PIVOTTRANSFORM_GT_circle_bottom'

    __slots__ = (
        'circle_out_shape',
        'circle_in_shape',
        )

    def setup(self):
        self.line_width = 1.5
        self.color = (1, 0.55, 0.16)
        self.color_highlight = (0, 0, 0)
        self.alpha = 0.9
        self.alpha_highlight = 0.99

        if not hasattr(self, 'circle_out_shape'):
            circle_out = get_circle(position=(0, 0), radius=1.2, segments=24)
            self.circle_out_shape = self.new_custom_shape('LINES', circle_out)
        if not hasattr(self, 'circle_in_shape'):
            circle_in = get_circle(position=(0, 0), radius=0.5, segments=32)
            self.circle_in_shape = self.new_custom_shape('TRI_FAN', circle_in)

    def draw(self, context):
        state.line_width_set(self.line_width)
        state.depth_test_set('LESS_EQUAL')
        self.draw_custom_shape(self.circle_out_shape)
        self.draw_custom_shape(self.circle_in_shape)
        state.depth_test_set('NONE')
        state.line_width_set(1.0)

    def draw_select(self, context, select_id):
        self.draw_custom_shape(self.circle_out_shape, select_id=select_id)
        self.draw_custom_shape(self.circle_in_shape, select_id=select_id)


class PIVOTTRANSFORM_GGT_bottom(GizmoGroup):
    bl_idname = 'PIVOTTRANSFORM_GGT_bottom'
    bl_label = 'Bottom'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        if is_tool_active(context, 'pivot.align') and context.scene.pivot_transform.tool_mode_bottom:
            return context.active_object or context.selected_objects

    @classmethod
    def setup_keymap(cls, keyconfig):
        km = keyconfig.keymaps.new(name='Pivot Transform: Click', space_type='VIEW_3D')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK')
        return km

    def setup(self, context):
        self.bottom_vertex = self.gizmos.new('PIVOTTRANSFORM_GT_circle_bottom')
        self.op_vertex = self.bottom_vertex.target_set_operator('object.pt_set_pivot_location')
        self.op_vertex.custom_description = 'Move pivot to the lowest geometry point'
        self.bottom_origin = self.gizmos.new('PIVOTTRANSFORM_GT_circle_bottom')
        self.op_origin = self.bottom_origin.target_set_operator('object.pt_set_pivot_location')
        self.op_origin.custom_description = 'Move pivot below the current origin'

        for g in self.gizmos:
            g.scale_basis = 0.2

    def invoke_prepare(self, context, gizmo):
        self.op_vertex.location = gizmo.matrix_basis.translation
        self.op_origin.location = gizmo.matrix_basis.translation

    def refresh(self, context):
        # Обновляем положение гизма в зависимости от выделенных объектов

        depsgraph = context.evaluated_depsgraph_get()

        # --- Определяем самую нижнюю вершину среди всех выделенных объектов ---
        min_z = float("inf")
        lowest_co = None  # мировые координаты самой нижней вершины

        for obj in context.selected_objects:
            if obj.type == 'MESH':
                # Берём вычисленную (evaluated) меш-версию, чтобы учитывать модификаторы
                obj_eval = obj.evaluated_get(depsgraph)
                mesh = obj_eval.to_mesh()

                try:
                    mw = obj.matrix_world
                    for v in mesh.vertices:
                        co_world = mw @ v.co
                        if co_world.z < min_z:
                            min_z = co_world.z
                            lowest_co = co_world.copy()
                finally:
                    obj_eval.to_mesh_clear()

            else:
                # Для прочих типов берём точки bound_box
                mw = obj.matrix_world
                for corner in obj.bound_box:
                    co_world = mw @ Vector(corner)
                    if co_world.z < min_z:
                        min_z = co_world.z
                        lowest_co = co_world.copy()

        # Если ничего не нашли – выход
        if lowest_co is None:
            return

        # --- Вторая точка: под пивотом активного объекта, но на высоте min_z ---
        active_obj = context.object or (context.selected_objects[0] if context.selected_objects else None)
        if active_obj is None:
            return

        pivot_loc = active_obj.matrix_world.translation
        origin_bottom_co = Vector((pivot_loc.x, pivot_loc.y, min_z))

        # Устанавливаем позиции для гизмов (ориентация не задаётся)
        mat_vert = Matrix.Identity(4)
        mat_vert.translation = lowest_co
        self.bottom_vertex.matrix_basis = mat_vert

        mat_orig = Matrix.Identity(4)
        mat_orig.translation = origin_bottom_co
        self.bottom_origin.matrix_basis = mat_orig

    def draw_prepare(self, context):
        p1 = self.bottom_vertex.matrix_basis.translation
        p2 = self.bottom_origin.matrix_basis.translation

        # Локация пивота активного объекта (если есть)
        pivot_loc = None
        if context.object is not None:
            pivot_loc = context.object.matrix_world.translation.copy()

        # Вспомогательная функция сравнения координат с учётом допуска
        def _co_equal(c1, c2, eps=1e-5):
            if c1 is None or c2 is None:
                return False
            return (c1 - c2).length_squared < eps ** 2

        # Скрываем гизмо, если оно совпадает с пивотом
        if _co_equal(p1, pivot_loc):
            self.bottom_vertex.hide = True
        else:
            self.bottom_vertex.hide = False

        # Скрываем второй гизмо, если точки совпадают
        if _co_equal(p1, p2) or _co_equal(p2, pivot_loc):
            self.bottom_origin.hide = True
        else:
            self.bottom_origin.hide = False







classes = [
    PIVOTTRANSFORM_GT_circle_bottom,
    PIVOTTRANSFORM_GGT_bottom,
    ]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
