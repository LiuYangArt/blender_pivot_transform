import bpy
import rna_keymap_ui
from bpy.types import AddonPreferences, PropertyGroup
from bpy.props import EnumProperty, BoolProperty
from .keymaps import get_hotkey_entry_item


ADDON_PACKAGE = __package__


class PIVOTTRANSFORM_settings(PropertyGroup):
    # tool
    snap_elements: EnumProperty(
        name = 'Snap Element',
        items = [
            ('INCREMENT', 'Increment', 'Snap to transform increments', 'SNAP_INCREMENT', 2),
            ('GRID', 'Grid', 'Snap to grid points', 'SNAP_GRID', 4),
            ('VERTEX', 'Vertex', 'Snap to vertices', 'SNAP_VERTEX', 2**3),
            ('EDGE', 'Edge', 'Snap to edges', 'SNAP_EDGE', 2**4),
            ('FACE', 'Face', 'Snap to faces', 'SNAP_FACE', 2**5),
            ('VOLUME', 'Volume', 'Snap inside volumes', 'SNAP_VOLUME', 2**6),
            ('EDGE_MIDPOINT', 'Edge Midpoint', 'Snap to edge midpoints', 'SNAP_MIDPOINT', 2**7),
            ('EDGE_PERPENDICULAR', 'Edge Perpendicular', 'Snap perpendicular to edges', 'SNAP_PERPENDICULAR', 2**8),
            ('FACE_PROJECT', 'Face Project', 'Project onto faces while snapping', 'SNAP_FACE', 2**9),
            ('FACE_NEAREST', 'Face Nearest', 'Snap to the nearest face point', 'SNAP_FACE_NEAREST', 2**10),
        ],
        description = 'Snap elements used by Pivot Transform tools',
        options = {'ENUM_FLAG'},
        default = {'VERTEX', 'EDGE', 'FACE'},
        )

    target: EnumProperty(
        name="Target",
        description="Choose whether tools affect the active object or all selected objects",
        items=[
            ('ACTIVE', "Active", "Transform only the active object's pivot", 'PIVOT_ACTIVE', 0),
            ('SELECTED', "Selected", "Transform pivots of all selected objects", 'PIVOT_INDIVIDUAL', 1), # PIVOT_MEDIAN
        ],
        default='ACTIVE',
    )

    tool_mode_xform: BoolProperty(name="XForm", default=False)
    # Опции инструмента Pivot Align (оба включены по умолчанию).
    tool_mode_align_axis: BoolProperty(name="Axis Align", default=True)
    tool_mode_bottom: BoolProperty(name="Bottom", default=True)
    tool_mode_save: BoolProperty(name="Save", default=False)

    flow_edge_midpoint: BoolProperty(name="Edge Midpoint", default=True)
    flow_face_center: BoolProperty(name="Face Center", default=True)
    flow_backface_culling: BoolProperty(
        name="Backface Culling",
        description="Hide snap handles on back-facing or occluded geometry",
        default=True,
    )
    flow_use_modifiers: BoolProperty(
        name="Use Modifiers",
        description="Snap to evaluated mesh geometry in Object Mode",
        default=False,
    )

    # Pivot Save
    pivot_save_visible: BoolProperty(name="Visible Saved Points", default=True)
    pivot_save_global: BoolProperty(name="Global Save", default=True)

    # 3D Cursor
    cursor_face_center: BoolProperty(name="Cursor Face Center", default=True)
    cursor_save_visible: BoolProperty(name="Visible Saved Points", default=True)
    cursor_orient: EnumProperty(
        name="Gizmo Orientation",
        items=[
            ("CURSOR", "Cursor", "Use the 3D cursor orientation", 'ORIENTATION_CURSOR', 0),
            ("GLOBAL", "Global", "Use world orientation", 'ORIENTATION_GLOBAL', 1),
            ],
        default='CURSOR',
        )


class PIVOT_transform_preferences(AddonPreferences):
    bl_idname = ADDON_PACKAGE

    # To Bottom
    drop_to_x: BoolProperty(name="Drop To X", default=False)
    drop_to_y: BoolProperty(name="Drop To Y", default=False)
    drop_to_z: BoolProperty(name="Drop To Z", default=False)
    drop_to_active: BoolProperty(name="Drop To Active", default=False)

    TB_mode: EnumProperty(
        name="Mode",
        items=[
            ("LOWEST_CENTER_POINT", "Lowest Median Center Point", "Use the center of the lowest bounding-box side"),
            ("LOWEST_ORIGIN_POINT", "Lowest Origin Point", "Keep origin X/Y and use the lowest geometry Z"),
            ("LOWEST_VERT_POINT", "Lowest Vertex Point", "Use the average position of the lowest vertices"),
            ]
            )

    TB_orient: EnumProperty(
        name="Orientation",
        items=[
            ("WORLD", "World", "Use world axes"),
            ("OBJECT", "Object", "Use object axes"),
            ])

    TB_use_modifier: BoolProperty(name="Use Modifier")
    TB_offset: BoolProperty(name="Offset")

    # To Select
    TS_axis: EnumProperty(
        name='Axis',
        description='Object Mode: choose which coordinates match the active object',
        items=[
            ('X', 'X', 'Match only the X coordinate', '', 0),
            ('Y', 'Y', 'Match only the Y coordinate', '', 1),
            ('Z', 'Z', 'Match only the Z coordinate', '', 2),
            ('ALL', 'All', 'Match all coordinates', '', 3),
        ],
        default='ALL',
    )
    align_to: BoolProperty(name="Align To Normal", default=True)

    def draw(self, context):
        layout = self.layout

        # Keymaps
        layout.label(text="Keymaps", icon='KEYINGSET')
        col = layout.column()
        wm = context.window_manager
        kc = wm.keyconfigs.user or wm.keyconfigs.addon
        km = kc.keymaps.get('3D View') if kc else None
        if km is None:
            col.label(text='No 3D View keymap found')
        else:
            col.label(text='Pie Menu:')
            kmi = get_hotkey_entry_item(km, 'wm.call_menu_pie', 'VIEW3D_MT_pie_pivot', 'name')
            if kmi:
                col.context_pointer_set('keymap', km)
                rna_keymap_ui.draw_kmi([], kc, km, kmi, col, 0)
            else:
                col.label(text='No hotkey entry found')

            col.label(text='Tool:')
            kmi = get_hotkey_entry_item(km, 'wm.tool_set_by_id', 'pivot.transform', 'name')
            if kmi:
                col.context_pointer_set('keymap', km)
                rna_keymap_ui.draw_kmi([], kc, km, kmi, col, 0)
            else:
                col.label(text='No hotkey entry found')

            col.label(text='3D Cursor Tool:')
            kmi = get_hotkey_entry_item(km, 'wm.tool_set_by_id', 'pivot.cursor', 'name')
            if kmi:
                col.context_pointer_set('keymap', km)
                rna_keymap_ui.draw_kmi([], kc, km, kmi, col, 0)
            else:
                col.label(text='No hotkey entry found')

        col.label(text="*Some hotkeys may not work because of the use of other addons!!!")

        layout.separator(type='LINE')

        # Links
        layout.label(text="Links", icon='URL')
        row = layout.row()
        row.operator('wm.url_open', text="Superhive").url = "https://superhivemarket.com/creators/derksen"
        row.operator('wm.url_open', text="Gumroad").url = "https://derksen.gumroad.com"
        row.operator('wm.url_open', text="Artstation").url = "https://artstation.com/derksen"

        col = layout.column()
        col.label(text="Special thanks to TinkerBoi for testing the addon, feedback")
        col.label(text="and help in developing the feature Save Pivot in list.")
        col.operator("wm.url_open", text="TinkerBoi Store").url = "https://blendermarket.com/creators/blenderboi"


    # def get_pie_menu(self, km, operator, menu):
    #     for idx, kmi in enumerate(km.keymap_items):
    #         if km.keymap_items.keys()[idx] == operator:
    #             if km.keymap_items[idx].properties.name == menu:
    #                 return kmi
    #     return None


classes = [
    PIVOTTRANSFORM_settings,
    PIVOT_transform_preferences,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.pivot_transform = bpy.props.PointerProperty(type=PIVOTTRANSFORM_settings)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
