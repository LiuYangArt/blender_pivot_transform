import bpy
from gpu import state
from bpy.types import UIList, Operator, PropertyGroup, GizmoGroup, Gizmo, Menu
from bpy.props import FloatVectorProperty, BoolProperty, IntProperty, CollectionProperty, EnumProperty
from mathutils import Matrix, Vector, Euler, Quaternion
from ..ilumetric.tool_utils import is_tool_active
from ..ilumetric.custom_math.quaternion import normal_qat_from_two_point
from math import pi
from bpy_extras.view3d_utils import location_3d_to_region_2d


class OBJECT_OT_pt_rotate_cursor(Operator):
    bl_idname = 'object.pt_rotate_cursor'
    bl_label = 'Rotate 3D Cursor'
    bl_description = 'Rotate the 3D cursor around the selected axis'

    axis: EnumProperty(
        name='Axis',
        items=[('X', 'X', 'Rotate around the X axis'), ('Y', 'Y', 'Rotate around the Y axis'), ('Z', 'Z', 'Rotate around the Z axis')],
        default='Z',
    )

    coordinate_system: EnumProperty(
        name='Coordinate System',
        items=[('GLOBAL', 'Global', 'Use world axes'), ('CURSOR', 'Local', 'Use the 3D cursor local axes')],
        default='GLOBAL',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_mode = None  # исходный rotation_mode курсора
        self.orig_euler = None  # исходное значение rotation_euler, если применимо
        self.orig_quat = None   # исходный quaternion
        self.orig_axis_angle = None  # исходный axis_angle (angle,x,y,z)
        self.current_matrix = None  # матрица текущего вращения для финального применения
        # Счётчик суммарного угла при вращении
        self.total_angle = 0.0

    def invoke(self, context, event):
        cursor = context.scene.cursor

        # Сохраняем исходный режим и значения для возможного восстановления
        self.original_mode = cursor.rotation_mode
        if self.original_mode == 'QUATERNION':
            self.orig_quat = cursor.rotation_quaternion.copy()
        elif self.original_mode == 'AXIS_ANGLE':
            self.orig_axis_angle = tuple(cursor.rotation_axis_angle)
        else:  # любые Эйлеры
            self.orig_euler = cursor.rotation_euler.copy()

        # Переключаем курсор во внутренний XYZ для удобства вращения
        cursor.rotation_mode = 'XYZ'

        self.init_rotation = cursor.rotation_euler.copy()

        self.init_mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        self.prev_mouse_pos = self.init_mouse_pos.copy()

        region = context.region
        rv3d = context.region_data
        self.cursor_location_2d = location_3d_to_region_2d(
            region, rv3d, context.scene.cursor.location
        )

        self.rotation_axis = {
            'X': Vector((1, 0, 0)),
            'Y': Vector((0, 1, 0)),
            'Z': Vector((0, 0, 1)),
        }[self.axis]

        if self.coordinate_system == 'CURSOR':
            self.rotation_axis = (
                context.scene.cursor.rotation_euler.to_matrix() @ self.rotation_axis
            )

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            self._rotate_cursor(context, event)
        elif event.type == 'LEFTMOUSE':
            self._apply_final_rotation(context)
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            # Отменяем: возвращаем исходный режим и значения
            self._restore_original_rotation(context)
            return {'CANCELLED'}
        # Continue modal operator *and* forward the event so the gizmo can respond
        return {'RUNNING_MODAL', 'PASS_THROUGH'}

    def _rotate_cursor(self, context, event):
        rv3d = context.region_data
        current_mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))

        if self.cursor_location_2d is None:
            return

        prev_vector = self.prev_mouse_pos - self.cursor_location_2d
        current_vector = current_mouse_pos - self.cursor_location_2d

        if prev_vector.length == 0 or current_vector.length == 0:
            self.prev_mouse_pos = current_mouse_pos.copy()
            return

        delta_angle = prev_vector.angle(current_vector)
        cross_z = prev_vector.x * current_vector.y - prev_vector.y * current_vector.x
        delta_angle *= 1 if cross_z > 0 else -1

        if rv3d.view_perspective == 'CAMERA':
            view_vector = rv3d.view_matrix.inverted().col[2].xyz.normalized()
        elif rv3d.is_perspective:
            view_vector = rv3d.view_matrix.inverted().col[2].xyz.normalized()
        else:
            view_vector = rv3d.view_rotation @ Vector((0, 0, 1))

        if view_vector.dot(self.rotation_axis) < 0:
            delta_angle = -delta_angle

        if event.shift:
            delta_angle *= 0.1

        self.total_angle += delta_angle

        if event.ctrl:
            snap_inc = context.scene.tool_settings.snap_angle_increment_3d
            snapped_angle = round(self.total_angle / snap_inc) * snap_inc
        else:
            snapped_angle = self.total_angle

        rot_mat = Matrix.Rotation(snapped_angle, 3, self.rotation_axis)
        new_rot_mat = rot_mat @ self.init_rotation.to_matrix()
        self.current_matrix = new_rot_mat

        # Обновляем визуальное вращение во временном режиме XYZ
        context.scene.cursor.rotation_euler = new_rot_mat.to_euler('XYZ')

        self.prev_mouse_pos = current_mouse_pos.copy()

    def _apply_final_rotation(self, context):
        """Применяет финальное вращение и возвращает rotation_mode курсора."""
        cursor = context.scene.cursor

        if self.current_matrix is None:
            self.current_matrix = cursor.rotation_euler.to_matrix()

        # Конвертируем к нужному режиму и устанавливаем
        if self.original_mode == 'QUATERNION':
            cursor.rotation_mode = 'QUATERNION'
            cursor.rotation_quaternion = self.current_matrix.to_quaternion()
        elif self.original_mode == 'AXIS_ANGLE':
            cursor.rotation_mode = 'AXIS_ANGLE'
            quat = self.current_matrix.to_quaternion()
            axis, angle = quat.to_axis_angle()
            cursor.rotation_axis_angle = (angle, axis.x, axis.y, axis.z)
        else:  # Эйлер любого порядка
            cursor.rotation_mode = self.original_mode
            cursor.rotation_euler = self.current_matrix.to_euler(self.original_mode)

    def _restore_original_rotation(self, context):
        """Восстанавливает исходное состояние курсора при отмене."""
        cursor = context.scene.cursor
        cursor.rotation_mode = self.original_mode
        if self.original_mode == 'QUATERNION' and self.orig_quat is not None:
            cursor.rotation_quaternion = self.orig_quat
        elif self.original_mode == 'AXIS_ANGLE' and self.orig_axis_angle is not None:
            cursor.rotation_axis_angle = self.orig_axis_angle
        elif self.orig_euler is not None:
            cursor.rotation_euler = self.orig_euler

    def execute(self, context):
        return {'FINISHED'}


class PIVOTTRANSFORM_GGT_gizmo_cursor(GizmoGroup):
    bl_idname = 'PIVOTTRANSFORM_GGT_gizmo_cursor'
    bl_label = 'Gizmo for 3D Cursor'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        return is_tool_active(context, 'pivot.cursor')

    @classmethod
    def setup_keymap(cls, keyconfig):
        km = keyconfig.keymaps.new(name='3D Cursor PRO: Tweak', space_type='VIEW_3D')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK_DRAG')
        return km

    def setup(self, context):
        color_x = (1, 0.22, 0.24)
        color_y = (0.2, 0.78, 0.35)
        color_z = (0, 0.53, 1)
        color_highlight = (0.0, 0.0, 0.0)
        alpha = 0.8
        alpha_highlight = 1

        # --- ARROW
        self.arrow_x = self.gizmos.new('GIZMO_GT_arrow_3d')
        self.arrow_x.use_tooltip = False
        self.arrow_x.use_draw_offset_scale = True
        self.arrow_x.use_draw_modal = True
        self.arrow_x.color = color_x
        self.arrow_x.color_highlight = color_highlight
        self.arrow_x.alpha = alpha
        self.arrow_x.alpha_highlight = alpha_highlight
        self.ar_x = self.arrow_x.target_set_operator('transform.translate')
        self.ar_x.constraint_axis = (True, False, False)
        self.ar_x.release_confirm = True
        self.ar_x.cursor_transform = True

        self.arrow_y = self.gizmos.new('GIZMO_GT_arrow_3d')
        self.arrow_y.use_tooltip = False
        self.arrow_y.use_draw_offset_scale = True
        self.arrow_y.use_draw_modal = True
        self.arrow_y.color = color_y
        self.arrow_y.color_highlight = color_highlight
        self.arrow_y.alpha = alpha
        self.arrow_y.alpha_highlight = alpha_highlight
        self.ar_y = self.arrow_y.target_set_operator('transform.translate')
        self.ar_y.constraint_axis = (False, True, False)
        self.ar_y.release_confirm = True
        self.ar_y.cursor_transform = True

        self.arrow_z = self.gizmos.new('GIZMO_GT_arrow_3d')
        self.arrow_z.use_tooltip = False
        self.arrow_z.use_draw_offset_scale = True
        self.arrow_z.use_draw_modal = True
        self.arrow_z.color = color_z
        self.arrow_z.color_highlight = color_highlight
        self.arrow_z.alpha = alpha
        self.arrow_z.alpha_highlight = alpha_highlight
        self.ar_z = self.arrow_z.target_set_operator('transform.translate')
        self.ar_z.constraint_axis = (False, False, True)
        self.ar_z.release_confirm = True
        self.ar_z.cursor_transform = True

        # --- DIAL
        self.dial_x = self.gizmos.new('GIZMO_GT_dial_3d')
        self.dial_x.draw_options = {'CLIP'} # 'FILL_SELECT', 'ANGLE_VALUE'
        self.dial_x.color = color_x
        self.dial_x.color_highlight = color_highlight
        self.dial_x.alpha = alpha
        self.dial_x.alpha_highlight = alpha_highlight
        self.dial_x.use_tooltip = False
        self.dial_x.use_draw_value = True
        self.op_dx = self.dial_x.target_set_operator('object.pt_rotate_cursor')
        self.op_dx.axis = 'X'

        self.dial_y = self.gizmos.new('GIZMO_GT_dial_3d')
        self.dial_y.draw_options = {'CLIP'}
        self.dial_y.color = color_y
        self.dial_y.color_highlight = color_highlight
        self.dial_y.alpha = alpha
        self.dial_y.alpha_highlight = alpha_highlight
        self.dial_y.use_tooltip = False
        self.dial_y.use_draw_value = True
        self.op_dy = self.dial_y.target_set_operator('object.pt_rotate_cursor')
        self.op_dy.axis = 'Y'

        self.dial_z = self.gizmos.new('GIZMO_GT_dial_3d')
        self.dial_z.draw_options = {'CLIP'}
        self.dial_z.color = color_z
        self.dial_z.color_highlight = color_highlight
        self.dial_z.alpha = alpha
        self.dial_z.alpha_highlight = alpha_highlight
        self.dial_z.use_tooltip = False
        self.dial_z.use_draw_value = True
        self.op_dz = self.dial_z.target_set_operator('object.pt_rotate_cursor')
        self.op_dz.axis = 'Z'


        # --- DOT
        # self.dot = self.gizmos.new('GIZMO_GT_move_3d')
        # self.dot.use_tooltip = False
        # self.dot.color = (1, 0.22, 0.24)
        # self.dot.color_highlight = color_highlight
        # self.dot.alpha = alpha
        # self.dot.alpha_highlight = alpha_highlight
        # self.dot.draw_options = {'FILL_SELECT', 'ALIGN_VIEW'}
        # self.ar_dot = self.dot.target_set_operator('transform.translate')
        # self.ar_dot.release_confirm = True
        # self.ar_dot.cursor_transform = True

    def invoke_prepare(self, context, gizmo):
        settings = context.scene.pivot_transform
        self.op_dx.coordinate_system = settings.cursor_orient
        self.op_dy.coordinate_system = settings.cursor_orient
        self.op_dz.coordinate_system = settings.cursor_orient

        self.ar_x.orient_type = settings.cursor_orient
        self.ar_y.orient_type = settings.cursor_orient
        self.ar_z.orient_type = settings.cursor_orient

    def draw_prepare(self, context):
        settings = context.scene.pivot_transform
        cursor = context.scene.cursor

        orient = settings.cursor_orient #'GLOBAL' if context.window.scene.transform_orientation_slots[0].type == 'GLOBAL' else 'CURSOR'
        self.ar_x.orient_type = orient
        self.ar_x.orient_matrix_type = orient
        self.ar_y.orient_type = orient
        self.ar_y.orient_matrix_type = orient
        self.ar_z.orient_type = orient
        self.ar_z.orient_matrix_type = orient

        #sizeGizmo = 1
        sizeCursor = 1
        #lwDot = 3

        #coef = 0.2 if sizeCursor > 0.6 else 0.5
        # --- DOT
        # self.dot.scale_basis = sizeCursor * 0.1
        # self.dot.line_width = sizeGizmo * lwDot
        # self.dot.matrix_basis = cursor.matrix.normalized()

        l, r, s  = cursor.matrix.decompose()
        if settings.cursor_orient == 'GLOBAL':
            xR = Quaternion((0.0, 1.0, 0.0), pi/2)
            yR = Quaternion((1.0, 0.0, 0.0), -pi/2)
            zR = Quaternion((0.0, 0.0, 1.0), 0)
            x_matrix_move = Matrix.LocRotScale(l, xR, s).normalized()
            y_matrix_move = Matrix.LocRotScale(l, yR, s).normalized()
            z_matrix_move = Matrix.LocRotScale(l, zR, s).normalized()

            x_matrix_rot = x_matrix_move
            y_matrix_rot = y_matrix_move
            z_matrix_rot = z_matrix_move

        else:
            xR = r @ Quaternion((0.0, 1.0, 0.0), pi/2)
            yR = r @ Quaternion((1.0, 0.0, 0.0), -pi/2)
            zR = r
            x_matrix_move = Matrix.LocRotScale(l, xR, s).normalized()
            y_matrix_move = Matrix.LocRotScale(l, yR, s).normalized()
            z_matrix_move = Matrix.LocRotScale(l, zR, s).normalized()


            x_matrix_rot = Matrix.LocRotScale(l, (r @ Quaternion( (0.0, 1.0, 0.0), pi/2)), s).normalized()
            y_matrix_rot = Matrix.LocRotScale(l, (r @ Quaternion( (1.0, 0.0, 0.0), -pi/2)), s).normalized()
            z_matrix_rot = Matrix.LocRotScale(l, r, s).normalized()

        mo_a = Matrix.Translation(Vector( (0.0, 0.0, 0.6)))

        # --- ARROW
        self.arrow_x.length = 0.3
        self.arrow_x.line_width = sizeCursor * 3
        self.arrow_x.scale_basis = sizeCursor * 1.2
        self.arrow_x.matrix_basis = x_matrix_move
        self.arrow_x.matrix_offset = mo_a

        self.arrow_y.length = 0.3
        self.arrow_y.line_width = sizeCursor * 3
        self.arrow_y.scale_basis = sizeCursor * 1.2
        self.arrow_y.matrix_basis = y_matrix_move
        self.arrow_y.matrix_offset = mo_a

        self.arrow_z.length = 0.3
        self.arrow_z.line_width = sizeCursor * 3
        self.arrow_z.scale_basis = sizeCursor * 1.2
        self.arrow_z.matrix_basis = z_matrix_move
        self.arrow_z.matrix_offset = mo_a

        # --- DIAL
        self.dial_x.scale_basis = sizeCursor * 0.7
        self.dial_x.line_width = sizeCursor * 3
        self.dial_x.matrix_basis = x_matrix_rot

        self.dial_y.scale_basis = sizeCursor * 0.7
        self.dial_y.line_width = sizeCursor * 3
        self.dial_y.matrix_basis = y_matrix_rot

        self.dial_z.scale_basis = sizeCursor * 0.7
        self.dial_z.line_width = sizeCursor * 3
        self.dial_z.matrix_basis = z_matrix_rot


def update_gizmo():
    try:
        bpy.utils.unregister_class(PIVOTTRANSFORM_GGT_cursor_saved_points)
        bpy.utils.register_class(PIVOTTRANSFORM_GGT_cursor_saved_points)
    except Exception as e:
        print("\n[{}]\n{}\n\nError:\n{}".format(__name__, "Updating Gizmo has failed", e))
        pass


class PTG3_store(PropertyGroup):
    position: FloatVectorProperty()
    rotation: FloatVectorProperty()


class PTG3_UL_items(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)

        pos = row.operator('object.pt_cursor_saved_set', text="", icon='ORIENTATION_VIEW')
        pos.index = index
        pos.action = 'POS'

        rot = row.operator('object.pt_cursor_saved_set', text="", icon='ORIENTATION_GIMBAL')
        rot.index = index
        rot.action = 'ROT'

        allAct = row.operator('object.pt_cursor_saved_set', text='All')
        allAct.index = index
        allAct.action = 'ALL'

        layout.prop(item, 'name', text="", emboss=False)


class OBJECT_OT_pt_cursor_saved_set(Operator):
    bl_idname = 'object.pt_cursor_saved_set'
    bl_label = 'Set'
    bl_description = 'Apply a saved 3D cursor transform'
    bl_options= {'REGISTER'}

    index: IntProperty()

    action: EnumProperty(
        name='Axis',
        items=[
            ('POS', 'Set Position', 'Apply only the saved position', '', 0),
            ('ROT', 'Set Rotation', 'Apply only the saved rotation', '', 1),
            ('ALL', 'Set Position & Rotation', 'Apply the saved position and rotation', '', 2)],
        default='ALL',
        )

    def execute(self, context):
        saved_props = context.scene
        # Корректируем индекс на случай, если список изменился после создания гизмо
        col_size = len(saved_props.cursor_transformation_)
        if col_size == 0:
            return {'CANCELLED'}

        real_index = min(self.index, col_size - 1)

        # Сделать текущую трансформацию активной в UI-списке
        saved_props.cursor_Active_Index = real_index

        try:
            point = saved_props.cursor_transformation_[real_index].position
            rotate = saved_props.cursor_transformation_[real_index].rotation

            if self.action in {'POS', 'ALL'}:
                context.scene.cursor.location = point

            if self.action in {'ROT', 'ALL'}:
                context.scene.cursor.rotation_euler = rotate

        except IndexError:
            # Коллекция изменилась быстрее, чем успели обновиться гизмо
            return {'CANCELLED'}
        #update_gizmo()
        return {'FINISHED'}


class OBJECT_OT_pt_cursor_saved_move(Operator):
    bl_idname = 'object.pt_cursor_saved_move'
    bl_label = 'Move'
    bl_description = 'Move the saved 3D cursor item in the list'
    bl_options= {'REGISTER'}

    isUp: BoolProperty()

    def execute(self, context):
        saved_props = context.scene

        idx = saved_props.cursor_Active_Index

        if self.isUp and idx >= 1:
            saved_props.cursor_transformation_.move(idx, idx-1)
            saved_props.cursor_Active_Index -= 1

        if self.isUp==False and idx < len(saved_props.cursor_transformation_) - 1:
            saved_props.cursor_transformation_.move(idx, idx+1)
            saved_props.cursor_Active_Index += 1

        return {'FINISHED'}


class OBJECT_OT_pt_cursor_saved_add(Operator):
    bl_idname = 'object.pt_cursor_saved_add'
    bl_label = 'Add'
    bl_description = 'Save the current 3D cursor transform'
    bl_options= {'REGISTER'}

    def execute(self, context):
        saved_props = context.scene

        point = saved_props.cursor_transformation_.add()
        point.name = "3D Cursor " + str(saved_props.cursor_Active_Index+2)
        point.position = context.scene.cursor.location
        point.rotation = context.scene.cursor.rotation_euler

        saved_props.cursor_Active_Index = len(saved_props.cursor_transformation_)-1

        # Обновляем 3D-вью, чтобы появилось новое гизмо
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        update_gizmo()
        return {'FINISHED'}


class OBJECT_OT_pt_cursor_saved_remove(Operator):
    bl_idname = 'object.pt_cursor_saved_remove'
    bl_label = 'Remove'
    bl_description = 'Remove the selected saved 3D cursor transform'
    bl_options= {'REGISTER', 'UNDO'}

    def execute(self, context):
        saved_props = context.scene

        if len(saved_props.cursor_transformation_) > 0:
            saved_props.cursor_transformation_.remove(saved_props.cursor_Active_Index)

        # Корректируем активный индекс после удаления
        size_after = len(saved_props.cursor_transformation_)
        if size_after == 0:
            saved_props.cursor_Active_Index = -1
        else:
            saved_props.cursor_Active_Index = min(saved_props.cursor_Active_Index, size_after - 1)

        # Обновляем 3D-вью, чтобы убрать гизмо удалённой точки
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        update_gizmo()
        return {'FINISHED'}


class OBJECT_OT_pt_cursor_saved_menu(Operator):
    bl_idname = 'object.pt_cursor_saved_menu'
    bl_label = '3D Cursor Saved Point Menu'
    bl_description = 'Open actions for this saved 3D cursor transform'
    bl_options = {'INTERNAL'}

    index: IntProperty()

    def execute(self, context):
        saved_props = context.scene

        # Ensure index is valid and make the item active in the UI list
        if len(saved_props.cursor_transformation_) == 0:
            return {'CANCELLED'}

        real_index = min(self.index, len(saved_props.cursor_transformation_) - 1)
        saved_props.cursor_Active_Index = real_index

        # Store index for use inside the pie menu
        context.window_manager.ptg3_gizmo_index = real_index

        # Call the pie menu
        bpy.ops.wm.call_menu_pie(name='PTG3_MT_cursor_action_pie')
        return {'FINISHED'}


class PTG3_MT_cursor_action_pie(Menu):
    bl_idname = 'PTG3_MT_cursor_action_pie'
    bl_label = '3D Cursor Actions'

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()

        idx = context.window_manager.ptg3_gizmo_index

        # Set Position
        op = pie.operator('object.pt_cursor_saved_set', text='Position', icon='ORIENTATION_VIEW')
        op.index = idx
        op.action = 'POS'

        # Set Rotation
        op = pie.operator('object.pt_cursor_saved_set', text='Rotation', icon='ORIENTATION_GIMBAL')
        op.index = idx
        op.action = 'ROT'

        # Set Position & Rotation
        op = pie.operator('object.pt_cursor_saved_set', text='Position & Rotation', icon='ORIENTATION_LOCAL')
        op.index = idx
        op.action = 'ALL'

        # Delete Saved Point
        op = pie.operator('object.pt_cursor_saved_remove', text='Delete', icon='TRASH')


class PIVOTTRANSFORM_GT_axis(Gizmo):
    bl_idname = 'PIVOTTRANSFORM_GT_axis'

    __slots__ = (
        'shape_x',
        'shape_y',
        'shape_z',
        'color_x',
        'color_y',
        'color_z',
    )

    def setup(self):
        self.scale_basis = 1
        self.alpha = 0.9
        self.line_width = 3
        self.use_draw_modal = False
        self.hide_select = True

        self.color_x = (1, 0.22, 0.24)
        self.color_y = (0.2, 0.78, 0.35)
        self.color_z = (0, 0.53, 1)

        size = 0.5
        self.shape_x = self.new_custom_shape('LINES', [(0.0, 0.0, 0.0), (size, 0.0, 0.0)])
        self.shape_y = self.new_custom_shape('LINES', [(0.0, 0.0, 0.0), (0.0, size, 0.0)])
        self.shape_z = self.new_custom_shape('LINES', [(0.0, 0.0, 0.0), (0.0, 0.0, size)])

    def draw(self, context):
        state.line_width_set(self.line_width)

        # x
        self.color = self.color_x
        self.draw_custom_shape(self.shape_x)
        # y
        self.color = self.color_y
        self.draw_custom_shape(self.shape_y)
        # z
        self.color = self.color_z
        self.draw_custom_shape(self.shape_z)

        state.line_width_set(1.0)


class PIVOTTRANSFORM_GGT_cursor_saved_points(GizmoGroup):
    bl_idname = 'PIVOTTRANSFORM_GGT_cursor_saved_points'
    bl_label = 'Saved 3D Cursor Points'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        if context.scene.pivot_transform.cursor_save_visible:
            return is_tool_active(context, 'pivot.cursor') and len(context.scene.cursor_transformation_) > 0

    @classmethod
    def setup_keymap(cls, keyconfig):
        km = keyconfig.keymaps.new(name='3D Cursor PRO: Click', space_type='VIEW_3D')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK')
        return km

    def _ensure_gizmo_count(self, context):
        saved = context.scene.cursor_transformation_
        # Удаляем лишние гизмо
        # while len(self.gizmos) > len(saved):
        #     g = self.gizmos[-1]
        #     self.gizmos.remove(g)
        # Добавляем недостающие
        while len(self.gizmos) < len(saved):
            g = self.gizmos.new('PIVOTTRANSFORM_GT_triangle')
            #g.draw_options = {'FILL', 'FILL_SELECT', 'ALIGN_VIEW'}
            #g.draw_style = 'CROSS_2D'
            g.use_tooltip = False
            g.color = (1, 0.22, 0.24)
            g.color_highlight = (0.0, 0.0, 0.0)
            g.alpha = 0.9
            g.alpha_highlight = 1.0
            g.scale_basis = 0.08
            g.line_width = 2
            idx = len(self.gizmos) - 1
            op = g.target_set_operator('object.pt_cursor_saved_menu')
            op.index = idx

    def setup(self, context):
        self._ensure_gizmo_count(context)

        self.axis = self.gizmos.new('PIVOTTRANSFORM_GT_axis')

    def refresh(self, context):
        saved = context.scene.cursor_transformation_
        for idx, (g, item) in enumerate(zip(self.gizmos, saved)):
            # Обновляем оператор (если, например, порядок изменился)
            op = g.target_set_operator('object.pt_cursor_saved_menu')
            op.index = idx
            # Позиция
            loc = Vector(item.position)
            # Ориентация не критична для точки, но добавим её для наглядности
            rot = Euler(item.rotation).to_quaternion()
            g.matrix_basis = Matrix.LocRotScale(loc, rot, Vector((1, 1, 1))).normalized()

    def draw_prepare(self, context):
        highlighted_gizmo = None
        for g in self.gizmos:
            if g.is_highlight:
                highlighted_gizmo = g
                break

        if highlighted_gizmo is not None:
            self.axis.hide = False
            self.axis.matrix_basis = highlighted_gizmo.matrix_basis
        else:
            self.axis.hide = True


class PIVOTTRANSFORM_GGT_cursor_pro_pick(GizmoGroup):
    bl_idname = 'PIVOTTRANSFORM_GGT_cursor_pro_pick'
    bl_label = 'Pick 3D Cursor'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'SHOW_MODAL_ALL', 'VR_REDRAWS'}

    __slots__ = (
        'ray',
        'cl',
        'cq',

    )

    use_pos: BoolProperty(default=True)
    use_orient: BoolProperty(default=True)
    normal_store: FloatVectorProperty(name="Stored Normal", size=3, subtype='XYZ', default=(0.0, 0.0, 1.0))
    cursor_matrix: FloatVectorProperty(size=(4,4), subtype='MATRIX')

    def setup(self, context):
        self.ray = self.gizmos.new('GIZMO_GT_snap_3d')
        self.cl, self.cq, s = context.scene.cursor.matrix.decompose()

    @staticmethod
    def get_object_under_location(context, location, normal):
        result, hit_location, normal, index, object, matrix = context.scene.ray_cast(
            context.view_layer.depsgraph, location+normal, -normal, distance=10.0)
        if result and object.type == 'MESH':
            return object
        return None

    @staticmethod
    def get_snap_location(self, context):
        settings = context.scene.pivot_transform
        index = self.ray.snap_elem_index[2]
        if index != -1 and settings.cursor_face_center:
            obj = self.get_object_under_location(context, self.ray.location, self.ray.normal)
            if obj:
                snap_location = obj.matrix_world @ obj.data.polygons[index].center
            else:
                snap_location = self.ray.location
        else:
            snap_location = self.ray.location
        return snap_location

    def draw_prepare(self, context):
        tool_wrapper = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        props_group = tool_wrapper.gizmo_group_properties('PIVOTTRANSFORM_GGT_cursor_pro_pick')
        use_pos = props_group.use_pos
        use_orient = props_group.use_orient

        cpro_advance_align = True # TODO добавить в настройки
        #snap_location = None
        #if use_pos or (use_pos is False and use_orient is False):
        snap_location = self.get_snap_location(self, context)

        # FIXME не работает
        if use_pos is False and use_orient is False:
            l = context.scene.cursor.location
            if cpro_advance_align:
                q = normal_qat_from_two_point(l, snap_location, Vector(props_group.normal_store), self.ray.normal)
            else:
                n = l - snap_location
                q = n.to_track_quat('-Z', 'X')
        else:
            if use_pos: # shift
                l = snap_location
            else:
                l = self.cl

            if use_orient: # ctrl
                q = self.ray.normal.to_track_quat('Z', 'X')
            else:
                q = self.cq
            props_group.normal_store = self.ray.normal

        props_group.cursor_matrix = Matrix.LocRotScale(l, q, Vector((1,1,1)))


class OBJECT_OT_pt_cursor_pro_pick(Operator):
    bl_idname = 'object.pt_cursor_pro_pick'
    bl_label = "3D Cursor Pick"
    bl_description = 'Pick a snapped 3D cursor transform'
    bl_options = {'REGISTER', 'UNDO'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._snap_copy = False
        self._cursor_mat_copy = Matrix()

    def modal(self, context, event):
        context.scene.tool_settings.use_snap = True

        tool_wrapper = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        gprops = tool_wrapper.gizmo_group_properties('PIVOTTRANSFORM_GGT_cursor_pro_pick')

        #context.area.tag_redraw()
        #print(context.scene.tool_settings.use_snap)
        # Новая логика:
        #   LMB (нет модификаторов)  → позиция + ориентация (оба True)
        #   Shift                     → только ориентация
        #   Ctrl                      → только позиция
        #   Shift + Ctrl              → выравнивание Z-оси (оба False)
        gprops.use_pos = not event.ctrl # FIXME не работает гизмо
        gprops.use_orient = not event.shift
        context.scene.cursor.matrix = gprops.cursor_matrix

        #print(gprops.use_orient)

        if event.value == 'RELEASE' and event.type in {'ESC', 'RIGHTMOUSE'}:
            context.window_manager.gizmo_group_type_unlink_delayed('PIVOTTRANSFORM_GGT_cursor_pro_pick')
            context.area.header_text_set(None)
            context.scene.tool_settings.use_snap = self._snap_copy
            context.scene.cursor.matrix = self._cursor_mat_copy
            return {'CANCELLED'}

        elif event.value == 'RELEASE' and event.type in {'RET', 'LEFTMOUSE'}:
            context.window_manager.gizmo_group_type_unlink_delayed('PIVOTTRANSFORM_GGT_cursor_pro_pick')
            context.area.header_text_set(None)
            context.scene.tool_settings.use_snap = self._snap_copy
            return {'FINISHED'}

        #return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        self._cursor_mat_copy = context.scene.cursor.matrix
        self._snap_copy = context.scene.tool_settings.use_snap

        context.scene.tool_settings.use_snap = True
        context.window_manager.gizmo_group_type_ensure('PIVOTTRANSFORM_GGT_cursor_pro_pick')
        header_text = "Shift: Only Position"
        context.area.header_text_set(text=header_text)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


classes = (
    OBJECT_OT_pt_rotate_cursor,
    PIVOTTRANSFORM_GGT_gizmo_cursor,
    PTG3_store,
    PTG3_UL_items,
    OBJECT_OT_pt_cursor_saved_set,
    OBJECT_OT_pt_cursor_saved_move,
    OBJECT_OT_pt_cursor_saved_add,
    OBJECT_OT_pt_cursor_saved_remove,
    OBJECT_OT_pt_cursor_saved_menu,
    PTG3_MT_cursor_action_pie,
    PIVOTTRANSFORM_GT_axis,
    PIVOTTRANSFORM_GGT_cursor_saved_points,
    PIVOTTRANSFORM_GGT_cursor_pro_pick,
    OBJECT_OT_pt_cursor_pro_pick,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.cursor_transformation_ = CollectionProperty(type=PTG3_store)
    bpy.types.Scene.cursor_Active_Index = IntProperty()

    # Store index passed from gizmo -> pie menu
    bpy.types.WindowManager.ptg3_gizmo_index = IntProperty(default=-1)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.cursor_transformation_
    del bpy.types.Scene.cursor_Active_Index

    del bpy.types.WindowManager.ptg3_gizmo_index
