# Transform Pivot Gizmo 优化方案

## 目标

`Alt+Shift+A` pie menu 左下角改成单按钮双状态：

- 未进入 Transform Pivot：显示 `Transform Pivot`。
- 已进入 Transform Pivot：显示 `Apply`。
- 两个按钮不能同时出现。

## 交互规则

1. `Transform Pivot`
   - 进入状态时记录所有目标对象的原始 pivot 状态。
   - 显示 pivot gizmo，初始位置/旋转来自当前活动对象真实 origin。
   - 不使用 3D Cursor 做 pivot 移动代理，避免视觉上看到 3D Cursor 移动。

2. 拖动 gizmo
   - 实时移动选中对象真实 pivot/origin。
   - 预览即真实对象状态，保证 gizmo、origin、对象变换结果一致。
   - 多选时遵循现有 pivot 作用范围设置：Active / Selected。

3. `Apply`
   - 只确认当前实时结果并退出 Transform Pivot 状态。
   - 不再把 Cursor transform 二次应用到 pivot。

4. 取消
   - `Esc` / 右键取消。
   - 恢复进入 Transform Pivot 前记录的所有目标对象 pivot 状态。
   - 退出 Transform Pivot 状态。

## Ctrl Snap

- 拖动 pivot gizmo 时，按住 `Ctrl` 使用 Blender 当前 snap 设置。
- 不写死 `snap_elements`。
- 不强制传 `snap=True` / `snap_elements`，让 Blender 根据当前用户设置和 Ctrl 状态决定是否 snap。
- 优先使用 `bpy.ops.transform.translate(..., translate_origin=True)` 这类原生 transform 路径。
- 遵循用户当前 `scene.tool_settings` / active tool 的 snap 配置。
- 插件偏好里的 `snap_elements` 不再用于 Transform Pivot gizmo 的 Ctrl Snap。

## 实现约束

1. 不复用会移动 3D Cursor 的 helper
   - 当前 `utils.set_pivot_location()` / `cursorPivot()` 依赖临时移动 3D Cursor。
   - Transform Pivot 必须新增 cursor-free pivot/origin helper。
   - 全流程不得写入 `context.scene.cursor.location` / `context.scene.cursor.rotation_*`。

2. Undo 策略
   - Transform Pivot 整个 session 只产生一个可撤销步骤。
   - 拖动过程不能每帧或每次鼠标事件 push undo。
   - `Apply` 确认当前结果；`Cancel` 恢复原状态后退出。

3. 恢复内容
   - Start 时记录目标对象原始 world matrix / origin 状态。
   - 如果实现需要改 object data 来补偿 origin，Cancel 必须恢复到进入前视觉状态。
   - 恢复选择、active object、mode。

4. 子对象稳定性
   - 修改父对象 origin/matrix 时，记录 direct children 的 world matrix。
   - 实时移动和 Cancel 后，子对象世界变换不能跳。

5. 异常退出清理
   - 对象被删、切换工具、切换模式、打开新文件、禁用插件时，自动退出 Transform Pivot 状态。
   - 清理运行时缓存，避免悬挂对象引用。

6. 支持范围
   - 首版只启用能稳定 cursor-free 改 origin 的对象类型。
   - 不支持的对象类型直接禁用入口，不做 silent fallback。

## 实现建议

1. 状态数据
   - `Scene.pt_object_pivot_transform_active: BoolProperty`
   - `Scene.pt_object_pivot_transform_matrix: FloatVectorProperty(size=16)`
   - 运行时缓存：对象引用、原始 matrix/world origin、children world matrix、选择状态、active object、mode。

2. 操作符
   - `object.pt_object_pivot_transform_start`
   - `object.pt_object_pivot_transform_apply`
   - `object.pt_object_pivot_transform_cancel`
   - `object.pt_object_pivot_transform_monitor`

3. Gizmo
   - `PIVOTTRANSFORM_GGT_object_pivot_transform`
   - gizmo matrix 直接来自当前 pivot/origin 状态。
   - 样式和操作必须与 `pivot.cursor` 的 `PIVOTTRANSFORM_GGT_gizmo_cursor` 完全一致。
   - 复用同一套视觉参数：`GIZMO_GT_arrow_3d` 三轴箭头、`GIZMO_GT_dial_3d` 三轴旋转环、XYZ 颜色、黑色 highlight、alpha、line_width、scale_basis、matrix_offset。
   - 复用同一套朝向逻辑：遵循 `settings.cursor_orient`，支持 `GLOBAL` / `CURSOR` 两种朝向表现。
   - 平移操作行为与 3D Cursor gizmo 一致：三轴约束、左键拖动、release confirm、Ctrl 使用 Blender 当前 snap。
   - 旋转操作行为与 `object.pt_rotate_cursor` 一致：拖动旋转、Shift 精调、Ctrl 使用 `snap_angle_increment_3d`。
   - 实现时只能把目标从 3D Cursor 替换为 pivot/origin；不得写入 `context.scene.cursor`。
   - 拖动回调直接调用 cursor-free pivot/origin helper，实时写入对象 origin。
   - 不通过 `context.scene.cursor` 中转。

4. Pie menu
   - 左下角根据 `pt_object_pivot_transform_active` 分支绘制：
     - `False`：`Transform Pivot`
     - `True`：`Apply`

## 验证

- `python -m py_compile __init__.py ui.py gizmos\object_pivot_transform.py operators\pivot_transform.py`
- Blender 5.1+ register/unregister 通过。
- 手动验证：
  - pie menu 单按钮双状态。
  - Ctrl 拖动遵循当前 Blender snap 设置。
  - 拖动时对象真实 origin 实时移动。
  - Apply 保留结果并退出。
  - Esc / 右键恢复进入前 pivot。
  - 父对象 origin 变化时子对象不跳。
  - 切工具/删对象/禁用插件能清理状态。
  - 全流程中 3D Cursor 不移动。
