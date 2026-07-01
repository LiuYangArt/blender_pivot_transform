import bpy
from bpy.types import GizmoGroup
from ..ilumetric.tool_utils import is_tool_active


def viewport_points(context):
    use_tool_header = context.space_data.show_region_tool_header

    if use_tool_header:
        header_height = context.area.regions[0].height * 2
    else:
        header_height = context.area.regions[0].height

    wl = context.area.regions[4].width
    ht = context.area.height - header_height
    hb = 0
    wr = context.area.width - context.area.regions[5].width

    wc = (wl + wr) / 2
    hc = (hb + ht) / 2

    return wl, wr, hb, ht, wc, hc


class PIVOTTRANSFORM_GGT_ui_widget(GizmoGroup):
    bl_idname = 'PIVOTTRANSFORM_GGT_ui_widget'
    bl_label = 'UI Widget'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'SCALE', 'SHOW_MODAL_ALL'}

    @classmethod
    def setup_keymap(cls, keyconfig):
        km = keyconfig.keymaps.new(name='Pivot Transform: Click', space_type='VIEW_3D')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK')
        return km

    @classmethod
    def poll(cls, context):
        return is_tool_active(context, 'pivot.transform') and context.selected_objects

    def setup(self, context):
        # shape = bytes([
        #     0x73, 0x73, 0x73, 0x36, 0x8C, 0x36, 0x8C, 0x73,
        #     0xC9, 0x73, 0xC9, 0x8C, 0x8C, 0x8C, 0x8C, 0xC9,
        #     0x73, 0xC9, 0x73, 0x8C, 0x36, 0x8C, 0x36, 0x73,
        #     0x36, 0x73,
        # ])
        #self.center.shape = shape
        line_width = 3
        alpha = 1
        backdrop_fill_alpha = 0.8
        color = (0.11, 0.11, 0.12)
        color_highlight = (0.23, 0.23, 0.24)

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'} # , 'HELPLINE'
        g.icon = 'RESTRICT_SELECT_OFF'
        g.target_set_operator('object.pt_pivot_to_select')

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'}
        g.icon = 'LIGHTPROBE_SPHERE'
        op = g.target_set_operator('object.pt_origin_set')
        op.type = 'ORIGIN_GEOMETRY'
        op.center = 'MEDIAN'

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'}
        g.icon = 'PIVOT_CURSOR'
        op = g.target_set_operator('object.pt_origin_set')
        op.type = 'ORIGIN_CURSOR'
        op.center = 'MEDIAN'

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'}
        g.icon = 'IMPORT'
        op = g.target_set_operator('object.pt_pivot_to_bottom')

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = set()
        g.icon = 'REMOVE'
        g.hide_select = True

        # применить трансформации
        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'}
        g.icon = 'GESTURE_PAN'
        op = g.target_set_operator('object.pt_transform_apply')
        op.location = True
        op.rotation = False
        op.scale = False
        op.corrective_flip_normals = True

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'}
        g.icon = 'GESTURE_ROTATE'
        op = g.target_set_operator('object.pt_transform_apply')
        op.location = False
        op.rotation = True
        op.scale = False
        op.corrective_flip_normals = True

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'}
        g.icon = 'GESTURE_ZOOM'
        op = g.target_set_operator('object.pt_transform_apply')
        op.location = False
        op.rotation = False
        op.scale = True
        op.corrective_flip_normals = True

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'}
        g.icon = 'CON_SHRINKWRAP'
        op = g.target_set_operator('object.pt_transform_apply')
        op.location = False
        op.rotation = True
        op.scale = True
        op.corrective_flip_normals = True

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'}
        g.icon = 'GIZMO'
        op = g.target_set_operator('object.pt_transform_apply')
        op.location = True
        op.rotation = True
        op.scale = True
        op.apply_delta = True
        op.corrective_flip_normals = True

        for g in self.gizmos:
            g.color = color
            g.color_highlight = color_highlight
            g.backdrop_fill_alpha = backdrop_fill_alpha
            g.alpha = alpha
            g.line_width = line_width

    def draw_prepare(self, context):
        ui_scale = context.preferences.system.ui_scale

        wl, wr, hb, ht, wc, hc = viewport_points(context)

        left_offset = wl + (20 * ui_scale)

        # --- настройки расположения кнопок ---
        button_scale = 28/2 # радиус кнопки (без учёта ui-масштаба)
        offset = 10      # желаемый зазор между кнопками (без учёта ui-масштаба)
        separator_layout_scale = 0.1 # множитель высоты для разделителя в раскладке

        num_buttons = len(self.gizmos)
        if num_buttons == 0:
            return

        # --- 1. рассчитываем общую высоту блока ---

        # размеры в "реальных" пикселях на экране
        button_diameter_px = button_scale * 2 * ui_scale
        offset_px = offset * ui_scale

        layout_heights = []
        for g in self.gizmos:
            is_separator = (g.icon == 'REMOVE')

            # Эффективный диаметр для расчета раскладки
            layout_diameter = button_diameter_px
            if is_separator:
                layout_diameter *= separator_layout_scale

            layout_heights.append(layout_diameter)

        total_gizmos_height = sum(layout_heights)
        total_offset_height = max(0, num_buttons - 1) * offset_px
        total_group_height = total_gizmos_height + total_offset_height

        # --- 2. размещаем кнопки ---

        # y-координата для верха самого верхнего элемента
        current_y = hc + (total_group_height / 2)

        for i, g in enumerate(self.gizmos):
            layout_diameter = layout_heights[i]

            # центр текущего элемента находится на (current_y - его_радиус_в_раскладке)
            gizmo_center_y = current_y - (layout_diameter / 2)

            g.matrix_basis.translation = (left_offset, gizmo_center_y, 0)
            g.scale_basis = button_scale # визуальный масштаб одинаков для всех

            # смещаем y к нижней границе текущего элемента для следующей итерации
            current_y -= (layout_diameter + offset_px)


class PIVOTTRANSFORM_GGT_ui_widget_cursor(GizmoGroup):
    bl_idname = 'PIVOTTRANSFORM_GGT_ui_widget_cursor'
    bl_label = 'UI Widget Cursor'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'SCALE', 'SHOW_MODAL_ALL'}

    @classmethod
    def setup_keymap(cls, keyconfig):
        km = keyconfig.keymaps.new(name='Pivot Transform: Click', space_type='VIEW_3D')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK')
        return km

    @classmethod
    def poll(cls, context):
        return is_tool_active(context, 'pivot.cursor')

    def setup(self, context):
        line_width = 3
        alpha = 1
        backdrop_fill_alpha = 0.8
        color = (0.11, 0.11, 0.12)
        color_highlight = (0.23, 0.23, 0.24)

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'}
        g.icon = 'RESTRICT_SELECT_OFF'
        g.target_set_operator('object.pt_cursor_to_active')

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'}
        g.icon = 'RESTRICT_VIEW_OFF'
        g.target_set_operator('object.pt_align_from_view')

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = set()
        g.icon = 'REMOVE'
        g.hide_select = True

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'}
        g.icon = 'GESTURE_PAN'
        op = g.target_set_operator('object.pt_reset_cursor')
        op.loc = True
        op.rot = False

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'}
        g.icon = 'GESTURE_ROTATE'
        op = g.target_set_operator('object.pt_reset_cursor')
        op.loc = False
        op.rot = True

        g = self.gizmos.new('GIZMO_GT_button_2d')
        g.draw_options = {'OUTLINE', 'BACKDROP'}
        g.icon = 'GIZMO'
        op = g.target_set_operator('object.pt_reset_cursor')
        op.loc = True
        op.rot = True

        for g in self.gizmos:
            g.color = color
            g.color_highlight = color_highlight
            g.backdrop_fill_alpha = backdrop_fill_alpha
            g.alpha = alpha
            g.line_width = line_width

    def draw_prepare(self, context):
        ui_scale = context.preferences.system.ui_scale

        wl, wr, hb, ht, wc, hc = viewport_points(context)

        left_offset = wl + (20 * ui_scale)

        # --- настройки расположения кнопок ---
        button_scale = 28/2 # радиус кнопки (без учёта ui-масштаба)
        offset = 10      # желаемый зазор между кнопками (без учёта ui-масштаба)
        separator_layout_scale = 0.1 # множитель высоты для разделителя в раскладке

        num_buttons = len(self.gizmos)
        if num_buttons == 0:
            return

        # --- 1. рассчитываем общую высоту блока ---

        # размеры в "реальных" пикселях на экране
        button_diameter_px = button_scale * 2 * ui_scale
        offset_px = offset * ui_scale

        layout_heights = []
        for g in self.gizmos:
            is_separator = (g.icon == 'REMOVE')

            # Эффективный диаметр для расчета раскладки
            layout_diameter = button_diameter_px
            if is_separator:
                layout_diameter *= separator_layout_scale

            layout_heights.append(layout_diameter)

        total_gizmos_height = sum(layout_heights)
        total_offset_height = max(0, num_buttons - 1) * offset_px
        total_group_height = total_gizmos_height + total_offset_height

        # --- 2. размещаем кнопки ---

        # y-координата для верха самого верхнего элемента
        current_y = hc + (total_group_height / 2)

        for i, g in enumerate(self.gizmos):
            layout_diameter = layout_heights[i]

            # центр текущего элемента находится на (current_y - его_радиус_в_раскладке)
            gizmo_center_y = current_y - (layout_diameter / 2)

            g.matrix_basis.translation = (left_offset, gizmo_center_y, 0)
            g.scale_basis = button_scale # визуальный масштаб одинаков для всех

            # смещаем y к нижней границе текущего элемента для следующей итерации
            current_y -= (layout_diameter + offset_px)


classes = [
    PIVOTTRANSFORM_GGT_ui_widget,
    PIVOTTRANSFORM_GGT_ui_widget_cursor,
    ]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
