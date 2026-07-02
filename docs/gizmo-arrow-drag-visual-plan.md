# Gizmo Arrow 拖动视觉方案二

## 目标

修复 3D Cursor 和 Pivot gizmo 的 axis arrow 拖动视觉。

期望：

- 拖动 X/Y/Z 任意轴时，不显示“原地灰色 arrow + 移动黑色 arrow”。
- 被拖动 axis 仍显示原轴颜色，例如 X 始终红色、Y 始终绿色、Z 始终蓝色。
- 被拖动 axis arrow 和其它 axis arrow 一样，跟随整个 gizmo 当前位置更新。
- 3D Cursor 和 Pivot 两套 gizmo 行为一致。

## 当前状态

已提交的临时改动：`6f6fd9a Adjust gizmo arrow modal colors`。

该提交做了：

- `gizmos/cursor.py`：把 3D Cursor arrow 的 `use_draw_modal` 改为 `False`，并把 `color_highlight` 改为轴色。
- `gizmos/object_pivot_transform.py`：把 Pivot arrow 的 `use_draw_modal` 改为 `False`，并把 `color_highlight` 改为轴色。

用户验证结果：

- 原来的“原地灰色 + 移动黑色 arrow”消失了。
- 但被拖动的原 axis arrow 也消失了。

所以当前提交不是最终方案，只是确认了问题来源和限制。

## 相关文件

- `gizmos/cursor.py`
  - `PIVOTTRANSFORM_GGT_gizmo_cursor`
  - 创建 3D Cursor 的 X/Y/Z `GIZMO_GT_arrow_3d`
  - 当前使用 `transform.translate` 移动 cursor
- `gizmos/object_pivot_transform.py`
  - `PIVOTTRANSFORM_GGT_object_pivot_transform`
  - 创建 Pivot 的 X/Y/Z `GIZMO_GT_arrow_3d`
  - 当前也是通过 `transform.translate` + `cursor_transform = True` 移动 cursor/pivot

当前 arrow 的通用绘制模式：

```python
arrow = self.gizmos.new('GIZMO_GT_arrow_3d')
arrow.use_draw_offset_scale = True
arrow.use_draw_modal = False  # 当前临时状态
arrow.color = color
arrow.color_highlight = color
op = arrow.target_set_operator('transform.translate')
op.constraint_axis = (...)
op.release_confirm = True
op.cursor_transform = True
```

当前位置和轴向在 `draw_prepare()` 中刷新：

```python
arrow.matrix_basis = axis_matrix
arrow.matrix_offset = Matrix.Translation(Vector((0.0, 0.0, 0.6)))
```

`matrix_offset` 沿 arrow 自身局部 Z 偏移。X/Y arrow 先旋转到对应轴，所以偏移会表现为沿 X/Y/Z 轴推出。

## Blender 文档和源码依据

官方 API：

- `bpy.types.Gizmo`
  - 文档：<https://docs.blender.org/api/current/bpy.types.Gizmo.html>
  - `use_draw_modal`：文档说明为 “Show while dragging”。只能控制拖动时是否显示该 gizmo。
  - `matrix_basis` / `matrix_offset`：控制 gizmo 基础矩阵和偏移矩阵。
  - `target_set_operator()`：设置激活 gizmo 时运行的 operator。
- `bpy.types.GizmoGroup`
  - 文档：<https://docs.blender.org/api/current/bpy.types.GizmoGroup.html>
  - `SHOW_MODAL_ALL`：文档说明为交互时显示所有 gizmo，以及其它 gizmo 交互时也显示该组。

Blender 源码：

- `GIZMO_GT_arrow_3d`
  - 源码：<https://raw.githubusercontent.com/blender/blender/main/source/blender/editors/gizmo_library/gizmo_types/arrow3d_gizmo.cc>
  - `GIZMO_GT_arrow_3d` 是 Blender 内置 gizmo，不是本插件自定义类型。
  - `gizmo_arrow_setup()` 内部设置了 `WM_GIZMO_DRAW_MODAL`。
  - `gizmo_arrow_invoke()` 会保存 `init_matrix_final` 和 `init_arrow_length` 到 `interaction_data`。
  - `arrow_draw_intern()` 在 `gz->interaction_data` 存在时，会额外用 `init_matrix_final` 绘制一份半透明灰色 arrow：`float4{0.5f, 0.5f, 0.5f, 0.5f}`。

关键结论：

- 黑色移动 arrow 来自插件设置的 `color_highlight = (0, 0, 0)`。
- 原地灰色 arrow 来自 Blender 内置 `GIZMO_GT_arrow_3d` modal 交互绘制。
- Python API 没有暴露“关闭灰色 init arrow，但保留拖动中 arrow 显示”的开关。
- 因此只调 `use_draw_modal` / `color_highlight` / `SHOW_MODAL_ALL` 无法完整满足目标。

## 不推荐方案

### 仅恢复 `use_draw_modal = True`

效果预期：

- 被拖动 arrow 会重新出现。
- 如果 `color_highlight = 轴色`，移动 arrow 不再是黑色。
- 但 Blender 源码里的原地灰色 init arrow 大概率会回来。

结论：只能改善颜色，不能稳定移除 ghost。

### 仅修改 `SHOW_MODAL_ALL`

风险：

- `SHOW_MODAL_ALL` 作用于整个 gizmo group 的交互显示策略。
- 它不控制 `GIZMO_GT_arrow_3d` 内部 `interaction_data` 的灰色 arrow 绘制。
- 可能影响 dial 和其它 gizmo 的 modal 显示。

结论：不作为主方案。

## 推荐方案

把“可见 arrow”和“拖动命中/交互”拆开。

架构：

1. 可见彩色 arrow 只负责显示，不直接承担 Blender 内置 arrow modal 拖动。
2. 另建不可见或近透明 pick handle 负责接收鼠标拖动。
3. pick handle 绑定自定义 modal operator，而不是 `transform.translate`。
4. 自定义 modal operator 更新 `context.scene.cursor.location`。
5. `draw_prepare()` 每帧根据 cursor 当前矩阵刷新可见 arrow。

这样拖动期间可见 arrow 不进入 `GIZMO_GT_arrow_3d` 的内置 modal 交互，不会触发源码中的原地灰色 ghost。

## 实施方案

### 1. 新增自定义拖动 operator

建议放在 `gizmos/cursor.py`，或新建更清晰的模块后在 `__init__.py` 注册。

建议类名：

```python
class OBJECT_OT_pt_drag_cursor_axis(Operator):
    bl_idname = 'object.pt_drag_cursor_axis'
    bl_label = 'Drag Cursor Axis'
```

建议属性：

```python
axis: EnumProperty(items=[('X', 'X', ''), ('Y', 'Y', ''), ('Z', 'Z', '')])
coordinate_system: EnumProperty(items=[('GLOBAL', 'Global', ''), ('CURSOR', 'Cursor', '')])
```

职责：

- `invoke()`：记录初始 cursor location、初始 mouse、拖动轴向。
- `modal()`：鼠标移动时计算沿轴位移，更新 `context.scene.cursor.location`。
- `LEFTMOUSE`：确认。
- `ESC` / `RIGHTMOUSE`：恢复初始 location 并取消。

### 2. 轴向计算

GLOBAL：

```python
axis_vector = {
    'X': Vector((1, 0, 0)),
    'Y': Vector((0, 1, 0)),
    'Z': Vector((0, 0, 1)),
}[self.axis]
```

CURSOR：

```python
axis_vector = context.scene.cursor.rotation_euler.to_matrix() @ axis_vector
```

注意：如果 cursor rotation mode 不是 Euler，需要参考现有 `OBJECT_OT_pt_rotate_cursor` 的 rotation 处理，或优先从 `context.scene.cursor.matrix.decompose()[1]` 取 quaternion。

### 3. 鼠标位移投影

推荐从简单稳定版本开始：

1. 将起点 `start_location` 和 `start_location + axis_vector` 投影到屏幕。
2. 得到屏幕空间 axis direction。
3. 将鼠标 delta 投影到该屏幕方向。
4. 用视图尺度换算成世界位移。

可用 API：

```python
from bpy_extras.view3d_utils import location_3d_to_region_2d
```

实现时要处理：

- axis 投影到屏幕后长度接近 0 的情况。
- 正交/透视视图尺度差异。
- 需要和现有 `transform.translate` 手感尽量接近，但首要目标是视觉正确。

如果要更接近 Blender 内置移动，可参考项目已有移动 operator：

- `operators/pivot_transform.py`
- `gizmos/xform.py`

先用 `rg -n "modal\(|MOUSEMOVE|location_3d_to_region_2d|region_2d_to_location_3d" operators gizmos` 定位可复用模式。

### 4. 改造 3D Cursor gizmo

文件：`gizmos/cursor.py`

建议：

- 保留现有三根可见 arrow，用于显示。
- 可见 arrow 不绑定 `transform.translate`。
- 可见 arrow 设置：

```python
arrow.use_draw_modal = False
arrow.color = axis_color
arrow.color_highlight = axis_color
```

- 新增三个 pick handle，矩阵跟对应可见 arrow 一致。
- pick handle 可以先用 `GIZMO_GT_arrow_3d`，但必须避免可见 modal：

```python
handle.color = axis_color
handle.alpha = 0.0 或很低
handle.color_highlight = axis_color
handle.alpha_highlight = 0.0 或很低
handle.use_draw_modal = False
```

- handle 绑定：

```python
op = handle.target_set_operator('object.pt_drag_cursor_axis')
op.axis = 'X'
op.coordinate_system = settings.cursor_orient
```

注意：需要实测 `alpha = 0.0` 是否仍可 pick。若不可 pick，改成非常低 alpha，或使用其它可选中但视觉不明显的 gizmo 类型。

### 5. 改造 Pivot gizmo

文件：`gizmos/object_pivot_transform.py`

同 3D Cursor。

该 gizmo 当前也是基于 `context.scene.cursor.matrix` 绘制，并通过 `cursor_transform = True` 移动 cursor，因此自定义 operator 可以复用。

需要确保：

- Pivot 激活时拖动更新的是同一个 cursor/pivot 状态。
- 对象 pivot transform 流程未被破坏。

### 6. 注册类

如果 operator 放在 `gizmos/cursor.py`：

- 把 `OBJECT_OT_pt_drag_cursor_axis` 加进该文件 `classes`。

如果新建文件：

- 更新包注册入口。
- 先查看 `__init__.py` 的现有注册模式，不要发明新结构。

## 最小验证

代码级：

```powershell
python -m py_compile gizmos\cursor.py gizmos\object_pivot_transform.py
```

Blender 手动验证：

- 3D Cursor tool：拖动 X/Y/Z。
- Pivot transform：拖动 X/Y/Z。
- GLOBAL orientation。
- CURSOR orientation。
- 拖动确认。
- ESC / RIGHTMOUSE 取消。
- 检查没有原地灰色 ghost。
- 检查被拖动 arrow 不消失、不变黑。
- 检查其它 axis arrow 与被拖动 axis arrow 同步跟随。

## 回归风险

- 隐藏 pick handle 可能不可选中。
- 自定义拖动手感可能和 Blender 内置 `transform.translate` 不完全一致。
- Ctrl/Shift 修饰键行为可能丢失。
- 局部坐标和透视视角下，屏幕投影换算可能需要迭代。

## 完成标准

只有同时满足以下条件才算完成：

- 3D Cursor 和 Pivot 都没有灰色原地 ghost。
- 被拖动 axis arrow 保持轴色并持续可见。
- arrow 跟随 gizmo 整体移动。
- GLOBAL/CURSOR orientation 都可用。
- 取消拖动能恢复位置。
- 最小 Python 编译验证通过。