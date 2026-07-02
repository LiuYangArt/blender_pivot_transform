# Transform Pivot Gizmo 实施方案

## 目标

在 `Alt+Shift+A` pie menu 左下角提供一个单按钮双状态入口：

- 未进入状态：显示 `Transform Pivot`。
- 已进入状态：显示 `Apply`。

## 当前行为

1. 初始 gizmo transform 使用活动对象 pivot：
   - 位置：`context.active_object.matrix_world.translation`
   - 旋转：活动对象 world rotation
2. 支持多选：
   - 进入 Transform Pivot 后，所有选中对象 pivot 实时预览到 gizmo 位置/旋转。
   - `Apply` 确认当前结果并隐藏 gizmo。
3. 取消恢复：
   - `Esc` / 右键取消并恢复进入 Transform Pivot 前的 pivot。
4. Snap：
   - 移动 gizmo 复用 Blender `transform.translate` + `cursor_transform`。
   - `Ctrl` snap 遵循 Blender 当前 snap 设置。
5. Gizmo 稳定性：
   - 不再用自定义 offset handler 驱动 arrow。
   - arrow/dial 始终从当前 proxy cursor matrix 重新定位，避免 axis arrow 拖动后残留偏移。

## 实现结构

1. `gizmos/object_pivot_transform.py`
   - `Scene.pt_object_pivot_transform_active`
   - `Scene.pt_object_pivot_transform_matrix`
   - `object.pt_object_pivot_transform_start`
   - `object.pt_object_pivot_transform_apply`
   - `object.pt_object_pivot_transform_cancel`
   - `object.pt_object_pivot_transform_monitor`
   - `PIVOTTRANSFORM_GGT_object_pivot_transform`

2. 交互策略
   - 临时使用 3D Cursor 作为 gizmo proxy。
   - 记录原 3D Cursor matrix/mode，Apply/Cancel 后恢复。
   - arrow 直接调用 `transform.translate`，开启 `cursor_transform=True`。
   - dial 复用现有 `object.pt_rotate_cursor`。
   - cursor matrix 变化后同步 selected objects pivot，实现实时预览。

3. 恢复策略
   - Start 时记录所有选中对象的原始 pivot matrix。
   - Cancel 时逐对象恢复原始 pivot matrix。
   - 恢复原选择、active object、mode。

## 验证

- `python -m py_compile __init__.py ui.py gizmos\object_pivot_transform.py`
- Blender 5.1.2 background register/unregister 通过。
- Blender 5.1.2 实时预览 + Apply 测试通过。
- Blender 5.1.2 实时预览 + Cancel 恢复测试通过。