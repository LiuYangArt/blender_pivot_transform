import bpy
from bpy.types import GizmoGroup, Gizmo, Operator, Menu, UIList, PropertyGroup
from bpy.props import FloatVectorProperty, BoolProperty, IntProperty, EnumProperty, CollectionProperty
from mathutils import Matrix, Vector, Euler

from ..ilumetric.tool_utils import is_pivot_tool_active
from ..utils.utils import set_pivot_location, set_pivot_rotation

import gpu

def update_gizmo():
    try:
        bpy.utils.unregister_class(PIVOTTRANSFORM_GGT_pivot_saved_points)
        bpy.utils.register_class(PIVOTTRANSFORM_GGT_pivot_saved_points)
    except Exception as e:
        print("\n[{}]\n{}\n\nError:\n{}".format(__name__, "Updating Gizmo has failed", e))
        pass


class PIVOTTRANSFORM_store(PropertyGroup):
    position: FloatVectorProperty()
    rotation: FloatVectorProperty()


class PIVOTTRANSFORM_UL_items(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)

        pos = row.operator('object.pt_saved_pivot_set', text="", icon='ORIENTATION_VIEW')
        pos.index = index
        pos.action = 'POS'

        rot = row.operator('object.pt_saved_pivot_set', text="", icon='ORIENTATION_GIMBAL')
        rot.index = index
        rot.action = 'ROT'

        allAct = row.operator('object.pt_saved_pivot_set', text="All")
        allAct.index = index
        allAct.action = 'ALL'

        layout.prop( item, 'name', text='', emboss = False )


class OBJECT_OT_pt_saved_pivot_set(Operator):
    bl_idname = 'object.pt_saved_pivot_set'
    bl_label = 'Set Pivot'
    bl_description = 'Apply a saved pivot; Ctrl copies it to selected objects'
    bl_options= {'INTERNAL'}

    index: IntProperty()

    action: EnumProperty(
        name='Axis',
        items=[
            ('POS', 'Set Position', 'Apply only the saved position', '', 0),
            ('ROT', 'Set Rotation', 'Apply only the saved rotation', '', 1),
            ('ALL', 'Set Position & Rotation', 'Apply the saved position and rotation', '', 2)],
        default='ALL',
        )

    setPos: BoolProperty(name='Paste Transform', default=False)

    def execute(self, context):
        settings = context.scene.pivot_transform
        if settings.pivot_save_global:
            saved_props = context.scene
        else:
            saved_props = context.object

        try:
            point = saved_props.pivots_[self.index].position
            rotate = saved_props.pivots_[self.index].rotation

            if self.setPos:
                objs = context.selected_objects
                for ob in objs:
                    if self.action == 'POS':
                        ob.location = point
                    elif self.action == 'ROT':
                        ob.rotation_euler = rotate
                    else:
                        ob.location = point
                        ob.rotation_euler = rotate
            else:
                if self.action in {'POS', 'ALL'}:
                    set_pivot_location(context, location = point, undoPush = True, message = 'Pivot From Save'  )
                if self.action in {'ROT', 'ALL'}:
                    set_pivot_rotation(context, rotation = rotate, undoPush = True, message = 'Pivot From Save' )

        except:
            saved_props.pivots_Active_Index = -1
            point = saved_props.pivots_[self.index].position
            rotate = saved_props.pivots_[self.index].rotation

            if self.setPos:
                objs = context.selected_objects
                for ob in objs:
                    if self.action == 'POS':
                        ob.location = point
                    elif self.action == 'ROT':
                        ob.rotation_euler = rotate
                    else:
                        ob.location = point
                        ob.rotation_euler = rotate
            else:
                if self.action in {'POS', 'ALL'}:
                    set_pivot_location(context, location = point, undoPush = True, message = 'Pivot From Save'  )
                if self.action in {'ROT', 'ALL'}:
                    set_pivot_rotation(context, rotation = rotate, undoPush = True, message = 'Pivot From Save' )
        return {'FINISHED'}


    def invoke(self, context, event):
        self.setPos = event.ctrl
        return self.execute(context)


class OBJECT_OT_pt_saved_pivot_move(Operator):
    bl_idname = 'object.pt_saved_pivot_move'
    bl_label = 'Move Pivot'
    bl_description = 'Move the saved pivot item in the list'
    bl_options= {'REGISTER'}

    isUp: BoolProperty()

    def execute(self, context):
        settings = context.scene.pivot_transform
        if settings.pivot_save_global:
            saved_props = context.scene
        else:
            saved_props = context.object

        idx = saved_props.pivots_Active_Index

        if self.isUp and idx >= 1:
            saved_props.pivots_.move(idx, idx-1)
            saved_props.pivots_Active_Index -= 1

        if self.isUp is False and idx < len(saved_props.pivots_) - 1:
            saved_props.pivots_.move(idx, idx+1)
            saved_props.pivots_Active_Index += 1
        return {'FINISHED'}


class OBJECT_OT_pt_saved_pivot_add(Operator):
    bl_idname = 'object.pt_saved_pivot_add'
    bl_label = 'Add Pivot'
    bl_description = 'Save the active pivot transform'
    bl_options= {'REGISTER'}

    def execute(self, context):
        settings = context.scene.pivot_transform
        if settings.pivot_save_global:
            saved_props = context.scene
        else:
            saved_props = context.object

        point = saved_props.pivots_.add()
        point.name = "Pivot " + str(saved_props.pivots_Active_Index+2)
        point.position = context.object.location
        point.rotation = context.object.rotation_euler
        saved_props.pivots_Active_Index = len(saved_props.pivots_)-1
        update_gizmo()
        return {'FINISHED'}


class OBJECT_OT_pt_saved_pivot_remove(Operator):
    bl_idname = 'object.pt_saved_pivot_remove'
    bl_label = 'Remove Pivot'
    bl_description = 'Remove the selected saved pivot'
    bl_options= {'REGISTER'}

    def execute(self, context):
        settings = context.scene.pivot_transform
        if settings.pivot_save_global:
            saved_props = context.scene
        else:
            saved_props = context.object

        if len(saved_props.pivots_) > 0:
            saved_props.pivots_.remove(saved_props.pivots_Active_Index)

            if saved_props.pivots_Active_Index == 0:
                saved_props.pivots_Active_Index += 1

            if saved_props.pivots_Active_Index > -1:
                saved_props.pivots_Active_Index = 0
        update_gizmo()
        return {'FINISHED'}


# -----------------------------------------------------------------------------
#   Operators for gizmo interaction
# -----------------------------------------------------------------------------
class OBJECT_OT_pt_saved_pivot_menu(Operator):
    """Pie-menu for actions on saved pivot point (set, delete)."""
    bl_idname = 'object.pt_saved_pivot_menu'
    bl_label = 'Saved Pivot Menu'
    bl_description = 'Open actions for this saved pivot'
    bl_options = {'INTERNAL'}

    index: IntProperty()

    def execute(self, context):
        wm = context.window_manager
        settings = context.scene.pivot_transform
        saved_props = context.scene if settings.pivot_save_global else context.object
        if saved_props is None or len(saved_props.pivots_) == 0:
            return {'CANCELLED'}

        real_index = min(self.index, len(saved_props.pivots_) - 1)
        saved_props.pivots_Active_Index = real_index

        wm.pivotgp_gizmo_index = real_index

        bpy.ops.wm.call_menu_pie(name='PIVOTGP_MT_pivot_action_pie')
        return {'FINISHED'}


class PIVOTGP_MT_pivot_action_pie(Menu):
    bl_idname = 'PIVOTGP_MT_pivot_action_pie'
    bl_label = 'Saved Pivot Actions'

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()
        idx = context.window_manager.pivotgp_gizmo_index

        # Set Position
        op = pie.operator('object.pt_saved_pivot_set', text='Position', icon='CON_LOCLIMIT')
        op.index = idx
        op.action = 'POS'

        # Set Rotation
        op = pie.operator('object.pt_saved_pivot_set', text='Rotation', icon='CON_ROTLIKE')
        op.index = idx
        op.action = 'ROT'

        # Set Position & Rotation
        op = pie.operator('object.pt_saved_pivot_set', text='Position & Rotation', icon='ORIENTATION_LOCAL')
        op.index = idx
        op.action = 'ALL'

        # Delete Saved Point
        pie.operator('object.pt_saved_pivot_remove', text='Delete', icon='TRASH')


class Gizmo_ViewAligned(Gizmo): # TODO перенести в utils
    __slots__ = ('use_align_view')

    @staticmethod
    def _apply_align_view(mat_world: Matrix, rv3d):
        """Billboard: R_align = (view_mat · R)ᵀ, без масштаба и переноса."""
        # 1. Берём только вращение, удаляя масштаб:
        rot = mat_world.to_3x3().normalized()      # <- нормализация убрала S
        rot4 = rot.to_4x4()

        # 2. Строим матрицу выравнивания.
        align = rv3d.view_matrix @ rot4
        align.translation.zero()                   # T = 0
        align.transpose()                          # ( … )ᵀ  ==  обратное R

        # 3. Домножаем – только на GPU-стеке, данные гизмо не трогаем.
        gpu.matrix.multiply_matrix(align)

    # основной отрисовщик
    def draw_custom_shape(self, shape, *, matrix=None, select_id=None, context=None):
        import gpu
        if matrix is None:
            matrix = self.matrix_world

        batch, shader = shape
        shader.bind()
        ctx  = context or bpy.context
        blend = False

        if select_id is not None:
            gpu.select.load_id(select_id)
            use_blend = False
        else:
            if self.is_highlight:
                color = (*self.color_highlight, self.alpha_highlight)
            else:
                color = (*self.color, self.alpha)
            shader.uniform_float("color", color)
            use_blend = color[3] < 1.0

        if use_blend:
            gpu.state.blend_set('ALPHA')

        with gpu.matrix.push_pop():
            gpu.matrix.multiply_matrix(matrix)   # базовая матрица

            if getattr(self, 'use_align_view', False):
                rv3d = getattr(ctx, "region_data", None)
                if rv3d:
                    self._apply_align_view(matrix, rv3d)

            batch.draw(shader)

        if blend:
            gpu.state.blend_set('NONE')


class PIVOTTRANSFORM_GT_triangle(Gizmo_ViewAligned):
    bl_idname = 'PIVOTTRANSFORM_GT_triangle'

    __slots__ = (
        'shape',
        )

    def setup(self):
        self.line_width = 1.5
        self.color = (1, 0.55, 0.16)
        self.color_highlight = (0.78, 0.78, 0.8)
        self.alpha = 0.9
        self.alpha_highlight = 0.99

        self.use_align_view = True

        if not hasattr(self, 'shape'):
            from .bottom import get_circle
            tri = get_circle(position=(0, 0), radius=1.2, segments=4)
            self.shape = self.new_custom_shape('TRI_FAN', tri)

    def draw(self, context):
        self.draw_custom_shape(self.shape)

    def draw_select(self, context, select_id):
        self.draw_custom_shape(self.shape, select_id=select_id)
# -----------------------------------------------------------------------------
#   GizmoGroup that draws saved pivot points in 3D-view
# -----------------------------------------------------------------------------
class PIVOTTRANSFORM_GGT_pivot_saved_points(GizmoGroup):
    bl_idname = 'PIVOTTRANSFORM_GGT_pivot_saved_points'
    bl_label = 'Saved Pivot Points'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SHOW_MODAL_ALL'}

    @classmethod
    def setup_keymap(cls, keyconfig):
        km = keyconfig.keymaps.new(name='Pivot Transform Saved: Click', space_type='VIEW_3D')
        km.keymap_items.new('gizmogroup.gizmo_tweak', type='LEFTMOUSE', value='CLICK')
        return km

    # ------------------------------------------------------------------
    #   Utility
    # ------------------------------------------------------------------
    @staticmethod
    def _get_saved_props(context):
        settings = context.scene.pivot_transform
        return context.scene if settings.pivot_save_global else context.object

    @classmethod
    def poll(cls, context):
        settings = context.scene.pivot_transform
        if not settings.pivot_save_visible:
            return False
        if not is_pivot_tool_active(context):
            return False
        saved_props = cls._get_saved_props(context)
        return saved_props is not None and len(saved_props.pivots_) > 0

    # ------------------------------------------------------------------
    #   Gizmo lifecycle helpers
    # ------------------------------------------------------------------
    def _ensure_gizmo_count(self, context):
        saved_props = self._get_saved_props(context)
        if saved_props is None:
            return
        saved = saved_props.pivots_

        # NOTE: self.gizmos already includes axis gizmo (added later).
        # We only care that we have at least len(saved) point gizmos.
        while len(self.gizmos) < len(saved):
            g = self.gizmos.new('PIVOTTRANSFORM_GT_triangle')
            #g.draw_options = {'FILL', 'FILL_SELECT', 'ALIGN_VIEW'}
            #g.draw_style = 'CROSS_2D'
            g.use_align_view = True
            g.use_tooltip = False
            g.color = (1, 0.55, 0.16)
            g.color_highlight = (1, 0.8, 0)
            g.alpha = 0.9
            g.alpha_highlight = 0.99
            g.scale_basis = 0.08
            g.line_width = 2
            idx = len(self.gizmos) - 1  # zero-based index of newly added gizmo
            op = g.target_set_operator('object.pt_saved_pivot_menu')
            op.index = idx

    # ------------------------------------------------------------------
    #   Blender callbacks
    # ------------------------------------------------------------------
    def setup(self, context):
        # Create point gizmos first
        self._ensure_gizmo_count(context)
        # Axis gizmo for highlight feedback
        self.axis = self.gizmos.new('PIVOTTRANSFORM_GT_axis')

    def refresh(self, context):
        saved_props = self._get_saved_props(context)
        if saved_props is None:
            return
        saved = saved_props.pivots_

        for idx, (g, item) in enumerate(zip(self.gizmos, saved)):
            # Update operator index (may change after re-ordering)
            op = g.target_set_operator('object.pt_saved_pivot_menu')
            op.index = idx

            # Matrix for gizmo point (location + orientation)
            loc = Vector(item.position)
            rot = Euler(item.rotation).to_quaternion()
            g.matrix_basis = Matrix.LocRotScale(loc, rot, Vector((1, 1, 1))).normalized()

    def draw_prepare(self, context):
        # Show axis on highlighted gizmo
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


# --- UI ---
# class VIEW3D_PT_pt_save(Panel):
#     bl_idname = 'VIEW3D_PT_pt_save'
#     bl_label = 'Pivot Save'
#     bl_space_type = 'VIEW_3D'
#     bl_region_type = 'UI'
#     bl_parent_id = 'VIEW3D_PT_pivot_transform'
#     bl_options = {'DEFAULT_CLOSED'}

#     def draw(self, context):
#         layout = self.layout

#         settings = context.scene.pivot_transform
#         if settings.pivot_save_global:
#             saved_props = context.scene
#         else:
#             saved_props = context.object

#         if len(saved_props.pivots_) > 0:
#             row = layout.row()
#             row.template_list('PIVOTTRANSFORM_UL_items', '', saved_props, 'pivots_', saved_props, 'pivots_Active_Index')

#             col = row.column( align = True )
#             col.operator('object.pt_saved_pivot_add', text="", icon='ADD')
#             col.operator('object.pt_saved_pivot_remove', text="", icon='REMOVE')
#             col.separator()
#             col.operator('object.pt_saved_pivot_move', text="", icon='TRIA_UP').isUp = True
#             col.operator('object.pt_saved_pivot_move', text="", icon='TRIA_DOWN').isUp = False
#             col.separator()
#             if settings.pivot_save_global:
#                 col.prop(settings, 'pivot_save_global', text="", icon='WORLD')
#             else:
#                 col.prop(settings, 'pivot_save_global', text="", icon='WORLD')

#             # данные позиции и вращения
#             col = layout.column( align = True )
#             row = col.row( align = True )
#             row.label(icon='ORIENTATION_VIEW')
#             row.prop(saved_props.pivots_[saved_props.pivots_Active_Index], 'position', text="")

#             row = col.row( align = True )
#             row.label(icon='ORIENTATION_GIMBAL')
#             row.prop(saved_props.pivots_[saved_props.pivots_Active_Index], 'rotation', text="")

#         else:
#             row = layout.row()
#             row.operator('object.pt_saved_pivot_add', text="Save Pivot", icon='FILE_TICK')
#             row.prop(settings, 'pivot_save_global', text="", icon='WORLD')


classes = (
    PIVOTTRANSFORM_store,
    PIVOTTRANSFORM_UL_items,
    OBJECT_OT_pt_saved_pivot_add,
    OBJECT_OT_pt_saved_pivot_remove,
    OBJECT_OT_pt_saved_pivot_set,
    OBJECT_OT_pt_saved_pivot_move,

    OBJECT_OT_pt_saved_pivot_menu,
    PIVOTGP_MT_pivot_action_pie,
    PIVOTTRANSFORM_GT_triangle,
    PIVOTTRANSFORM_GGT_pivot_saved_points,

    #VIEW3D_PT_pt_save,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.pivots_ = CollectionProperty(type=PIVOTTRANSFORM_store)
    bpy.types.Scene.pivots_Active_Index = IntProperty()

    bpy.types.Object.pivots_ = CollectionProperty(type=PIVOTTRANSFORM_store)
    bpy.types.Object.pivots_Active_Index = IntProperty()

    # WindowManager property to pass index from gizmo to pie-menu
    bpy.types.WindowManager.pivotgp_gizmo_index = IntProperty(default=-1)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.pivots_
    del bpy.types.Scene.pivots_Active_Index

    del bpy.types.Object.pivots_
    del bpy.types.Object.pivots_Active_Index

    del bpy.types.WindowManager.pivotgp_gizmo_index
