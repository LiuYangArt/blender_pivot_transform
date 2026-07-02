import bpy
from bpy.types import GizmoGroup
from mathutils import Matrix, Vector, Quaternion
from math import pi


class PIVOTTRANSFORM_GGT_object_pivot_transform(GizmoGroup):
    bl_idname = 'PIVOTTRANSFORM_GGT_object_pivot_transform'
    bl_label = 'Object Pivot Transform Gizmo'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        return bool(getattr(context.scene, 'pt_object_pivot_transform_active', False)) and context.mode == 'OBJECT' and context.active_object is not None

    @classmethod
    def setup_keymap(cls, keyconfig):
        km = keyconfig.keymaps.new(name='Object Pivot Transform: Tweak', space_type='VIEW_3D')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK_DRAG')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK_DRAG', ctrl=True)
        return km

    def setup(self, context):
        color_x = (1, 0.22, 0.24)
        color_y = (0.2, 0.78, 0.35)
        color_z = (0, 0.53, 1)
        color_highlight = (0.0, 0.0, 0.0)
        alpha = 0.8
        alpha_highlight = 1.0

        self.arrow_x = self._new_arrow(color_x, color_highlight, alpha, alpha_highlight)
        self.op_x = self.arrow_x.target_set_operator('object.pt_object_pivot_transform_drag')
        self.op_x.axis = 'X'

        self.arrow_y = self._new_arrow(color_y, color_highlight, alpha, alpha_highlight)
        self.op_y = self.arrow_y.target_set_operator('object.pt_object_pivot_transform_drag')
        self.op_y.axis = 'Y'

        self.arrow_z = self._new_arrow(color_z, color_highlight, alpha, alpha_highlight)
        self.op_z = self.arrow_z.target_set_operator('object.pt_object_pivot_transform_drag')
        self.op_z.axis = 'Z'

    def _new_arrow(self, color, color_highlight, alpha, alpha_highlight):
        arrow = self.gizmos.new('GIZMO_GT_arrow_3d')
        arrow.use_tooltip = True
        arrow.use_draw_offset_scale = True
        arrow.use_draw_modal = True
        arrow.color = color
        arrow.color_highlight = color_highlight
        arrow.alpha = alpha
        arrow.alpha_highlight = alpha_highlight
        return arrow

    def invoke_prepare(self, context, gizmo):
        settings = context.scene.pivot_transform
        self.op_x.orientation = settings.cursor_orient
        self.op_y.orientation = settings.cursor_orient
        self.op_z.orientation = settings.cursor_orient

    def draw_prepare(self, context):
        settings = context.scene.pivot_transform
        obj = context.active_object
        if obj is None:
            return
        loc, rot, _scale = obj.matrix_world.decompose()
        scale = Vector((1.0, 1.0, 1.0))

        if settings.cursor_orient == 'GLOBAL':
            x_rot = Quaternion((0.0, 1.0, 0.0), pi / 2)
            y_rot = Quaternion((1.0, 0.0, 0.0), -pi / 2)
            z_rot = Quaternion((0.0, 0.0, 1.0), 0)
        else:
            x_rot = rot @ Quaternion((0.0, 1.0, 0.0), pi / 2)
            y_rot = rot @ Quaternion((1.0, 0.0, 0.0), -pi / 2)
            z_rot = rot

        offset = Matrix.Translation(Vector((0.0, 0.0, 0.6)))
        self._prepare_arrow(self.arrow_x, Matrix.LocRotScale(loc, x_rot, scale).normalized(), offset)
        self._prepare_arrow(self.arrow_y, Matrix.LocRotScale(loc, y_rot, scale).normalized(), offset)
        self._prepare_arrow(self.arrow_z, Matrix.LocRotScale(loc, z_rot, scale).normalized(), offset)

    def _prepare_arrow(self, arrow, matrix, offset):
        arrow.length = 0.3
        arrow.line_width = 3
        arrow.scale_basis = 1.2
        arrow.matrix_basis = matrix
        arrow.matrix_offset = offset


classes = [PIVOTTRANSFORM_GGT_object_pivot_transform]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
