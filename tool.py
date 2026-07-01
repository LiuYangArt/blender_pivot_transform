import os
import bpy
from bpy.types import WorkSpaceTool
from .ilumetric.ui_utils import draw_line_separator


SIDEBAR_LABEL_FACTOR = 0.4


def is_tool_header(layout):
    return layout.direction == 'HORIZONTAL'


def sidebar_properties(layout):
    layout.use_property_split = True
    layout.use_property_decorate = False


def sidebar_control(layout, label, factor=SIDEBAR_LABEL_FACTOR, alignment='EXPAND'):
    """Split row with a right-aligned label on the left, controls on the right.

    Mirrors Blender's own property layout so vertical sidebar entries read as
    "Label   [controls]" instead of stretching edge-to-edge."""
    sidebar_properties(layout)
    split = layout.split(factor=factor, align=True)
    label_row = split.row(align=True)
    label_row.alignment = 'RIGHT'
    label_row.label(text=label)
    row = split.row(align=True)
    row.use_property_split = False
    row.use_property_decorate = False
    row.alignment = alignment
    return row


def _draw_pivot_save_header(layout, settings):
    row = layout.row(align=True)
    row.prop(settings, 'pivot_save_visible', text="", icon='DECORATE_KEYFRAME', toggle=True)
    row.popover(panel='VIEW3D_PT_pt_save', text="Saved List")
    row.prop(settings, 'pivot_save_global', text="", icon='WORLD', toggle=True)
    row = layout.row(align=True)
    row.scale_x = 1.3
    row.operator('object.pt_saved_pivot_add', text="", icon='ADD')


def _draw_pivot_save_sidebar(layout, settings):
    row = layout.row(align=True)
    row.scale_x = 1.3
    row.prop(settings, 'pivot_save_visible', text="", icon='DECORATE_KEYFRAME', toggle=True)
    row.operator('object.pt_saved_pivot_add', text="", icon='ADD')
    row.prop(settings, 'pivot_save_global', text="", icon='WORLD', toggle=True)
    row.popover(panel='VIEW3D_PT_pt_save', text="Saved List")


def _draw_header_common(layout, scene, settings):
    layout.prop(scene.tool_settings, 'use_transform_data_origin', text="Pivot Transform")
    draw_line_separator(layout)
    layout.prop(settings, 'target', expand=True)
    draw_line_separator(layout)


def _draw_sidebar_target(layout, scene, settings):
    layout.prop(scene.tool_settings, 'use_transform_data_origin', text="Pivot Transform")
    sidebar_properties(layout)
    col = layout.column(heading="Target", align=True)
    col.prop(settings, 'target', expand=True)


def draw_flow_settings(context, layout, tool):
    scene = bpy.context.scene
    settings = scene.pivot_transform

    if is_tool_header(layout):
        _draw_header_common(layout, scene, settings)

        flow_row = layout.row(align=True)
        flow_row.label(text='Flow Setting:')
        flow_row.scale_x = 1.3
        flow_row.prop(settings, 'flow_edge_midpoint', text='', icon='SNAP_MIDPOINT', toggle=True)
        flow_row.prop(settings, 'flow_face_center', text='', icon='SNAP_FACE_CENTER', toggle=True)
        flow_row.prop(settings, 'flow_backface_culling', text='', icon='MOD_WIREFRAME', toggle=True)
        flow_row.prop(settings, 'flow_use_modifiers', text='', icon='MODIFIER', toggle=True)
        flow_row.scale_x = 1

        draw_line_separator(layout)
        _draw_pivot_save_header(layout, settings)
        return

    # --- Vertical sidebar layout ---------------------------------------
    _draw_sidebar_target(layout, scene, settings)

    layout.separator()
    col = layout.column(heading="Flow Snapping", align=True)
    col.prop(settings, 'flow_edge_midpoint', text="Edge Midpoint")
    col.prop(settings, 'flow_face_center', text="Face Center")
    col.prop(settings, 'flow_backface_culling', text="Backface Culling")
    col.prop(settings, 'flow_use_modifiers', text="Use Modifiers")

    layout.separator()
    _draw_pivot_save_sidebar(layout, settings)


def draw_bbox_settings(context, layout, tool):
    scene = bpy.context.scene
    settings = scene.pivot_transform

    if is_tool_header(layout):
        _draw_header_common(layout, scene, settings)
        _draw_pivot_save_header(layout, settings)
        return

    # --- Vertical sidebar layout ---------------------------------------
    _draw_sidebar_target(layout, scene, settings)

    layout.separator()
    _draw_pivot_save_sidebar(layout, settings)


def draw_align_settings(context, layout, tool):
    scene = bpy.context.scene
    settings = scene.pivot_transform

    if is_tool_header(layout):
        _draw_header_common(layout, scene, settings)

        row = layout.row(align=True)
        row.prop(settings, 'tool_mode_align_axis', toggle=True)
        row.prop(settings, 'tool_mode_bottom', toggle=True)

        draw_line_separator(layout)
        _draw_pivot_save_header(layout, settings)
        return

    # --- Vertical sidebar layout ---------------------------------------
    _draw_sidebar_target(layout, scene, settings)

    layout.separator()
    col = layout.column(heading="Align", align=True)
    col.prop(settings, 'tool_mode_align_axis', text="Axis Align")
    col.prop(settings, 'tool_mode_bottom', text="Bottom")

    layout.separator()
    _draw_pivot_save_sidebar(layout, settings)


class PIVOTTRANSFORM(WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_idname = 'pivot.transform'
    bl_idname_fallback = 'builtin.select_box'
    bl_label = "Pivot Flow"
    bl_description = "Place the pivot on picked geometry"
    bl_icon = os.path.join(os.path.dirname(__file__), './icons/dat', 'pt.flow')
    bl_keymap = (
        ("object.pt_pivot_drop", {"type": 'LEFTMOUSE', "value": 'CLICK_DRAG'}, None),
    )
    bl_cursor = 'DEFAULT'

    @classmethod
    def draw_settings(cls, context, layout, tool):
        draw_flow_settings(context, layout, tool)


class PIVOTTRANSFORM_Object(PIVOTTRANSFORM):
    bl_context_mode = 'OBJECT'

class PIVOTTRANSFORM_Mesh(PIVOTTRANSFORM):
    bl_context_mode = 'EDIT_MESH'

class PIVOTTRANSFORM_Curve(PIVOTTRANSFORM):
    bl_context_mode = 'EDIT_CURVE'

class PIVOTTRANSFORM_Surface(PIVOTTRANSFORM):
    bl_context_mode = 'EDIT_SURFACE'

class PIVOTTRANSFORM_Armature(PIVOTTRANSFORM):
    bl_context_mode = 'EDIT_ARMATURE'


class PIVOTBBOX(WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_idname = 'pivot.bbox'
    bl_idname_fallback = 'builtin.select_box'
    bl_label = "Pivot BBox"
    bl_description = "Place the pivot on bounding-box points"
    bl_icon = os.path.join(os.path.dirname(__file__), './icons/dat', 'pt.bbox')
    bl_keymap = (
        ("object.pt_pivot_drop", {"type": 'LEFTMOUSE', "value": 'CLICK_DRAG'}, None),
    )
    bl_cursor = 'DEFAULT'

    @classmethod
    def draw_settings(cls, context, layout, tool):
        draw_bbox_settings(context, layout, tool)


class PIVOTBBOX_Object(PIVOTBBOX):
    bl_context_mode = 'OBJECT'

class PIVOTBBOX_Mesh(PIVOTBBOX):
    bl_context_mode = 'EDIT_MESH'

class PIVOTBBOX_Curve(PIVOTBBOX):
    bl_context_mode = 'EDIT_CURVE'

class PIVOTBBOX_Surface(PIVOTBBOX):
    bl_context_mode = 'EDIT_SURFACE'

class PIVOTBBOX_Armature(PIVOTBBOX):
    bl_context_mode = 'EDIT_ARMATURE'

class PIVOTBBOX_Pose(PIVOTBBOX):
    bl_context_mode = 'POSE'

class PIVOTBBOX_Lattice(PIVOTBBOX):
    bl_context_mode = 'EDIT_LATTICE'


class PIVOTALIGN(WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_idname = 'pivot.align'
    bl_idname_fallback = 'builtin.select_box'
    bl_label = "Pivot Align"
    bl_description = "Align the pivot to world axes or bottom points"
    bl_icon = os.path.join(os.path.dirname(__file__), './icons/dat', 'pt.align')
    bl_keymap = (
        ("object.pt_pivot_drop", {"type": 'LEFTMOUSE', "value": 'CLICK_DRAG'}, None),
    )
    bl_cursor = 'DEFAULT'

    @classmethod
    def draw_settings(cls, context, layout, tool):
        draw_align_settings(context, layout, tool)


class PIVOTALIGN_Object(PIVOTALIGN):
    bl_context_mode = 'OBJECT'

class PIVOTALIGN_Mesh(PIVOTALIGN):
    bl_context_mode = 'EDIT_MESH'

class PIVOTALIGN_Curve(PIVOTALIGN):
    bl_context_mode = 'EDIT_CURVE'

class PIVOTALIGN_Surface(PIVOTALIGN):
    bl_context_mode = 'EDIT_SURFACE'

class PIVOTALIGN_Armature(PIVOTALIGN):
    bl_context_mode = 'EDIT_ARMATURE'


def draw_cursor_settings(context, layout, tool):
    settings = context.scene.pivot_transform

    if is_tool_header(layout):
        layout.popover(panel='VIEW3D_PT_view3d_cursor', text="Transform")
        row = layout.row(align=True)
        row.scale_x = 1.3
        row.operator('object.pt_cursor_to_active', text="", icon='RESTRICT_SELECT_OFF')
        row.separator(factor=0.6)
        row.operator('object.pt_align_from_view', text="", icon='RESTRICT_VIEW_OFF')
        row.separator(factor=0.6)
        op = row.operator('object.pt_reset_cursor', text="", icon='EMPTY_ARROWS')
        op.loc = True
        op.rot = False
        op = row.operator('object.pt_reset_cursor', text="", icon='ORIENTATION_GIMBAL')
        op.loc = False
        op.rot = True
        draw_line_separator(layout)

        row = layout.row(align=True)
        row.label(icon='GIZMO')
        row.prop(settings, 'cursor_orient', expand=True)
        layout.prop(settings, 'cursor_face_center', text="Snap Face Center", icon='SNAP_FACE_CENTER', toggle=True)
        draw_line_separator(layout)

        row = layout.row(align=True)
        row.prop(settings, 'cursor_save_visible', text="", icon='DECORATE_KEYFRAME', toggle=True)
        row.popover(panel='VIEW3D_PT_pt_cursor_save', text="Saved List")

        row = layout.row(align=True)
        row.scale_x = 1.3
        row.operator('object.pt_cursor_saved_add', text="", icon='ADD')
        return


    # --- Vertical sidebar layout ---------------------------------------
    layout.popover(panel='VIEW3D_PT_view3d_cursor', text="Cursor Transform", icon='CURSOR')

    layout.separator()

    row = layout.column_flow(columns=4, align=False)
    row.operator('object.pt_cursor_to_active', text="", icon='RESTRICT_SELECT_OFF')
    row.operator('object.pt_align_from_view', text="", icon='RESTRICT_VIEW_ON')
    op = row.operator('object.pt_reset_cursor', text="", icon='EMPTY_ARROWS')
    op.loc = True
    op.rot = False
    op = row.operator('object.pt_reset_cursor', text="", icon='ORIENTATION_GIMBAL')
    op.loc = False
    op.rot = True

    layout.separator()

    sidebar_properties(layout)
    col = layout.column(heading="Orientation", align=True)
    col.prop(settings, 'cursor_orient', expand=True)

    col = layout.column(align=True)
    col.prop(settings, 'cursor_face_center', text="Snap Face Center")

    layout.separator()

    row = layout.row(align=True)
    row.scale_x = 1.3
    row.prop(settings, 'cursor_save_visible', text="", icon='DECORATE_KEYFRAME', toggle=True)
    row.operator('object.pt_cursor_saved_add', text="", icon='ADD')
    row.popover(panel='VIEW3D_PT_pt_cursor_save', text="Saved List")


class CURSORTRANSFORM(WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_idname = 'pivot.cursor'
    bl_idname_fallback = 'builtin.cursor'
    bl_label = "3D Cursor Transform"
    bl_description = "Place and orient the 3D cursor on picked geometry"
    bl_icon = os.path.join(os.path.dirname(__file__), './icons/dat', 'pt.cursor')
    #bl_widget = 'PIVOTTRANSFORM_GGT_ui_widget_cursor'
    bl_keymap = (
        ("object.pt_cursor_pro_pick", {"type": 'LEFTMOUSE', "value": 'CLICK_DRAG'}, None),
    )
    bl_cursor = 'DEFAULT'

    @classmethod
    def draw_settings(cls, context, layout, tool):
        draw_cursor_settings(context, layout, tool)

class PIVOTTRANSFORM_Object_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'OBJECT'

class PIVOTTRANSFORM_Mesh_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'EDIT_MESH'

class PIVOTTRANSFORM_Curve_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'EDIT_CURVE'

class PIVOTTRANSFORM_Surface_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'EDIT_SURFACE'

class PIVOTTRANSFORM_Text_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'EDIT_TEXT'

class PIVOTTRANSFORM_Armature_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'EDIT_ARMATURE'

class PIVOTTRANSFORM_Pose_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'POSE'

class PIVOTTRANSFORM_Metaball_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'EDIT_METABALL'

class PIVOTTRANSFORM_Lattice_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'EDIT_LATTICE'

class PIVOTTRANSFORM_GreasePencil_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'EDIT_GREASE_PENCIL'

class PIVOTTRANSFORM_PointCloud_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'EDIT_POINTCLOUD'

class PIVOTTRANSFORM_Sculpt_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'SCULPT'

class PIVOTTRANSFORM_PaintWeight_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'PAINT_WEIGHT'

class PIVOTTRANSFORM_PaintVertex_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'PAINT_VERTEX'

class PIVOTTRANSFORM_PaintTexture_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'PAINT_TEXTURE'

class PIVOTTRANSFORM_Particle_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'PARTICLE'

# Grease Pencil 2.0 и старые режимы
class PIVOTTRANSFORM_PaintGPencil_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'PAINT_GPENCIL'

class PIVOTTRANSFORM_EditGPencil_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'EDIT_GPENCIL'

class PIVOTTRANSFORM_SculptGPencil_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'SCULPT_GPENCIL'

class PIVOTTRANSFORM_WeightGPencil_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'WEIGHT_GPENCIL'

class PIVOTTRANSFORM_VertexGPencil_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'VERTEX_GPENCIL'

# Grease Pencil 3.0+
class PIVOTTRANSFORM_SculptCurves_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'SCULPT_CURVES'

class PIVOTTRANSFORM_PaintGreasePencil_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'PAINT_GREASE_PENCIL'

class PIVOTTRANSFORM_SculptGreasePencil_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'SCULPT_GREASE_PENCIL'

class PIVOTTRANSFORM_WeightGreasePencil_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'WEIGHT_GREASE_PENCIL'

class PIVOTTRANSFORM_VertexGreasePencil_Cursor(CURSORTRANSFORM):
    bl_context_mode = 'VERTEX_GREASE_PENCIL'

# EDIT_MESH
# EDIT_CURVE
# EDIT_CURVES
# EDIT_SURFACE
# EDIT_TEXT
# EDIT_ARMATURE
# EDIT_METABALL
# EDIT_LATTICE
# EDIT_GREASE_PENCIL
# EDIT_POINTCLOUD
# POSE
# SCULPT
# PAINT_WEIGHT
# PAINT_VERTEX
# PAINT_TEXTURE
# PARTICLE
# PAINT_GPENCIL
# EDIT_GPENCIL
# SCULPT_GPENCIL
# WEIGHT_GPENCIL
# VERTEX_GPENCIL
# SCULPT_CURVES
# PAINT_GREASE_PENCIL
# SCULPT_GREASE_PENCIL
# WEIGHT_GREASE_PENCIL
# VERTEX_GREASE_PENCIL


tools = (
    # Pivot Flow / BBox / Align — три отдельных инструмента в одной группе
    # тулбара (group=True создаёт группу, group=False добавляет в неё). Цикл
    # клавишей D (cycle=True в keymaps.py) проходит по всем трём.
    #
    # 3D Cursor Transform — доступен во всех режимах 3D-вьюпорта. Blender требует
    # отдельный WorkSpaceTool на каждый bl_context_mode. Режимы, отсутствующие в
    # текущей версии Blender (например, Grease Pencil v2 против v3,
    # EDIT_POINTCLOUD/SCULPT_CURVES), отсеиваются при регистрации в __init__.py.
    *(
        {'tool': cls, 'after': {'builtin.select'}, 'separator': False, 'group': True}
        for cls in (
            PIVOTTRANSFORM_Object_Cursor,
            PIVOTTRANSFORM_Mesh_Cursor,
            PIVOTTRANSFORM_Curve_Cursor,
            PIVOTTRANSFORM_Surface_Cursor,
            PIVOTTRANSFORM_Text_Cursor,
            PIVOTTRANSFORM_Armature_Cursor,
            PIVOTTRANSFORM_Pose_Cursor,
            PIVOTTRANSFORM_Metaball_Cursor,
            PIVOTTRANSFORM_Lattice_Cursor,
            PIVOTTRANSFORM_GreasePencil_Cursor,
            PIVOTTRANSFORM_PointCloud_Cursor,
            PIVOTTRANSFORM_Sculpt_Cursor,
            PIVOTTRANSFORM_PaintWeight_Cursor,
            PIVOTTRANSFORM_PaintVertex_Cursor,
            PIVOTTRANSFORM_PaintTexture_Cursor,
            PIVOTTRANSFORM_Particle_Cursor,
            PIVOTTRANSFORM_PaintGPencil_Cursor,
            PIVOTTRANSFORM_EditGPencil_Cursor,
            PIVOTTRANSFORM_SculptGPencil_Cursor,
            PIVOTTRANSFORM_WeightGPencil_Cursor,
            PIVOTTRANSFORM_VertexGPencil_Cursor,
            PIVOTTRANSFORM_SculptCurves_Cursor,
            PIVOTTRANSFORM_PaintGreasePencil_Cursor,
            PIVOTTRANSFORM_SculptGreasePencil_Cursor,
            PIVOTTRANSFORM_WeightGreasePencil_Cursor,
            PIVOTTRANSFORM_VertexGreasePencil_Cursor,
        )
    ),



    {'tool': PIVOTTRANSFORM_Object, 'after': {'builtin.select'} , 'separator': True, 'group': True},
    {'tool': PIVOTTRANSFORM_Mesh, 'after': {'builtin.select'} , 'separator': True, 'group': True},
    {'tool': PIVOTTRANSFORM_Curve, 'after': {'builtin.select'} , 'separator': True, 'group': True},
    {'tool': PIVOTTRANSFORM_Surface, 'after': {'builtin.select'} , 'separator': True, 'group': True},

    # EDIT_ARMATURE: Flow начинает группу (group=True), BBox и Align вступают в
    # неё (group=False + after), чтобы D-cycle проходил по всем трём — как в
    # OBJECT/MESH. Pose и Lattice остаются отдельными BBox-инструментами.
    {'tool': PIVOTTRANSFORM_Armature, 'after': {'builtin.select'} , 'separator': True, 'group': True},

    {'tool': PIVOTBBOX_Object, 'after': {'pivot.transform'} , 'separator': False, 'group': False},
    {'tool': PIVOTBBOX_Mesh, 'after': {'pivot.transform'} , 'separator': False, 'group': False},
    {'tool': PIVOTBBOX_Curve, 'after': {'pivot.transform'} , 'separator': False, 'group': False},
    {'tool': PIVOTBBOX_Surface, 'after': {'pivot.transform'} , 'separator': False, 'group': False},
    {'tool': PIVOTBBOX_Armature, 'after': {'pivot.transform'} , 'separator': False, 'group': False},
    {'tool': PIVOTBBOX_Pose, 'after': {'builtin.select'} , 'separator': True, 'group': False},
    {'tool': PIVOTBBOX_Lattice, 'after': {'builtin.select'} , 'separator': True, 'group': False},

    {'tool': PIVOTALIGN_Object, 'after': {'pivot.bbox'} , 'separator': False, 'group': False},
    {'tool': PIVOTALIGN_Mesh, 'after': {'pivot.bbox'} , 'separator': False, 'group': False},
    {'tool': PIVOTALIGN_Curve, 'after': {'pivot.bbox'} , 'separator': False, 'group': False},
    {'tool': PIVOTALIGN_Surface, 'after': {'pivot.bbox'} , 'separator': False, 'group': False},
    {'tool': PIVOTALIGN_Armature, 'after': {'pivot.bbox'} , 'separator': False, 'group': False},


)
