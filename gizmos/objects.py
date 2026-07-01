import bpy
from bpy.types import GizmoGroup
from ..ilumetric.tool_utils import is_pivot_tool_active
from bpy.types import Operator, Menu
from ..utils.utils import set_pivot_location, set_pivot_rotation

# HACK TODO измень подход с передачей имени объекта в оператор

class OBJECT_OT_pt_copy_transform_menu(Operator):
    """Operator that calls the PIE menu for copying transforms"""
    bl_idname = 'object.pt_copy_transform_menu'
    bl_label = 'Copy Transform Pie Menu'
    bl_description = "Open copy-pivot actions for this object"
    bl_options = {'INTERNAL'}  # без отмены – само меню не изменяет сцену

    obj_name: bpy.props.StringProperty(name="Object Name")

    def invoke(self, context, event):
        # Сохраняем имя объекта во временное свойство WindowManager, чтобы меню могло его получить
        context.window_manager["_pivottransform_src_obj"] = self.obj_name
        # Вызываем PIE-меню
        bpy.ops.wm.call_menu_pie(name="PIVOTTRANSFORM_MT_copy_transform_pie")
        return {'FINISHED'}


class OBJECT_OT_pt_copy_transforms(Operator):
    """Copying the pivot position/rotation from the selected object"""
    bl_idname = 'object.pt_copy_transforms'
    bl_label = 'Copy Transforms'
    bl_description = "Copy this object's pivot position and/or rotation to the selection"
    bl_options = {'REGISTER', 'UNDO'}

    obj_name: bpy.props.StringProperty(name="Object Name")
    copy_location: bpy.props.BoolProperty(name="Location", default=False)
    copy_rotation: bpy.props.BoolProperty(name="Rotation", default=False)

    @classmethod
    def poll(cls, context):
        return context.selected_objects

    def execute(self, context):
        src_obj = bpy.data.objects.get(self.obj_name)
        if src_obj is None:
            self.report({'WARNING'}, 'Source object not found')
            return {'CANCELLED'}

        # Вычисляем исходные данные
        src_loc = src_obj.matrix_world.translation.copy()
        src_rot = src_obj.matrix_world.decompose()[1]  # Quaternion

        # --- Копирование локации
        if self.copy_location:
            set_pivot_location(context, location=src_loc, undoPush=False)

        # --- Копирование вращения
        if self.copy_rotation:
            set_pivot_rotation(context, rotation=src_rot, undoPush=False)

        return {'FINISHED'}


class PIVOTTRANSFORM_MT_copy_transform_pie(Menu):
    bl_idname = 'PIVOTTRANSFORM_MT_copy_transform_pie'
    bl_label = 'Copy Transform'

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()

        wm = context.window_manager
        obj_name = wm.get("_pivottransform_src_obj", "")

        # --- Position
        op = pie.operator('object.pt_copy_transforms', text='Position', icon='EMPTY_AXIS')
        op.obj_name = obj_name
        op.copy_location = True
        op.copy_rotation = False

        # --- Rotation
        op = pie.operator('object.pt_copy_transforms', text='Rotation', icon='DRIVER_ROTATIONAL_DIFFERENCE')
        op.obj_name = obj_name
        op.copy_location = False
        op.copy_rotation = True

        # --- Both
        op = pie.operator('object.pt_copy_transforms', text='Pos & Rot', icon='ORIENTATION_GIMBAL')
        op.obj_name = obj_name
        op.copy_location = True
        op.copy_rotation = True


class PIVOTTRANSFORM_GGT_objects_points(GizmoGroup):
    bl_idname = 'PIVOTTRANSFORM_GGT_objects_points'
    bl_label = 'Objects Points'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        return (
            is_pivot_tool_active(context) and
            len(context.selected_objects) > 1
        )

    @classmethod
    def setup_keymap(cls, keyconfig):
        km = keyconfig.keymaps.new(name='Pivot Transform: Click', space_type='VIEW_3D')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK')
        return km

    def setup(self, context):
        self.point_gizmos: list[bpy.types.Gizmo] = []

    def _create_point_gizmo(self):
        g = self.gizmos.new('GIZMO_GT_move_3d')
        g.draw_options = {'FILL', 'FILL_SELECT', 'ALIGN_VIEW'}
        # g.draw_style = 'CROSS_2D'
        g.scale_basis = 0.08
        g.line_width = 3
        g.use_tooltip = True
        g.use_draw_hover = True

        g.color = (1, 0.55, 0.16)
        g.color_highlight = (1, 0.8, 0)
        g.alpha = 0.9
        g.alpha_highlight = 0.99

        # Используем наш универсальный оператор, вызывающий PIE-меню
        op = g.target_set_operator('object.pt_copy_transform_menu')
        op.obj_name = ""
        # tooltip зададим в обработчике refresh, когда будем знать имя объекта
        return g

    def refresh(self, context):
        selected = list(context.selected_objects)
        sel_count = len(selected)

        # Создаём недостающие гизмо, если выделено больше объектов,
        # чем у нас уже имеется гизмо.
        while len(self.point_gizmos) < sel_count:
            self.point_gizmos.append(self._create_point_gizmo())

        # Обновляем позиции и отображение
        for idx, obj in enumerate(selected):
            g = self.point_gizmos[idx]
            g.hide = False

            # --- Копируем матрицу объекта (позиция + вращение).
            loc = obj.matrix_world.translation.copy()
            rot_mat = obj.matrix_world.to_quaternion().to_matrix().to_4x4()
            rot_mat.translation = loc
            g.matrix_basis = rot_mat

            # Обновляем параметры нашего оператора
            op = g.target_set_operator('object.pt_copy_transform_menu')
            op.obj_name = obj.name

        # Скрываем лишние гизмо, если объектов стало меньше
        for idx in range(sel_count, len(self.point_gizmos)):
            self.point_gizmos[idx].hide = True

    # def invoke_prepare(self, context, gizmo):
    #     # Свойства оператора уже выставлены в refresh()
    #     pass

    def draw_prepare(self, context):
        any_highlight = any(getattr(g, "is_highlight", False) for g in self.point_gizmos if not getattr(g, "hide", False))
        for g in self.point_gizmos:
            if getattr(g, "hide", False):
                continue
            g.use_draw_hover = not any_highlight


classes = [
    OBJECT_OT_pt_copy_transform_menu,
    OBJECT_OT_pt_copy_transforms,
    PIVOTTRANSFORM_MT_copy_transform_pie,
    PIVOTTRANSFORM_GGT_objects_points,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
