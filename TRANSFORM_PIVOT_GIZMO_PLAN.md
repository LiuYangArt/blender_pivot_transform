# Transform Pivot Gizmo 优化方案

## 目标

`Alt+Shift+A` pie menu 左下角是单按钮双状态：

- 未进入 Transform Pivot：显示 `Transform Pivot`。
- 已进入 Transform Pivot：显示 `Apply`。
- 两个按钮不能同时出现。

## 核心策略

Transform Pivot 使用 **hidden 3D Cursor proxy**：

- Start 时记录 3D Cursor 原始位置、旋转模式、旋转值和可见性。
- 临时把 3D Cursor 放到 active object 的真实 origin。
- 隐藏 3D Cursor overlay，避免视觉上看到 cursor 移动。
- gizmo 平移直接走 Blender 原生 `transform.translate(cursor_transform=True)`。
- session monitor 监听 3D Cursor 位置变化，并实时同步到真实 object origin。
- Apply / Cancel / 异常退出时恢复 3D Cursor 原始状态和显示状态。

这样 Ctrl snap、约束轴、release confirm 都复用 Blender 原生 3D Cursor transform 行为。

## 交互规则

1. `Transform Pivot`
   - 进入状态时记录目标对象原始 pivot 状态。
   - 记录 3D Cursor 原始 transform 和 overlay 显示状态。
   - 将 3D Cursor 放到当前 active object origin。
   - 隐藏 3D Cursor 显示。
   - 显示 pivot gizmo。

2. 拖动 gizmo
   - gizmo 箭头使用 `transform.translate` + `cursor_transform=True`。
   - Blender 原生 transform 负责 Ctrl snap、轴约束、confirm/cancel 手感。
   - monitor 将 3D Cursor 当前位置同步到目标对象真实 origin。
   - 多选时遵循现有 pivot 作用范围设置：Active / Selected。

3. `Apply`
   - 先同步最后一次 cursor 位置到 object origin。
   - 保留当前 object origin 结果。
   - 恢复 3D Cursor 原始 transform 和显示状态。
   - 退出 Transform Pivot 状态。

4. 取消
   - `Esc` / 右键取消。
   - 恢复进入 Transform Pivot 前记录的所有目标对象 origin 状态。
   - 恢复 3D Cursor 原始 transform 和显示状态。
   - 退出 Transform Pivot 状态。

## Ctrl Snap

- Ctrl snap 完全交给 Blender 原生 `transform.translate(cursor_transform=True)`。
- 不写死 `snap_elements`。
- 不读取插件偏好里的 `snap_elements`。
- 不手写 viewport pick / raycast snap。
- 遵循用户当前 `scene.tool_settings`、active transform snap 设置和 Blender 原生 Ctrl 行为。

## 实现约束

1. 允许临时写入 3D Cursor
   - Transform Pivot session 内可把 3D Cursor 作为 hidden proxy。
   - 只能在 session 内写入 cursor。
   - Apply / Cancel / unregister / 异常退出必须恢复 cursor 原始状态。

2. 3D Cursor 必须隐藏
   - Start 时隐藏所有当前窗口 3D View 的 `space.overlay.show_cursor`。
   - 退出时恢复每个 space 原始值。

3. Undo 策略
   - Transform Pivot 整个 session 只产生一个可撤销步骤。
   - 拖动过程不能每帧或每次鼠标事件 push undo。
   - `Apply` 确认当前结果；`Cancel` 恢复原状态后退出。

4. 恢复内容
   - Start 时记录目标对象原始 world origin。
   - Cancel 必须恢复进入前视觉状态。
   - 恢复选择、active object、mode。
   - 恢复 3D Cursor location / rotation mode / rotation value / overlay visibility。

5. 子对象稳定性
   - 修改父对象 origin/matrix 时，记录 direct children 的 world matrix。
   - 实时移动和 Cancel 后，子对象世界变换不能跳。

6. 异常退出清理
   - 对象被删、切换模式、打开新文件、禁用插件时，自动退出 Transform Pivot 状态。
   - 清理运行时缓存，避免悬挂对象引用。
   - 清理时必须恢复 3D Cursor 状态和 overlay visibility。

7. 支持范围
   - 首版只实现 origin 平移。
   - 旋转 gizmo 暂不实现。
   - 不支持的对象类型禁用入口，不做 silent fallback。

## 实现建议

1. 状态数据
   - `Scene.pt_object_pivot_transform_active: BoolProperty`
   - `Scene.pt_object_pivot_transform_matrix: FloatVectorProperty(size=16)`
   - 运行时缓存：对象引用、原始 origin、children world matrix、选择状态、active object、mode、cursor 原始状态、overlay 显示状态。

2. 操作符
   - `object.pt_object_pivot_transform_start`
   - `object.pt_object_pivot_transform_apply`
   - `object.pt_object_pivot_transform_cancel`
   - `object.pt_object_pivot_transform_monitor`

3. Gizmo
   - `PIVOTTRANSFORM_GGT_object_pivot_transform`
   - 平移箭头复用 `pivot.cursor` 的原生 transform 路径：
     - `GIZMO_GT_arrow_3d`
     - `target_set_operator('transform.translate')`
     - `constraint_axis`
     - `release_confirm = True`
     - `cursor_transform = True`
   - gizmo matrix 来自 hidden 3D Cursor proxy。
   - 视觉参数与 `PIVOTTRANSFORM_GGT_gizmo_cursor` 保持一致。
   - 朝向逻辑遵循 `settings.cursor_orient`，支持 `GLOBAL` / `CURSOR`。

4. Pie menu
   - 左下角根据 `pt_object_pivot_transform_active` 分支绘制：
     - `False`：`Transform Pivot`
     - `True`：`Apply`

## 验证

- `python -m py_compile __init__.py ui.py gizmos\object_pivot_transform.py operators\object_pivot_transform.py`
- Blender 5.1+ register/unregister 通过。
- 手动验证：
  - pie menu 单按钮双状态。
  - Start 后 3D Cursor 不可见。
  - Ctrl 拖动手感与 `pivot.cursor` 一致。
  - 拖动时对象真实 origin 实时移动。
  - Apply 保留结果并恢复 3D Cursor。
  - Esc / 右键恢复进入前 pivot 并恢复 3D Cursor。
  - 父对象 origin 变化时子对象不跳。
  - 切模式/删对象/禁用插件能清理状态。
