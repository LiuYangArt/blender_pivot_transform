import bpy
from bpy.types import Panel, Menu
from .ilumetric.tool_utils import is_pivot_tool_active
from .preferences import ADDON_PACKAGE


def _draw_to_bottom_options(layout, props):
    row = layout.row(align=True)
    row.label(text="Drop To")
    row.prop(props, 'drop_to_x', text='X', toggle=True)
    row.prop(props, 'drop_to_y', text='Y', toggle=True)
    row.prop(props, 'drop_to_z', text='Z', toggle=True)
    layout.prop(props, 'TB_mode')
    layout.prop(props, 'TB_use_modifier')
    layout.prop(props, 'drop_to_active')


def _assign_to_bottom_options(op, props):
    op.drop_to_x = props.drop_to_x
    op.drop_to_y = props.drop_to_y
    op.drop_to_z = props.drop_to_z
    op.mode = props.TB_mode
    op.use_modifier = props.TB_use_modifier
    op.drop_to_active = props.drop_to_active
    return op


def _draw_to_select_options(layout, props, context):
    if context.mode == 'OBJECT':
        layout.prop(props, 'TS_axis', expand=True)
        layout.prop(props, 'align_to', text="Align Orientation")
    else:
        layout.prop(props, 'align_to', text="Align To Normal")


def _assign_to_select_options(op, props, context):
    if context.mode == 'OBJECT':
        op.axis = props.TS_axis
    op.align = props.align_to
    return op


class VIEW3D_PT_pt_cursor_save(Panel):
    bl_label = 'Cursor Save'
    bl_idname = 'VIEW3D_PT_pt_cursor_save'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = 'VIEW3D_PT_pivot_transform'
    bl_options = {'DEFAULT_CLOSED'}
    bl_ui_units_x = 12

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        saved_props = scene.cursor_transformation_
        active_index = scene.cursor_Active_Index
        if len(saved_props) > 0:
            row = layout.row()
            row.template_list('PTG3_UL_items', '', scene, 'cursor_transformation_', scene, 'cursor_Active_Index')
            col = row.column(align=True)
            col.operator('object.pt_cursor_saved_add', text="", icon='ADD')
            col.operator('object.pt_cursor_saved_remove', text="", icon='REMOVE')
            col.separator()
            col.operator('object.pt_cursor_saved_move', text="", icon='TRIA_UP').isUp = True
            col.operator('object.pt_cursor_saved_move', text="", icon='TRIA_DOWN').isUp = False
            # данные позиции и вращения
            col = layout.column(align=True )
            row = col.row(align=True )
            row.label(icon='ORIENTATION_VIEW')
            row.prop(saved_props[active_index], 'position', text="")

            row = col.row(align=True)
            row.label(icon='ORIENTATION_GIMBAL')
            row.prop(saved_props[active_index], 'rotation', text="")
        else:
            layout.operator('object.pt_cursor_saved_add', text="Save Cursor", icon='FILE_TICK')


class VIEW3D_PT_pt_to_bottom_options(Panel):
    bl_label = 'To Bottom'
    bl_idname = 'VIEW3D_PT_pt_to_bottom_options'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_options = {'HIDE_HEADER'}
    bl_ui_units_x = 12

    def draw(self, context):
        props = context.preferences.addons[ADDON_PACKAGE].preferences
        _draw_to_bottom_options(self.layout, props)


class VIEW3D_PT_pt_to_select_options(Panel):
    bl_label = 'To Select'
    bl_idname = 'VIEW3D_PT_pt_to_select_options'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_options = {'HIDE_HEADER'}
    bl_ui_units_x = 12

    def draw(self, context):
        props = context.preferences.addons[ADDON_PACKAGE].preferences
        _draw_to_select_options(self.layout, props, context)


class VIEW3D_PT_pt_save(Panel):
    bl_idname = 'VIEW3D_PT_pt_save'
    bl_label = 'Pivot Save'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = 'VIEW3D_PT_pivot_transform'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.pivot_transform
        if settings.pivot_save_global:
            saved_props = context.scene
        else:
            saved_props = context.object

        if len(saved_props.pivots_) > 0:
            row = layout.row()
            row.template_list('PIVOTTRANSFORM_UL_items', '', saved_props, 'pivots_', saved_props, 'pivots_Active_Index')

            col = row.column( align = True )
            col.operator('object.pt_saved_pivot_add', text="", icon='ADD')
            col.operator('object.pt_saved_pivot_remove', text="", icon='REMOVE')
            col.separator()
            col.operator('object.pt_saved_pivot_move', text="", icon='TRIA_UP').isUp = True
            col.operator('object.pt_saved_pivot_move', text="", icon='TRIA_DOWN').isUp = False
            col.separator()
            col.prop(settings, 'pivot_save_global', text="", icon='WORLD')

            # данные позиции и вращения
            col = layout.column( align = True )
            row = col.row( align = True )
            row.label(icon='ORIENTATION_VIEW')
            row.prop(saved_props.pivots_[saved_props.pivots_Active_Index], 'position', text="")

            row = col.row( align = True )
            row.label(icon='ORIENTATION_GIMBAL')
            row.prop(saved_props.pivots_[saved_props.pivots_Active_Index], 'rotation', text="")

        else:
            row = layout.row()
            row.operator('object.pt_saved_pivot_add', text="Save Pivot", icon='FILE_TICK')
            row.prop(settings, 'pivot_save_global', text="", icon='WORLD')


class VIEW3D_PT_pt_apply(Panel):
    bl_label = 'Apply'
    bl_idname = 'VIEW3D_PT_pt_apply'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = 'VIEW3D_PT_pivot_transform'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        row = layout.column_flow(columns=3, align=False)
        op = row.operator('object.pt_transform_apply', text="", icon='ORIENTATION_VIEW')
        op.location = True
        op.rotation = False
        op.scale = False
        op.corrective_flip_normals = True
        op = row.operator('object.pt_transform_apply', text="", icon='ORIENTATION_GIMBAL')
        op.location = False
        op.rotation = True
        op.scale = False
        op.corrective_flip_normals = True
        op = row.operator('object.pt_transform_apply', text="", icon='FULLSCREEN_ENTER')
        op.location = False
        op.rotation = False
        op.scale = True
        op.corrective_flip_normals = True

        op = layout.operator('object.pt_transform_apply', text="Apply All Transform")
        op.location = True
        op.rotation = True
        op.scale = True
        op.apply_delta = True
        op.corrective_flip_normals = True

        row = layout.row(align=True)
        op = row.operator('object.pt_transform_apply', text="Rotation & Scale")
        op.location = False
        op.rotation = True
        op.scale = True
        op.corrective_flip_normals = True


class VIEW3D_PT_pivot_transform(Panel):
    bl_label = ' '
    bl_idname = 'VIEW3D_PT_pivot_transform'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Pivot Transform'

    @classmethod
    def poll(self, context):
        mesh_type = {'MESH', 'CURVE', 'SURFACE', 'META', 'ARMATURE', 'LATTICE', 'GPENCIL', 'EMPTY'}
        return context.active_object and context.object.type in mesh_type

    def draw_header(self, context):
        layout = self.layout
        layout.prop(context.scene.tool_settings, 'use_transform_data_origin', text="Pivot Transform")

    def draw_header_preset(self, context):
        layout = self.layout
        sub = layout.row(align=True)
        sub.scale_x = 1.2
        sub.operator('object.pt_open_preferences', text='', icon='PREFERENCES')
        sub.operator('object.pt_open_documentation', text='', icon='HELP')
        sub.separator()

    def draw(self, context):
        props = context.preferences.addons[ADDON_PACKAGE].preferences

        layout = self.layout

        if context.mode == 'OBJECT':
            row = layout.column_flow(columns=2, align=False)
            to_select = row.row(align=True)
            op = to_select.operator('object.pt_pivot_to_select', text="To Active", icon='POINTCLOUD_POINT')
            _assign_to_select_options(op, props, context)
            to_select.popover(panel='VIEW3D_PT_pt_to_select_options', text="", icon='DOWNARROW_HLT')
            to_bottom = row.row(align=True)
            op = to_bottom.operator('object.pt_pivot_to_bottom', text="To Bottom", icon='IMPORT')
            _assign_to_bottom_options(op, props)
            to_bottom.popover(panel='VIEW3D_PT_pt_to_bottom_options', text="", icon='DOWNARROW_HLT', direction='HORIZONTAL')

            row = layout.column_flow(columns=3, align=False)
            row.operator('object.pt_origin_set', text="", icon='PIVOT_CURSOR').type = 'ORIGIN_CURSOR' # To 3D Cursor
            row.operator('object.pt_origin_set', text="", icon='LIGHTPROBE_SPHERE').type = 'ORIGIN_CENTER_OF_MASS'
            row.operator('object.pt_origin_set', text="", icon='PIVOT_ACTIVE').type = 'GEOMETRY_ORIGIN'

        else:
            row = layout.column_flow(columns=2, align=False)
            to_select = row.row(align=True)
            op = to_select.operator('object.pt_pivot_to_select', text="To Select", icon='RESTRICT_SELECT_OFF')
            _assign_to_select_options(op, props, context)
            to_select.popover(panel='VIEW3D_PT_pt_to_select_options', text="", icon='DOWNARROW_HLT', direction='HORIZONTAL')
            row.operator('object.pt_origin_set', text="", icon='PIVOT_ACTIVE').type = 'GEOMETRY_ORIGIN'

        # 3D Cursor Ops
        layout.separator(type='LINE')
        row = layout.column_flow(columns=4, align=False)
        row.operator('object.pt_cursor_to_active', text="", icon='RESTRICT_SELECT_OFF')
        row.operator('object.pt_align_from_view', text="", icon='RESTRICT_VIEW_ON')
        op = row.operator('object.pt_reset_cursor', text="", icon='EMPTY_ARROWS')
        op.loc = True
        op.rot = False
        op = row.operator('object.pt_reset_cursor', text="", icon='ORIENTATION_GIMBAL')
        op.loc = False
        op.rot = True


class VIEW3D_MT_pie_pivot(Menu):
    bl_idname = 'VIEW3D_MT_pie_pivot'
    bl_label = 'Pie Menu'

    @classmethod
    def poll(cls, context):
        mesh_type = {'MESH', 'CURVE', 'SURFACE', 'META', 'ARMATURE', 'LATTICE', 'GPENCIL', 'EMPTY'}
        return context.active_object and context.object.type in mesh_type

    def draw(self, context):
        props = context.preferences.addons[ADDON_PACKAGE].preferences

        layout = self.layout

        pie = layout.menu_pie()

        #1
        if context.mode == 'OBJECT':
            to_select = pie.row(align=True)
            to_select.emboss = 'PIE_MENU'
            to_select.scale_x = 1.1
            to_select.scale_y = 1.5
            to_select.popover(panel='VIEW3D_PT_pt_to_select_options', text="", icon='DOWNARROW_HLT')
            op = to_select.operator('object.pt_pivot_to_select', text='To Active', icon='POINTCLOUD_POINT')
            _assign_to_select_options(op, props, context)

        elif context.object.type in {'MESH', 'ARMATURE', 'CURVE'}:
            to_select = pie.row(align=True)
            to_select.emboss = 'PIE_MENU'
            to_select.scale_x = 1.1
            to_select.scale_y = 1.5
            to_select.popover(panel='VIEW3D_PT_pt_to_select_options', text="", icon='DOWNARROW_HLT')
            op = to_select.operator('object.pt_pivot_to_select', text='To Select', icon='RESTRICT_SELECT_OFF')
            _assign_to_select_options(op, props, context)

        else:
            pie.separator()

        #2
        if context.mode == 'OBJECT':
            col = pie.column(align=True)
            col.scale_x = 0.9
            col.scale_y = 1.2

            box = col.box()
            box.operator('object.pt_origin_set', text='Pivot To 3d Cursor', icon='PIVOT_CURSOR').type = 'ORIGIN_CURSOR'
            box.operator('object.pt_origin_set', text='Mesh To Pivot', icon='PIVOT_ACTIVE').type = 'GEOMETRY_ORIGIN'
            row = box.row()
            row.label(icon='LIGHTPROBE_SPHERE')
            row.operator('object.pt_origin_set', text='Mesh').type = 'ORIGIN_GEOMETRY'
            row.operator('object.pt_origin_set', text='Mass').type = 'ORIGIN_CENTER_OF_MASS'
            row.operator('object.pt_origin_set', text='Volume').type = 'ORIGIN_CENTER_OF_VOLUME'

            box = col.box()
            box.popover(panel='VIEW3D_PT_pt_save', icon='FILE_TICK')
            box.popover(panel='VIEW3D_PT_pt_cursor_save', icon='FILE_TICK')
        else:
            pie.operator('object.pt_origin_set', text='Mesh To Pivot', icon='PIVOT_ACTIVE').type = 'GEOMETRY_ORIGIN'

        #3
        if context.object.type in {'MESH', 'ARMATURE', 'CURVE'}:
            to_bottom = pie.row(align=True)
            to_bottom.emboss = 'PIE_MENU'
            to_bottom.scale_x = 1.1
            to_bottom.scale_y = 1.5
            op = to_bottom.operator('object.pt_pivot_to_bottom', text='To Bottom', icon='IMPORT')
            _assign_to_bottom_options(op, props)
            to_bottom.popover(panel='VIEW3D_PT_pt_to_bottom_options', text="", icon='DOWNARROW_HLT', direction='HORIZONTAL')
        else:
            pie.separator()

        #4
        box = pie.box()
        box.scale_x = 1.2
        box.scale_y = 1.3

        row = box.column_flow(columns=3, align=False)
        op = row.operator('object.pt_transform_apply', text="", icon='ORIENTATION_VIEW')
        op.location = True
        op.rotation = False
        op.scale = False
        op.corrective_flip_normals = True
        op = row.operator('object.pt_transform_apply', text="", icon='ORIENTATION_GIMBAL')
        op.location = False
        op.rotation = True
        op.scale = False
        op.corrective_flip_normals = True
        op = row.operator('object.pt_transform_apply', text="", icon='FULLSCREEN_ENTER')
        op.location = False
        op.rotation = False
        op.scale = True
        op.corrective_flip_normals = True

        op = box.operator('object.pt_transform_apply', text='Apply All Transform')
        op.location = True
        op.rotation = True
        op.scale = True
        op.apply_delta = True
        op.corrective_flip_normals = True

        row = box.row(align=True)
        op = row.operator('object.pt_transform_apply', text='Rotation & Scale')
        op.location = False
        op.rotation = True
        op.scale = True
        op.corrective_flip_normals = True

        #5
        # 3D Cursor Ops
        cursor_row = pie.column_flow(columns=4, align=True)
        cursor_row.emboss = 'PIE_MENU'
        cursor_row.scale_x = 1.5
        cursor_row.scale_y = 1.5
        cursor_row.operator('object.pt_cursor_to_active', text="", icon='RESTRICT_SELECT_OFF')
        cursor_row.operator('object.pt_align_from_view', text="", icon='RESTRICT_VIEW_ON')
        op = cursor_row.operator('object.pt_reset_cursor', text="", icon='EMPTY_ARROWS')
        op.loc = True
        op.rot = False
        op = cursor_row.operator('object.pt_reset_cursor', text="", icon='ORIENTATION_GIMBAL')
        op.loc = False
        op.rot = True

        #6
        pie.separator()

        #7
        pie.separator()

        #8
        pie.separator()


def draw_apply(self, context):
    layout = self.layout
    layout.separator()
    if context.scene.tool_settings.use_transform_data_origin and not is_pivot_tool_active(context):
        layout.prop(context.scene.tool_settings, 'use_transform_data_origin', text='Apply Pivot Transform',  icon='CHECKMARK')


classes = [
    VIEW3D_PT_pt_to_bottom_options,
    VIEW3D_PT_pt_to_select_options,
    VIEW3D_PT_pivot_transform,
    VIEW3D_PT_pt_apply,
    VIEW3D_PT_pt_save,
    VIEW3D_PT_pt_cursor_save,
    VIEW3D_MT_pie_pivot,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.VIEW3D_MT_editor_menus.append(draw_apply)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.types.VIEW3D_MT_editor_menus.remove(draw_apply)
