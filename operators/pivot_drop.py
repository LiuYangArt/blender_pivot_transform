import bpy
from bpy.types import Operator
from ..ilumetric.tool_utils import is_tool_active



class OBJECT_OT_pt_pivot_drop(Operator):
    bl_idname = 'object.pt_pivot_drop'
    bl_label = "Pivot Drop"
    bl_description = "Drag the pivot to a snapped location"

    def execute(self, context):
        #print('PT_OT_drop')
        settings = context.scene.pivot_transform

        # На инструменте Pivot Flow клик обрабатывает preselect-gizmo.
        # Pivot Drop оставляем только для обычного drag-снапа (BBox / Align).
        if is_tool_active(context, 'pivot.transform'):
            return {'CANCELLED'}

        bpy.ops.transform.transform(
            'INVOKE_DEFAULT',
            mode = 'TRANSLATION',
            release_confirm = True,
            # orient_matrix = self.orient_matrix,
            # center_override = self.center_override,
            snap = True,
            snap_target = 'CENTER',
            snap_align = True,
            snap_elements = settings.snap_elements,
        )
        return {'FINISHED'}



classes = [
    OBJECT_OT_pt_pivot_drop,
    ]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
