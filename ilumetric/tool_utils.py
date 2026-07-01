import bpy

__all__ = (
    "active_tool",
    "is_tool_active",
    "is_pivot_tool_active",
    "PIVOT_TOOL_IDNAMES",
    "WorkspaceToolWatcher",
)


# Все инструменты Pivot, между которыми переключается пользователь (D-cycle).
# Общие гизмо (saved points, cursor point, object points) активны на любом из них.
PIVOT_TOOL_IDNAMES = ('pivot.transform', 'pivot.bbox', 'pivot.align')


def active_tool():
    from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active
    return VIEW3D_PT_tools_active.tool_active_from_context(bpy.context)

def is_tool_active(context: bpy.types.Context, tool_idname: str) -> bool:
    """Проверка, активен ли сейчас инструмент *tool_idname* в переданном контексте.

    В первую очередь пытаемся определить инструмент через ``context.workspace.tools``.
    Такой способ надёжнее работает в 3D-вью. Если по каким-то причинам определить
    активный инструмент не удалось (например, отсутствует активная область),
    выполняется запасной вариант, основанный на внутренней функции
    *bl_ui.space_toolsystem_toolbar*.
    """
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        return getattr(tool, 'idname', None) == tool_idname
    except Exception:
        # Fallback – используем глобальный контекст (менее надёжно, но лучше, чем ничего)
        tool = active_tool()
        return getattr(tool, 'idname', None) == tool_idname


def is_pivot_tool_active(context: bpy.types.Context) -> bool:
    """True, если активен любой из инструментов Pivot (Flow / BBox / Align).

    Используется общими гизмо, которые должны работать на всех трёх инструментах.
    """
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        idname = getattr(tool, 'idname', None)
    except Exception:
        idname = getattr(active_tool(), 'idname', None)
    return idname in PIVOT_TOOL_IDNAMES



class WorkspaceToolWatcher:
    """Подписка на изменение активного Workspace-Tool через *bpy.msgbus*.

    Пример использования::

        def _on_tool_changed(is_active):
            print("Мой инструмент активен?", is_active)

        watcher = WorkspaceToolWatcher('my_addon.my_tool', _on_tool_changed)
    """

    def __init__(self, tool_idname, callback, owner: object | None = None):
        # tool_idname может быть строкой или коллекцией строк (несколько инструментов).
        if isinstance(tool_idname, str):
            self.tool_idnames = frozenset((tool_idname,))
        else:
            self.tool_idnames = frozenset(tool_idname)
        self.callback = callback  # (bool) -> None
        self.owner = owner or object()
        self._state: bool | None = None  # неизвестно
        self._subscribe()

    # ---------------------------------------------------------------------
    # Внутренние методы
    # ---------------------------------------------------------------------

    def _subscribe(self):
        bpy.msgbus.subscribe_rna(
            key=(bpy.types.WorkSpace, 'tools'),
            owner=self.owner,
            args=(self,),
            notify=WorkspaceToolWatcher._notify,
            options={"PERSISTENT"},
        )
        # немедленно проверить текущее состояние
        self._notify(self)

    @staticmethod
    def _active_tool_id(ctx: bpy.types.Context) -> str | None:
        try:
            tool = ctx.workspace.tools.from_space_view3d_mode(ctx.mode, create=False)
            if tool and getattr(tool, 'idname', None):
                return tool.idname
        except Exception:
            pass

        # Fallback – используем глобальный helper из UI, когда Workspace или ctx.area недоступны
        try:
            from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active
            tool = VIEW3D_PT_tools_active.tool_active_from_context(ctx)
            return getattr(tool, 'idname', None)
        except Exception:
            return None

    @staticmethod
    def _notify(self_ref):  # msgbus прокидывает owner как единственный аргумент
        ctx = bpy.context
        active_id = WorkspaceToolWatcher._active_tool_id(ctx)
        is_active = active_id in self_ref.tool_idnames
        if is_active != self_ref._state:
            self_ref._state = is_active
            try:
                self_ref.callback(is_active)
            except Exception as e:
                print(f"[WorkspaceToolWatcher] callback error: {e}")

    def unsubscribe(self):
        """Отписаться от msgbus, когда наблюдатель больше не нужен."""
        bpy.msgbus.clear_by_owner(self.owner)

