import bpy
from bpy.types import Operator
from mathutils import Matrix, Vector

from .origin_transform import is_editable_id


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


def _data_transform(obj, matrix):
    if obj.type == 'EMPTY':
        return True
    if isinstance(obj.data, bpy.types.Mesh):
        try:
            obj.data.transform(matrix, shape_keys=True)
        except TypeError:
            obj.data.transform(matrix)
    elif isinstance(obj.data, bpy.types.Curve):
        obj.data.transform(matrix)
    elif isinstance(obj.data, bpy.types.Lattice):
        obj.data.transform(matrix)
    elif isinstance(obj.data, bpy.types.MetaBall):
        obj.data.transform(matrix)
    elif hasattr(bpy.types, 'PointCloud') and isinstance(obj.data, bpy.types.PointCloud):
        obj.data.transform(matrix)
    elif hasattr(bpy.types, 'GreasePencil') and isinstance(obj.data, bpy.types.GreasePencil):
        if not hasattr(obj.data, 'transform'):
            raise RuntimeError(f'Grease Pencil pivot rotation is not supported for {obj.name}')
        obj.data.transform(matrix)
    else:
        raise RuntimeError(f'Unsupported object data type for pivot transform: {obj.name} ({obj.type})')
    if hasattr(obj.data, 'update'):
        obj.data.update()
    obj.update_tag(refresh={'DATA'})
    return True


def _cursor_state(cursor):
    state = {
        'location': cursor.location.copy(),
        'rotation_mode': cursor.rotation_mode,
        'rotation_euler': cursor.rotation_euler.copy(),
        'rotation_quaternion': cursor.rotation_quaternion.copy(),
        'rotation_axis_angle': tuple(cursor.rotation_axis_angle),
    }
    return state


def _restore_cursor_state(context):
    if not _SESSION:
        return
    state = _SESSION.get('cursor_state')
    if not state:
        return
    cursor = context.scene.cursor
    cursor.location = state['location']
    cursor.rotation_mode = state['rotation_mode']
    if state['rotation_mode'] == 'QUATERNION':
        cursor.rotation_quaternion = state['rotation_quaternion']
    elif state['rotation_mode'] == 'AXIS_ANGLE':
        cursor.rotation_axis_angle = state['rotation_axis_angle']
    else:
        cursor.rotation_euler = state['rotation_euler']


def _capture_and_hide_cursor_overlays(context):
    overlays = []
    wm = context.window_manager
    for window in getattr(wm, 'windows', []):
        screen = getattr(window, 'screen', None)
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    overlays.append((space, space.overlay.show_cursor))
                    space.overlay.show_cursor = False
    return overlays


def _restore_cursor_overlays():
    if not _SESSION:
        return
    for space, visible in _SESSION.get('cursor_overlays', []):
        try:
            space.overlay.show_cursor = visible
        except ReferenceError:
            pass


def _set_cursor_to_active_origin(context):
    cursor = context.scene.cursor
    obj = context.active_object
    matrix = obj.matrix_world.copy().normalized()
    matrix.translation = obj.matrix_world.translation
    cursor.matrix = matrix


def _start_session(context):
    global _SESSION
    objects = _target_objects(context)
    if not objects:
        raise RuntimeError('No supported selected object for Transform Pivot')
    cursor = context.scene.cursor
    _SESSION = {
        'objects': [{'object': obj, 'matrix': obj.matrix_world.copy(), 'origin': obj.matrix_world.translation.copy()} for obj in objects],
        'selected': [obj for obj in context.selected_objects],
        'active': context.active_object,
        'mode': context.mode,
        'delta': Vector((0.0, 0.0, 0.0)),
        'cursor_state': _cursor_state(cursor),
        'cursor_overlays': _capture_and_hide_cursor_overlays(context),
    }
    _set_cursor_to_active_origin(context)
    _SESSION['cursor_start_location'] = cursor.location.copy()
    _SESSION['cursor_start_matrix'] = cursor.matrix.copy().normalized()
    _SESSION['last_cursor_location'] = cursor.location.copy()
    context.scene.pt_object_pivot_transform_active = True
    context.scene.pt_object_pivot_transform_matrix = [v for row in cursor.matrix.normalized() for v in row]
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


def _matrix_with_world_location_and_basis(location, basis):
    matrix = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            matrix[row][col] = basis[row][col]
    matrix.translation = location
    return matrix


def _set_world_matrix_preserve_visual(obj, matrix):
    if obj.type == 'EMPTY':
        obj.matrix_world = matrix
        obj.update_tag(refresh={'OBJECT'})
        return True
    compensation = matrix.inverted() @ obj.matrix_world.copy()
    _data_transform(obj, compensation)
    obj.matrix_world = matrix
    return True


def _cursor_rotation_delta(context):
    start = _SESSION['cursor_start_matrix'].to_3x3()
    current = context.scene.cursor.matrix.normalized().to_3x3()
    return current @ start.inverted()


def _apply_session_transform(context, delta, rotation_delta):
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
        base = item['matrix']
        location = item['origin'] + delta
        basis = rotation_delta @ base.to_3x3()
        matrix = _matrix_with_world_location_and_basis(location, basis)
        _set_world_matrix_preserve_visual(obj, matrix)
    context.view_layer.update()
    for child, matrix in child_mats:
        child = _safe_object(child)
        if child is not None:
            child.matrix_world = matrix
    context.view_layer.update()
    active = context.active_object
    if active is not None:
        context.scene.pt_object_pivot_transform_matrix = [v for row in context.scene.cursor.matrix.normalized() for v in row]
    return True


def _apply_session_delta(context, delta):
    return _apply_session_transform(context, delta, Matrix.Identity(3))


def sync_origin_from_cursor(context):
    if not _SESSION:
        return False
    cursor_loc = context.scene.cursor.location.copy()
    delta = cursor_loc - _SESSION['cursor_start_location']
    rotation_delta = _cursor_rotation_delta(context)
    ok = _apply_session_transform(context, delta, rotation_delta)
    if ok:
        _SESSION['last_cursor_location'] = cursor_loc
    return ok


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


def _finish_session(context):
    context.scene.pt_object_pivot_transform_active = False
    _restore_cursor_state(context)
    _restore_cursor_overlays()


def cancel_session(context, restore=True):
    global _SESSION
    if _SESSION and restore:
        _apply_session_delta(context, Vector((0.0, 0.0, 0.0)))
        _restore_selection(context)
    if _SESSION:
        _finish_session(context)
    _SESSION = None


def apply_session(context):
    global _SESSION
    if _SESSION:
        sync_origin_from_cursor(context)
        _restore_selection(context)
        _finish_session(context)
        _SESSION = None
        bpy.ops.ed.undo_push(message='Transform Pivot')


def handle_session_exit_event(context, event):
    if event.value != 'PRESS':
        return None
    if event.type == 'ESC':
        cancel_session(context, restore=True)
        return {'CANCELLED'}
    if event.type in {'RET', 'NUMPAD_ENTER', 'RIGHTMOUSE'}:
        apply_session(context)
        return {'FINISHED'}
    return None


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
        sync_origin_from_cursor(context)
        result = handle_session_exit_event(context, event)
        if result is not None:
            return result
        return {'PASS_THROUGH'}


classes = [
    OBJECT_OT_pt_object_pivot_transform_start,
    OBJECT_OT_pt_object_pivot_transform_apply,
    OBJECT_OT_pt_object_pivot_transform_cancel,
    OBJECT_OT_pt_object_pivot_transform_monitor,
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
