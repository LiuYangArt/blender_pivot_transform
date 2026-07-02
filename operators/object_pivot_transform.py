import bpy
from bpy.types import Operator
from bpy.props import EnumProperty
from mathutils import Matrix, Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

from ..ilumetric import pick_util
from .origin_transform import (
    is_editable_id,
    _mesh_translate,
    _curve_translate,
    _font_translate,
    _lattice_translate,
    _mball_translate,
    _pointcloud_translate,
    _gpencil_translate,
    _apply_inverse_offset,
    ORIGIN_TO_CURSOR,
)


_SUPPORTED_OBJECT_TYPES = {
    'MESH', 'CURVE', 'SURFACE', 'FONT', 'LATTICE', 'META', 'POINTCLOUD', 'GREASEPENCIL', 'EMPTY'
}
_SESSION = None


def _safe_object(obj):
    try:
        obj.name
        return obj
    except ReferenceError:
        return None


def _supported_object(obj):
    if obj is None or obj.type not in _SUPPORTED_OBJECT_TYPES:
        return False
    if obj.type == 'EMPTY':
        return True
    return obj.data is not None and is_editable_id(obj.data)


def _target_objects(context):
    settings = context.scene.pivot_transform
    if settings.target == 'ACTIVE':
        objects = [context.active_object] if context.active_object else []
    else:
        objects = list(context.selected_editable_objects)
        if context.active_object in objects:
            objects.remove(context.active_object)
            objects.insert(0, context.active_object)
    return [obj for obj in objects if _supported_object(obj)]


def _data_translate(obj, local_delta):
    if obj.type == 'EMPTY':
        return True
    if isinstance(obj.data, bpy.types.Mesh):
        _mesh_translate(obj.data, local_delta, edit_mode=(obj.mode == 'EDIT'))
    elif isinstance(obj.data, bpy.types.Curve):
        if obj.type == 'FONT':
            delta = local_delta.copy()
            delta.z = 0.0
            _font_translate(obj.data, delta)
        else:
            _curve_translate(obj.data, local_delta)
    elif isinstance(obj.data, bpy.types.Lattice):
        _lattice_translate(obj.data, local_delta)
    elif isinstance(obj.data, bpy.types.MetaBall):
        _mball_translate(obj.data, local_delta)
    elif hasattr(bpy.types, 'PointCloud') and isinstance(obj.data, bpy.types.PointCloud):
        _pointcloud_translate(obj.data, local_delta)
    elif hasattr(bpy.types, 'GreasePencil') and isinstance(obj.data, bpy.types.GreasePencil):
        if not _gpencil_translate(obj.data, local_delta):
            raise RuntimeError(f'Failed to move Grease Pencil origin for {obj.name}')
    else:
        raise RuntimeError(f'Unsupported object data type for pivot move: {obj.name} ({obj.type})')
    if hasattr(obj.data, 'update'):
        obj.data.update()
    obj.update_tag(refresh={'DATA'})
    return True


def move_origin_to_world(context, obj, world_location):
    obj = _safe_object(obj)
    if obj is None or not _supported_object(obj):
        return False
    world_location = Vector(world_location)
    if obj.type == 'EMPTY':
        matrix = obj.matrix_world.copy()
        matrix.translation = world_location
        obj.matrix_world = matrix
        obj.update_tag(refresh={'OBJECT'})
        return True
    local_delta = obj.matrix_world.inverted() @ world_location
    if local_delta.length_squared <= 1e-18:
        return True
    _data_translate(obj, local_delta)
    _apply_inverse_offset(context, obj, local_delta, ORIGIN_TO_CURSOR)
    return True


def _active_pivot_matrix(context):
    obj = context.active_object
    if obj is None:
        return Matrix.Identity(4)
    matrix = obj.matrix_world.copy().normalized()
    matrix.translation = obj.matrix_world.translation
    return matrix


def _start_session(context):
    global _SESSION
    objects = _target_objects(context)
    if not objects:
        raise RuntimeError('No supported selected object for Transform Pivot')
    _SESSION = {
        'objects': [{'object': obj, 'origin': obj.matrix_world.translation.copy()} for obj in objects],
        'selected': [obj for obj in context.selected_objects],
        'active': context.active_object,
        'mode': context.mode,
        'delta': Vector((0.0, 0.0, 0.0)),
    }
    context.scene.pt_object_pivot_transform_active = True
    context.scene.pt_object_pivot_transform_matrix = [v for row in _active_pivot_matrix(context) for v in row]
    return _SESSION


def _session_objects():
    if not _SESSION:
        return []
    result = []
    for item in _SESSION['objects']:
        obj = _safe_object(item['object'])
        if obj is not None:
            result.append((item, obj))
    return result


def _apply_session_delta(context, delta):
    pairs = _session_objects()
    if not pairs:
        cancel_session(context, restore=False)
        return False
    _SESSION['delta'] = Vector(delta)
    targets = {obj for _item, obj in pairs}
    child_mats = []
    for _item, obj in pairs:
        for child in obj.children:
            if child not in targets:
                child_mats.append((child, child.matrix_world.copy()))
    for item, obj in pairs:
        move_origin_to_world(context, obj, item['origin'] + delta)
    context.view_layer.update()
    for child, matrix in child_mats:
        child = _safe_object(child)
        if child is not None:
            child.matrix_world = matrix
    context.view_layer.update()
    active = context.active_object
    if active is not None:
        context.scene.pt_object_pivot_transform_matrix = [v for row in _active_pivot_matrix(context) for v in row]
    return True


def _restore_selection(context):
    if not _SESSION:
        return
    for obj in context.selected_objects:
        obj.select_set(False)
    for obj in _SESSION['selected']:
        obj = _safe_object(obj)
        if obj is not None:
            obj.select_set(True)
    active = _safe_object(_SESSION['active'])
    if active is not None:
        context.view_layer.objects.active = active


def cancel_session(context, restore=True):
    global _SESSION
    if _SESSION and restore:
        _apply_session_delta(context, Vector((0.0, 0.0, 0.0)))
        _restore_selection(context)
    context.scene.pt_object_pivot_transform_active = False
    _SESSION = None


def apply_session(context):
    global _SESSION
    context.scene.pt_object_pivot_transform_active = False
    _SESSION = None
    bpy.ops.ed.undo_push(message='Transform Pivot')


def _axis_world(context, axis, orientation):
    base = {
        'X': Vector((1.0, 0.0, 0.0)),
        'Y': Vector((0.0, 1.0, 0.0)),
        'Z': Vector((0.0, 0.0, 1.0)),
    }[axis]
    if orientation == 'GLOBAL' or context.active_object is None:
        return base
    return (context.active_object.matrix_world.to_quaternion() @ base).normalized()


def _snap_elements(context):
    tool_settings = context.scene.tool_settings
    elements = set(getattr(tool_settings, 'snap_elements', set()) or set())
    if not elements:
        elements = set(getattr(tool_settings, 'snap_elements_base', set()) or set())
    return elements or {'INCREMENT'}


def _increment_step(context):
    space = getattr(context, 'space_data', None)
    overlay = getattr(space, 'overlay', None)
    grid_scale = getattr(overlay, 'grid_scale', 0.0) if overlay else 0.0
    return float(grid_scale) if grid_scale and grid_scale > 0.0 else 1.0


def _snap_increment_units(context, value):
    step = _increment_step(context)
    return round(value / step) * step


def _snap_pick_elements(elements):
    result = set()
    if 'VERTEX' in elements:
        result.add('VERT')
    if 'EDGE' in elements or 'EDGE_MIDPOINT' in elements or 'EDGE_PERPENDICULAR' in elements:
        result.add('EDGE')
    if {'FACE', 'FACE_PROJECT', 'FACE_NEAREST'} & elements:
        result.add('FACE')
    return tuple(result)


def _visible_snap_targets(context):
    session_targets = {obj for _item, obj in _session_objects()}
    use_self = getattr(context.scene.tool_settings, 'use_snap_self', True)
    targets = []
    for obj in context.visible_objects:
        if not use_self and obj in session_targets:
            continue
        if obj.visible_get():
            targets.append(obj)
    return targets


def _snap_axis_units(context, event, origin, axis, value):
    elements = _snap_elements(context)
    pick_elements = _snap_pick_elements(elements)
    if pick_elements:
        result = pick_util.pick_element(
            context,
            _visible_snap_targets(context),
            (event.mouse_region_x, event.mouse_region_y),
            radius_px=18.0,
            elements=pick_elements,
            backface_culling=getattr(context.scene.tool_settings, 'use_snap_backface_culling', False),
            face_center=False,
            edge_midpoint='EDGE_MIDPOINT' in elements,
            use_modifiers=True,
            occlusion=True,
        )
        if result is not None and not result.is_empty and result.hitpos is not None:
            return (result.hitpos - origin).dot(axis)
    if 'INCREMENT' in elements or 'GRID' in elements:
        return _snap_increment_units(context, value)
    return value


class OBJECT_OT_pt_object_pivot_transform_start(Operator):
    bl_idname = 'object.pt_object_pivot_transform_start'
    bl_label = 'Transform Pivot'
    bl_description = 'Start moving selected object origins with the pivot gizmo'
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.active_object is not None

    def execute(self, context):
        try:
            _start_session(context)
        except RuntimeError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        if context.window is not None and not bpy.app.background:
            try:
                bpy.ops.object.pt_object_pivot_transform_monitor('INVOKE_DEFAULT')
            except RuntimeError as error:
                self.report({'WARNING'}, f'Pivot monitor was not started: {error}')
        return {'FINISHED'}


class OBJECT_OT_pt_object_pivot_transform_apply(Operator):
    bl_idname = 'object.pt_object_pivot_transform_apply'
    bl_label = 'Apply'
    bl_description = 'Apply the current pivot transform result'
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(getattr(context.scene, 'pt_object_pivot_transform_active', False))

    def execute(self, context):
        apply_session(context)
        return {'FINISHED'}


class OBJECT_OT_pt_object_pivot_transform_cancel(Operator):
    bl_idname = 'object.pt_object_pivot_transform_cancel'
    bl_label = 'Cancel Transform Pivot'
    bl_description = 'Cancel pivot transform and restore original origins'
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(getattr(context.scene, 'pt_object_pivot_transform_active', False))

    def execute(self, context):
        cancel_session(context, restore=True)
        return {'CANCELLED'}


class OBJECT_OT_pt_object_pivot_transform_monitor(Operator):
    bl_idname = 'object.pt_object_pivot_transform_monitor'
    bl_label = 'Transform Pivot Monitor'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not getattr(context.scene, 'pt_object_pivot_transform_active', False):
            return {'FINISHED'}
        if context.mode != 'OBJECT' or not _session_objects():
            cancel_session(context, restore=False)
            return {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            cancel_session(context, restore=True)
            return {'CANCELLED'}
        return {'PASS_THROUGH'}


class OBJECT_OT_pt_object_pivot_transform_drag(Operator):
    bl_idname = 'object.pt_object_pivot_transform_drag'
    bl_label = 'Move Pivot Origin'
    bl_description = 'Drag the selected object origin along an axis'
    bl_options = {'INTERNAL'}

    axis: EnumProperty(items=[('X', 'X', ''), ('Y', 'Y', ''), ('Z', 'Z', '')], default='X')
    orientation: EnumProperty(items=[('GLOBAL', 'Global', ''), ('CURSOR', 'Local', '')], default='GLOBAL')

    def invoke(self, context, event):
        if not getattr(context.scene, 'pt_object_pivot_transform_active', False):
            return {'CANCELLED'}
        pivot = context.active_object.matrix_world.translation.copy()
        axis = _axis_world(context, self.axis, self.orientation)
        start_2d = location_3d_to_region_2d(context.region, context.region_data, pivot)
        end_2d = location_3d_to_region_2d(context.region, context.region_data, pivot + axis)
        if start_2d is None or end_2d is None:
            self.report({'WARNING'}, 'Pivot axis is not visible')
            return {'CANCELLED'}
        screen_axis = end_2d - start_2d
        if screen_axis.length < 1e-3:
            self.report({'WARNING'}, 'Pivot axis is parallel to view')
            return {'CANCELLED'}
        self._start_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        self._active_origin = _SESSION['objects'][0]['origin'].copy()
        self._base_delta = _SESSION.get('delta', Vector((0.0, 0.0, 0.0))).copy()
        self._screen_axis = screen_axis.normalized()
        self._pixels_per_unit = screen_axis.length
        self._axis_world = axis
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            current = Vector((event.mouse_region_x, event.mouse_region_y))
            pixels = (current - self._start_mouse).dot(self._screen_axis)
            units = pixels / self._pixels_per_unit
            axis_base = self._base_delta.dot(self._axis_world)
            axis_value = axis_base + units
            if event.ctrl:
                axis_value = _snap_axis_units(
                    context,
                    event,
                    self._active_origin,
                    self._axis_world,
                    axis_value,
                )
            delta = self._base_delta + self._axis_world * (axis_value - axis_base)
            _apply_session_delta(context, delta)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            cancel_session(context, restore=True)
            return {'CANCELLED'}
        return {'RUNNING_MODAL', 'PASS_THROUGH'}


classes = [
    OBJECT_OT_pt_object_pivot_transform_start,
    OBJECT_OT_pt_object_pivot_transform_apply,
    OBJECT_OT_pt_object_pivot_transform_cancel,
    OBJECT_OT_pt_object_pivot_transform_monitor,
    OBJECT_OT_pt_object_pivot_transform_drag,
]


def register():
    from bpy.props import BoolProperty, FloatVectorProperty
    bpy.types.Scene.pt_object_pivot_transform_active = BoolProperty(default=False)
    bpy.types.Scene.pt_object_pivot_transform_matrix = FloatVectorProperty(size=16, default=tuple(Matrix.Identity(4)[i][j] for i in range(4) for j in range(4)))
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    cancel_session(bpy.context, restore=False)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.pt_object_pivot_transform_matrix
    del bpy.types.Scene.pt_object_pivot_transform_active
