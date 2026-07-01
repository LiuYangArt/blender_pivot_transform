import bpy
from . import preferences
from . import keymaps
from . import ui
from .ilumetric.tool_utils import WorkspaceToolWatcher, PIVOT_TOOL_IDNAMES
from .ilumetric import pick_util

from .utils import (
    utils,
)

from .gizmos import (
    axis_align,
    bbox,
    bottom,
    cursor,
    flow,
    objects,
    pivot_save,
    pivot_to_cursor,
    #ui_widget,
    xform,
)

from .operators import (
    ops,
    origin_transform,
    pivot_apply,
    pivot_drop,
    pivot_transform,
    pivot_to_select,
    pt_origin_set,
    pt_to_bottom,
)

from .tool import tools

modules = (
    preferences,

    ops,
    origin_transform,
    pivot_transform,
    pivot_to_select,
    pivot_apply,
    pivot_drop,
    pt_to_bottom,
    pt_origin_set,
    utils,

    axis_align,
    bbox,
    bottom,

    flow,
    objects,

    pivot_to_cursor,
    xform,
    #ui_widget,

    pivot_save,
    cursor,

    ui,

    keymaps,
)


_flow_tool_watcher: WorkspaceToolWatcher | None = None

def _on_flow_tool_changed(is_active: bool):
    import bpy
    ctx = bpy.context
    scene = getattr(ctx, "scene", None)
    if scene is None:
        return
    scene.tool_settings.use_transform_data_origin = is_active

def _make_flow_watcher():
    """Создать (или пересоздать) msgbus-наблюдатель и сразу синхронизировать сцену."""
    global _flow_tool_watcher
    if _flow_tool_watcher is not None:
        _flow_tool_watcher.unsubscribe()
    _flow_tool_watcher = WorkspaceToolWatcher(PIVOT_TOOL_IDNAMES, _on_flow_tool_changed)
    _flow_tool_watcher._notify(_flow_tool_watcher)

@bpy.app.handlers.persistent
def _on_load_post(_):
    """Blender handler: пересоздаём наблюдатель после File → New / Open."""
    _make_flow_watcher()


@bpy.app.handlers.persistent
def _on_depsgraph_update(scene, depsgraph):
    """Invalidate the Flow pick cache for objects whose geometry changed.

    GizmoGroup.refresh() only fires on selection-type changes, so geometry
    edits / modifier re-eval / frame changes would otherwise leave a stale
    cached BMesh. We invalidate per-object (cheap) using depsgraph.updates.
    """
    try:
        for update in depsgraph.updates:
            obj = update.id
            if isinstance(obj, bpy.types.Object) and update.is_updated_geometry:
                pick_util.invalidate_object(obj.original.as_pointer())
                # BBox-гизмо кеширует мировые точки выделения; refresh() не
                # ловит правки геометрии, поэтому инвалидируем здесь.
                bbox.mark_dirty()
    except (AttributeError, ReferenceError):
        pick_util.invalidate_all_caches()
        bbox.mark_dirty()


def _register_tools():
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper

    valid_modes = {}
    for tool in tools:
        tool_cls = tool['tool']
        space_type = tool_cls.bl_space_type
        if space_type not in valid_modes:
            helper = ToolSelectPanelHelper._tool_class_from_space_type(space_type)
            valid_modes[space_type] = set(helper._tools.keys()) if helper is not None else set()

        if tool_cls.bl_context_mode not in valid_modes[space_type]:
            # Режим отсутствует в этой версии Blender (например, GPv2/GPv3) — пропускаем.
            continue

        bpy.utils.register_tool(
            tool_cls,
            after=tool['after'],
            separator=tool['separator'],
            group=tool['group'],
        )


def _unregister_tools():
    seen = set()
    for tool in tools:
        tool_cls = tool['tool']
        tool_key = (tool_cls.bl_space_type, tool_cls.bl_context_mode, tool_cls.bl_idname)
        if tool_key in seen:
            continue
        seen.add(tool_key)
        _remove_tool_by_idname(tool_cls)


def _remove_tool_by_idname(tool_cls):
    from bl_ui.space_toolsystem_common import ToolDef, ToolSelectPanelHelper

    tools_helper = ToolSelectPanelHelper._tool_class_from_space_type(tool_cls.bl_space_type)
    if tools_helper is None:
        return

    tool_list = tools_helper._tools.get(tool_cls.bl_context_mode)
    if tool_list is None:
        # Режим не существует в этой версии Blender (например, GPv2/GPv3) — пропускаем.
        return
    keymaps = []

    for i in range(len(tool_list) - 1, -1, -1):
        item = tool_list[i]
        if isinstance(item, ToolDef):
            if item.idname == tool_cls.bl_idname:
                keymaps.append(item.keymap)
                del tool_list[i]
        elif isinstance(item, tuple):
            cleaned = []
            for sub_item in item:
                if isinstance(sub_item, ToolDef) and sub_item.idname == tool_cls.bl_idname:
                    keymaps.append(sub_item.keymap)
                else:
                    cleaned.append(sub_item)
            if len(cleaned) != len(item):
                if cleaned:
                    tool_list[i] = tuple(cleaned)
                else:
                    del tool_list[i]

    _clean_tool_list(tool_list)
    _remove_tool_keymaps(keymaps)

    if hasattr(tool_cls, "_bl_tool"):
        del tool_cls._bl_tool


def _clean_tool_list(tool_list):
    while tool_list and tool_list[-1] is None:
        del tool_list[-1]
    while tool_list and tool_list[0] is None:
        del tool_list[0]

    prev_is_none = False
    for i in range(len(tool_list) - 1, -1, -1):
        is_none = tool_list[i] is None
        if is_none and prev_is_none:
            del tool_list[i]
        prev_is_none = is_none


def _remove_tool_keymaps(keymaps):
    wm = bpy.context.window_manager
    for keymap_data in keymaps:
        if keymap_data is None:
            continue

        keymap_name = keymap_data[0]
        # Only remove keymaps generated for WorkSpaceTool definitions.
        # Never remove shared maps such as "3D View", otherwise add-on
        # shortcuts registered earlier in keymaps.py are removed too.
        if not keymap_name.startswith("3D View Tool:"):
            continue

        for keyconfig in (wm.keyconfigs.default, wm.keyconfigs.addon):
            if keyconfig is None:
                continue
            keymap = keyconfig.keymaps.get(keymap_name)
            if keymap is not None:
                keyconfig.keymaps.remove(keymap)


def register():
    for module in modules:
        module.register()

    _make_flow_watcher()

    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)

    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)

    _unregister_tools()
    _register_tools()


def unregister():
    _unregister_tools()

    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)

    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)

    pick_util.invalidate_all_caches()

    global _flow_tool_watcher
    if _flow_tool_watcher is not None:
        _flow_tool_watcher.unsubscribe()
        _flow_tool_watcher = None

    for module in reversed(modules):
        module.unregister()
