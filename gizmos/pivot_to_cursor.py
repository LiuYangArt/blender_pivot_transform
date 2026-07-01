import bpy
from bpy.types import GizmoGroup, Operator, Menu
from mathutils import Matrix, Quaternion

from ..ilumetric.tool_utils import is_pivot_tool_active
from ..utils.utils import set_pivot_location, set_pivot_rotation


class OBJECT_OT_pt_copy_from_cursor(Operator):
    """Copy pivot location/rotation from the 3D-cursor to all selected objects"""

    bl_idname = 'object.pt_copy_from_cursor'
    bl_label = 'Copy Pivot From Cursor'
    bl_description = 'Copy the 3D cursor position and/or rotation to selected pivots'
    bl_options = {'REGISTER', 'UNDO'}

    copy_location: bpy.props.BoolProperty(name='Location', default=False)
    copy_rotation: bpy.props.BoolProperty(name='Rotation', default=False)

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return bool(context.selected_objects)

    def execute(self, context: bpy.types.Context):
        cursor = context.scene.cursor

        # --- Save original cursor transform to restore later
        orig_location = cursor.location.copy()
        orig_rot_mode = cursor.rotation_mode
        orig_rot_euler = cursor.rotation_euler.copy()
        orig_rot_quat = cursor.rotation_quaternion.copy()

        try:
            # --- Copy location
            if self.copy_location:
                set_pivot_location(
                    context,
                    location=cursor.location.copy(),
                    undoPush=False,
                )

            # --- Copy rotation
            if self.copy_rotation:
                if cursor.rotation_mode == 'QUATERNION':
                    rot: Quaternion | Matrix = cursor.rotation_quaternion.copy()
                else:
                    rot = cursor.rotation_euler.to_quaternion()
                set_pivot_rotation(
                    context,
                    rotation=rot,
                    undoPush=False,
                )
        finally:
            # --- Always restore original cursor transform
            cursor.location = orig_location
            cursor.rotation_mode = orig_rot_mode
            if orig_rot_mode == 'QUATERNION':
                cursor.rotation_quaternion = orig_rot_quat
            else:
                cursor.rotation_euler = orig_rot_euler

        return {'FINISHED'}


class PIVOTTRANSFORM_MT_cursor_transform_pie(Menu):
    bl_idname = 'PIVOTTRANSFORM_MT_cursor_transform_pie'
    bl_label = 'Copy Pivot From Cursor'

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()

        # Position only
        op = pie.operator('object.pt_copy_from_cursor', text='Position', icon='EMPTY_AXIS')
        op.copy_location = True
        op.copy_rotation = False

        # Rotation only
        op = pie.operator('object.pt_copy_from_cursor', text='Rotation', icon='DRIVER_ROTATIONAL_DIFFERENCE')
        op.copy_location = False
        op.copy_rotation = True

        # Both position & rotation
        op = pie.operator('object.pt_copy_from_cursor', text='Pos & Rot', icon='ORIENTATION_GIMBAL')
        op.copy_location = True
        op.copy_rotation = True


class PIVOTTRANSFORM_GGT_cursor_point(GizmoGroup):
    bl_idname = 'PIVOTTRANSFORM_GGT_cursor_point'
    bl_label = 'Cursor Point'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        return is_pivot_tool_active(context) and context.selected_objects

    @classmethod
    def setup_keymap(cls, keyconfig):
        km = keyconfig.keymaps.new(name='Pivot Transform: Click', space_type='VIEW_3D')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK')
        return km

    def setup(self, context):
        self.cursor = self.gizmos.new('GIZMO_GT_move_3d')
        self.cursor.draw_options = {'FILL', 'FILL_SELECT', 'ALIGN_VIEW'}
        #self.cursor.draw_style = 'CROSS_2D'
        self.cursor.scale_basis = 0.08
        self.cursor.line_width = 3
        self.cursor.use_tooltip = True

        self.cursor.color = (1, 0.22, 0.24)
        self.cursor.color_highlight = (1, 0.38, 0.4)
        self.cursor.alpha = 0.9
        self.cursor.alpha_highlight = 0.99

        self.cursor.matrix_basis = context.scene.cursor.matrix

        op = self.cursor.target_set_operator('wm.call_menu_pie')
        op.name = 'PIVOTTRANSFORM_MT_cursor_transform_pie'

    def refresh(self, context):
        self.cursor.matrix_basis = context.scene.cursor.matrix


_classes = [
    OBJECT_OT_pt_copy_from_cursor,
    PIVOTTRANSFORM_MT_cursor_transform_pie,
    PIVOTTRANSFORM_GGT_cursor_point,
]


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
