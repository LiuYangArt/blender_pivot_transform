import bpy
from bpy.types import Operator


class OBJECT_OT_pt_open_documentation(Operator):
    bl_idname = 'object.pt_open_documentation'
    bl_label = "Open Documentation"
    bl_description = "Open Pivot Transform documentation in a web browser"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        bpy.ops.wm.url_open(url="https://max-derksen.gitbook.io/pivot-transform/")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class OBJECT_OT_pt_open_preferences(Operator):
    bl_idname = 'object.pt_open_preferences'
    bl_label = "Open Preferences"
    bl_description = "Open Pivot Transform preferences"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        bpy.ops.screen.userpref_show()
        context.preferences.active_section = 'ADDONS'
        bpy.data.window_managers["WinMan"].addon_search = 'Pivot Transform'
        return {'FINISHED'}


classes = [
    OBJECT_OT_pt_open_documentation,
    OBJECT_OT_pt_open_preferences,
    ]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
