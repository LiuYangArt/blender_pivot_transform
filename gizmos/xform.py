import bpy
from bpy.types import Operator, GizmoGroup
from bpy.props import FloatVectorProperty
from ..ilumetric.tool_utils import is_tool_active
from ..utils.matrix import get_matrix


class OBJECT_OT_pt_placement_move(Operator):
    bl_idname = 'object.pt_placement_move'
    bl_label = 'Placement'
    bl_description = 'Move the pivot across faces with snapping'

    orient_matrix: FloatVectorProperty(size=(3, 3), subtype='MATRIX')
    center_override: FloatVectorProperty(size=3, default=[0, 0, 0])

    def execute(self, context):
        # bpy.ops.transform.transform(
        #     'INVOKE_DEFAULT',
        #     mode = 'TRANSLATION',
        #     release_confirm = True,
        #     orient_matrix = self.orient_matrix,
        #     center_override = self.center_override,
        #     snap = True,
        #     snap_target = 'CENTER',
        #     snap_align = True,
        #     snap_elements = {'FACE'},
        # )

        bpy.ops.transform.translate(
            'INVOKE_DEFAULT',
            release_confirm = True,
            orient_matrix = self.orient_matrix,
            #center_override = self.center_override,
            snap = True,
            snap_target = 'CENTER',
            snap_align = True,
            snap_elements = {'FACE'},
            translate_origin = True,
        )
        return {'FINISHED'}


class PIVOTTRANSFORM_GGT_xform(GizmoGroup):
    bl_idname = 'PIVOTTRANSFORM_GGT_xform'
    bl_label = 'XForm'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        if is_tool_active(context, 'pivot.transform') and context.scene.pivot_transform.tool_mode_xform:
            return context.active_object or context.selected_objects

    @classmethod
    def setup_keymap(cls, keyconfig):
        km = keyconfig.keymaps.new(name='Pivot Transform: Tweak', space_type='VIEW_3D')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK_DRAG')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK_DRAG', ctrl=True)
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK_DRAG', shift=True)
        #km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK_DRAG', ctrl=True, shift=True)
        return km

    def setup(self, context):
        # # rotate
        # self.dial = self.gizmos.new('GP_GT_blank')
        # self.dial.set_shape(size=0.27, n=1)
        # self.dial.offset = 0.7
        # self.dial.draw_options = set()
        # self.dial.use_tooltip = False
        # self.dial.color = (0.2, 0.78, 0.35)
        # self.dial_op = self.dial.target_set_operator('transform.rotate')
        # self.dial_op.release_confirm = True
        # self.dial_op.constraint_axis = (False, False, True)
        # self.dial_op.snap = False
        # self.dial_op.orient_axis = 'Z'
        # self.dial_op.orient_type = 'NORMAL'

        # # scale
        # self.scale = self.gizmos.new('GP_GT_point')
        # self.scale.set_shape(size=0.12, n=4.5, segments=4, axis='Y', rotation=45)
        # self.scale.use_draw_offset_scale = True
        # self.scale.color = (0, 0.48, 1)
        # self.scale.offset = 1.55
        # self.scale.use_tooltip = False
        # self.scale.draw_options = {'BILLBOARD'}
        # self.scale_op = self.scale.target_set_operator('transform.resize')
        # self.scale_op.release_confirm = True
        # self.scale_op.constraint_axis = (False, False, True)
        # self.scale_op.orient_type = 'LOCAL'

        # # move
        # self.arrow = self.gizmos.new('GP_GT_arrow')
        # self.arrow.length = 0.4
        # self.arrow.offset = 1
        # self.arrow.set_shape(height=0.2, radius=0.1, segments=16)
        # self.arrow.use_draw_offset_scale = True
        # self.arrow.draw_options = set()
        # self.arrow.color = (0, 0.48, 1)
        # self.arrow.use_tooltip = True
        # self.arrow_op = self.arrow.target_set_operator('gp.placement_move_z')

        # dot
        self.dot = self.gizmos.new('GIZMO_GT_move_3d')
        self.dot.draw_options = {'FILL_SELECT'}
        self.dot.use_tooltip = True
        self.dot.color = (1, 0.8, 0)
        #self.dot.use_select_background = True
        self.dot.select_bias = 100
        self.dot_op = self.dot.target_set_operator('object.pt_placement_move')

        #self.dot.target_set_prop('scale_basis', self, 'size')



    def invoke_prepare(self, context, gizmo):
        orient_matrix = gizmo.matrix_basis.copy().to_3x3()
        pos = gizmo.matrix_basis.translation.copy()
        #self.arrow_op.orient_matrix = matrix
        #self.arrow_op.center_override = pos
        #self.scale_op.orient_matrix = matrix
        #self.scale_op.center_override = pos
        #self.dial_op.orient_matrix = matrix
        #self.dial_op.center_override = pos
        self.dot_op.orient_matrix = orient_matrix
        self.dot_op.center_override = pos

    def refresh(self, context):
        mX, mY, mZ = get_matrix(context, orient='LOCAL')
        self.dot.matrix_basis = mZ
        # self.arrow.matrix_basis = matrix
        # self.dial.matrix_basis = matrix @ Matrix.Rotation(pi/4, 4, 'Z')
        # self.scale.matrix_basis = matrix

        #var.REFRESH_MAT = False

    def draw_prepare(self, context):
        #settings = context.scene.pivot_transform
        ui_scale = context.preferences.system.ui_scale

        coef = 1
        size_gizmo = 1

        # l_size_a = size_gizmo * coef
        # l_size_d = size_gizmo * 0.8 * coef
        l_dot_size = size_gizmo * 0.2 * coef
        lw = size_gizmo * 3.0 * ui_scale

        # принудительное обновление матрицы
        orient_slots = context.window.scene.transform_orientation_slots[0].type
        if orient_slots=='VIEW':
            self.refresh(context)

        for g in self.gizmos:
            g.color_highlight = (0.78, 0.78, 0.8)
            g.alpha = 0.7
            g.alpha_highlight = 0.9

        # # move
        # self.arrow.line_width = lw
        # self.arrow.alpha = props.alpha_gizmo
        # self.arrow.alpha_highlight = props.highlight_alpha_gizmo
        # self.arrow.scale_basis = l_size_a
        # self.arrow.color_highlight = props.select_color

        # # rotate
        # self.dial.line_width = lw
        # self.dial.alpha = props.alpha_gizmo
        # self.dial.alpha_highlight = props.highlight_alpha_gizmo
        # self.dial.scale_basis = l_size_d
        # self.dial.color_highlight = props.select_color

        # # scale
        # self.scale.line_width = lw
        # self.scale.alpha = props.alpha_gizmo
        # self.scale.alpha_highlight = props.highlight_alpha_gizmo
        # self.scale.scale_basis = l_size_a
        # self.scale.color_highlight = props.select_color

        # dot
        #self.dot.color_highlight = props.select_color
        #self.dot.alpha = props.alpha_gizmo
        #self.dot.alpha_highlight = props.highlight_alpha_gizmo
        self.dot.line_width = lw
        self.dot.scale_basis = l_dot_size


classes = [
    OBJECT_OT_pt_placement_move,
    PIVOTTRANSFORM_GGT_xform,
    ]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
