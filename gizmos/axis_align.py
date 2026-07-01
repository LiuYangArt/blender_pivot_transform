import bpy
from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector
from ..ilumetric.tool_utils import is_tool_active
from ..ilumetric.custom_math.bbone import get_selected_bone_points


class PIVOTTRANSFORM_GT_line3d(Gizmo):
    bl_idname = 'PIVOTTRANSFORM_GT_line3d'

    __slots__ = (
        'line_shape',      # Ссылка на GizmoShape с линией
        'p1',              # Первая точка (Vector)
        'p2',              # Вторая точка (Vector)
        'line_width',
        'color',
        'color_highlight',
        'alpha',
        'alpha_highlight',
    )

    # ---------------------------------------------------------------------
    # Вспомогательные методы для создания и отрисовки кастомной формы gizmo
    # ---------------------------------------------------------------------
    def pivottransform_draw_custom_shape(self, shape, *, matrix=None, select_id=None):
        """Отрисовка кастомной формы (линии) с использованием dashed-шейдера."""
        import gpu
        from gpu import state

        if matrix is None:
            matrix = self.matrix_world

        batch, shader = shape

        # --- Режим выделения ---
        if select_id is not None:
            gpu.select.load_id(select_id)
            color = (1.0, 1.0, 1.0, 1.0)
            use_blend = False
        else:
            # Основной цвет/альфа с учётом хайлайта
            if self.is_highlight:
                color = (*self.color_highlight, self.alpha_highlight)
            else:
                color = (*self.color, self.alpha)

            use_blend = color[3] < 1.0

        shader.bind()
        shader.uniform_float('color', color)

        # --- Глобальные настройки OpenGL ---
        state.line_width_set(self.line_width)
        #state.depth_test_set('LESS_EQUAL')
        if use_blend:
            gpu.state.blend_set('ALPHA')

        with gpu.matrix.push_pop():
            gpu.matrix.multiply_matrix(matrix)
            batch.draw()

        if use_blend:
            gpu.state.blend_set('NONE')
        state.line_width_set(1.0)
        #state.depth_test_set('NONE')

    @staticmethod
    def pivottransform_new_custom_shape(type, verts):
        """Создание GPUBatch для заданного набора вершин."""
        from gpu.types import GPUBatch, GPUVertBuf, GPUVertFormat
        import gpu

        if len(verts) != 2:
            raise ValueError("Line gizmo expects exactly 2 vertices")

        dims = len(verts[0])
        if dims not in {2, 3}:
            raise ValueError("Expected 2D or 3D vertex")

        fmt = GPUVertFormat()
        pos_id = fmt.attr_add(id="pos", comp_type='F32', len=dims, fetch_mode='FLOAT')
        vbo = GPUVertBuf(len=len(verts), format=fmt)
        vbo.attr_fill(id=pos_id, data=verts)

        batch = GPUBatch(type=type, buf=vbo)
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch.program_set(shader)
        # используем стандартный юниформ-шейдер вместо кастомного
        return (batch, shader)

    def setup(self):
        # Визуальные параметры
        self.line_width = 1

        self.color = (0.74, 0.74, 0.75)
        self.color_highlight = (1.0, 1.0, 1.0)
        self.alpha = 0.1
        self.alpha_highlight = 1.0
        self.hide_select = True

        # Точки по умолчанию
        self.p1 = Vector((0.0, 0.0, 0.0))
        self.p2 = Vector((1.0, 0.0, 0.0))

        # Не масштабируемся от расстояния камеры
        self.use_draw_scale = False

        # Создаём форму линии
        self.line_shape = self.pivottransform_new_custom_shape('LINES', [self.p1, self.p2])

    def set_points(self, p1: Vector, p2: Vector):
        """Обновляет положение концов линии и пересоздаёт форму."""
        self.p1, self.p2 = Vector(p1), Vector(p2)
        self.line_shape = self.pivottransform_new_custom_shape('LINES', [self.p1, self.p2])

    def draw(self, context):
        self.pivottransform_draw_custom_shape(self.line_shape)


class PIVOTTRANSFORM_GGT_axis_align(GizmoGroup):
    bl_idname = 'PIVOTTRANSFORM_GGT_axis_align'
    bl_label = 'Axis Align'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SHOW_MODAL_ALL'}

    # Состояние видимости/запроса refresh для PERSISTENT-группы (см. poll).
    _was_visible = False
    _needs_refresh = False

    @classmethod
    def poll(cls, context):
        visible = bool(
            is_tool_active(context, 'pivot.align')
            and context.scene.pivot_transform.tool_mode_align_axis
            and (context.active_object or context.selected_objects)
        )
        # Группа PERSISTENT: при возврате на инструмент Blender не зовёт
        # refresh(), поэтому позиции остаются от прошлого выделения. Ставим флаг
        # принудительного refresh на ближайший draw_prepare().
        if visible and not cls._was_visible:
            cls._needs_refresh = True
        cls._was_visible = visible
        return visible

    @classmethod
    def setup_keymap(cls, keyconfig):
        km = keyconfig.keymaps.new(name='Pivot Transform: Click', space_type='VIEW_3D')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK')
        return km

    def setup(self, context):
        self.align_x = self.gizmos.new('GIZMO_GT_move_3d')
        self.align_x.draw_options = {'FILL', 'FILL_SELECT', 'ALIGN_VIEW'}
        self.align_x.draw_style = 'CROSS_2D'
        self.op_x = self.align_x.target_set_operator('object.pt_set_pivot_location')
        self.op_x.custom_description = 'Set pivot X to 0'

        self.align_y = self.gizmos.new('GIZMO_GT_move_3d')
        self.align_y.draw_options = {'FILL', 'FILL_SELECT', 'ALIGN_VIEW'}
        self.align_y.draw_style = 'CROSS_2D'
        self.op_y = self.align_y.target_set_operator('object.pt_set_pivot_location')
        self.op_y.custom_description = 'Set pivot Y to 0'

        self.align_z = self.gizmos.new('GIZMO_GT_move_3d')
        self.align_z.draw_options = {'FILL', 'FILL_SELECT', 'ALIGN_VIEW'}
        self.align_z.draw_style = 'CROSS_2D'
        self.op_z = self.align_z.target_set_operator('object.pt_set_pivot_location')
        self.op_z.custom_description = 'Set pivot Z to 0'

        self.line_x = self.gizmos.new('PIVOTTRANSFORM_GT_line3d')
        self.line_y = self.gizmos.new('PIVOTTRANSFORM_GT_line3d')
        self.line_z = self.gizmos.new('PIVOTTRANSFORM_GT_line3d')

        for g in self.gizmos:
            g.color_highlight = (0, 0, 0)
            g.use_tooltip = True
            g.line_width = 3

    def invoke_prepare(self, context, gizmo):
        self.op_x.location = gizmo.matrix_basis.translation
        self.op_y.location = gizmo.matrix_basis.translation
        self.op_z.location = gizmo.matrix_basis.translation

    def draw_prepare(self, context):
        # Возврат на инструмент (poll: невидим → видим) — refresh() сам не
        # вызовется, форсим его здесь один раз.
        cls = type(self)
        if cls._needs_refresh:
            cls._needs_refresh = False
            self.refresh(context)

        x_color_axis = (1, 0.22, 0.24)
        y_color_axis = (0.2, 0.78, 0.35)
        z_color_axis = (0, 0.53, 1)
        max_alpha = 0.9

        for g in self.gizmos:
            g.scale_basis = 0.08

        self.align_x.color, self.align_x.alpha = x_color_axis, max_alpha
        self.align_y.color, self.align_y.alpha = y_color_axis, max_alpha
        self.align_z.color, self.align_z.alpha = z_color_axis, max_alpha

        self.line_x.color = x_color_axis
        self.line_y.color = y_color_axis
        self.line_z.color = z_color_axis

    def refresh(self, context):
        selObj = context.selected_objects
        midPoint = Vector()
        settings = context.scene.pivot_transform

        if context.mode == 'EDIT_ARMATURE':
            # World head/tail of the selected bones; fall back to the armature
            # origin when nothing is selected yet.
            pts = get_selected_bone_points()
            if pts:
                midPoint = sum(pts, Vector()) / len(pts)
            elif context.object is not None:
                midPoint = context.object.matrix_world.translation.copy()
        elif settings.target == 'ACTIVE': # and context.active_object
            midPoint = context.object.location.copy()
        else:
            if selObj:
                object_co = [obj.location for obj in selObj]
                midPoint = sum(object_co, Vector()) / len(selObj)

        self.align_x.matrix_basis.translation = midPoint.copy(); self.align_x.matrix_basis.translation[0] = 0
        self.align_y.matrix_basis.translation = midPoint.copy(); self.align_y.matrix_basis.translation[1] = 0
        self.align_z.matrix_basis.translation = midPoint.copy(); self.align_z.matrix_basis.translation[2] = 0

        self.line_x.set_points(midPoint, self.align_x.matrix_basis.translation)
        self.line_y.set_points(midPoint, self.align_y.matrix_basis.translation)
        self.line_z.set_points(midPoint, self.align_z.matrix_basis.translation)

        pivot_loc = None
        if context.object is not None:
            pivot_loc = context.object.matrix_world.translation.copy()

        def _co_equal(c1, c2, eps=1e-5):
            if c1 is None or c2 is None:
                return False
            return (c1 - c2).length_squared < eps ** 2

        # Проверяем каждый гизмо оси и связанную линию
        axis_pairs = [
            (self.align_x, self.line_x),
            (self.align_y, self.line_y),
            (self.align_z, self.line_z),
        ]

        for gizmo, line in axis_pairs:
            if _co_equal(gizmo.matrix_basis.translation, pivot_loc):
                gizmo.hide = True
                line.hide = True
            else:
                gizmo.hide = False
                line.hide = False


classes = [
    PIVOTTRANSFORM_GT_line3d,
    PIVOTTRANSFORM_GGT_axis_align,
    ]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
