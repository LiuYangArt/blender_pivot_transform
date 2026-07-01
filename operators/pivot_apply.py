import bpy
import bmesh
from bpy.types import Operator
from mathutils import Matrix, Vector, Euler, Quaternion
from bpy.props import BoolProperty

# TODO нужно сделать отображение панели с настройками при запуске оператора

# ---------------------------------------------------------------------------
# helpers – direct data manipulation
# ---------------------------------------------------------------------------

def _rotation_matrix_3x3(obj):
    if obj.rotation_mode == 'QUATERNION':
        return obj.rotation_quaternion.to_matrix()
    if obj.rotation_mode == 'AXIS_ANGLE':
        aa = obj.rotation_axis_angle
        return Matrix.Rotation(aa[0], 3, Vector((aa[1], aa[2], aa[3])))
    return obj.rotation_euler.to_matrix()


def _reset_rotation(obj):
    if obj.rotation_mode == 'QUATERNION':
        obj.rotation_quaternion = Quaternion()
    elif obj.rotation_mode == 'AXIS_ANGLE':
        obj.rotation_axis_angle = (0.0, 0.0, 1.0, 0.0)
    else:
        obj.rotation_euler = Euler()


def _build_apply_matrix(obj, apply_loc, apply_rot, apply_sca):
    rs = None
    if apply_rot and apply_sca:
        rs = _rotation_matrix_3x3(obj) @ Matrix.Diagonal(Vector(obj.scale))
    elif apply_rot:
        rs = _rotation_matrix_3x3(obj)
    elif apply_sca:
        rs = Matrix.Diagonal(Vector(obj.scale))

    mat = rs.to_4x4() if rs else Matrix.Identity(4)

    if apply_loc:
        loc = obj.location
        mat[0][3] = loc[0]
        mat[1][3] = loc[1]
        mat[2][3] = loc[2]

    return mat


def _apply_to_data(obj, mat, flip_normals):
    """Применить матрицу к данным объекта (в object mode — через mesh.transform)."""
    data = obj.data
    if data is None:
        return

    if isinstance(data, bpy.types.Mesh):
        try:
            data.transform(mat, shape_keys=True)
        except TypeError:
            data.transform(mat)
        if flip_normals and mat.to_3x3().determinant() < 0:
            bm = bmesh.new()
            bm.from_mesh(data)
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
            bm.to_mesh(data)
            bm.free()
        data.update()
    elif hasattr(data, 'transform'):
        try:
            data.transform(mat)
        except Exception:
            pass
        if hasattr(data, 'update'):
            data.update()

    obj.update_tag(refresh={'DATA'})


# ---------------------------------------------------------------------------
# operator
# ---------------------------------------------------------------------------

class OBJECT_OT_pt_transform_apply(Operator):
    bl_idname = 'object.pt_transform_apply'
    bl_label = 'Apply Transform'
    bl_description = 'Apply selected transform channels'
    # Undo управляется вручную: в edit mode автоматический UNDO пушит в edit-mode
    # стек, который НЕ захватывает obj.location/rotation/scale → при Ctrl+Z меш
    # откатывается, а каналы трансформации остаются обнулёнными. Ручной memfile
    # push в object mode захватывает ВСЁ и даёт корректный однократный Ctrl+Z.
    bl_options = {'REGISTER'}

    location: BoolProperty(name='Location', default=False)
    rotation: BoolProperty(name='Rotation', default=False)
    scale: BoolProperty(name='Scale', default=False)
    properties: BoolProperty(name='Properties', default=False)
    apply_delta: BoolProperty(name='Apply Delta', default=False)
    corrective_flip_normals: BoolProperty(name='Corrective Flip Normals', default=True)

    @classmethod
    def description(cls, context, properties):
        parts = []
        if properties.location:
            parts.append('Location')
        if properties.rotation:
            parts.append('Rotation')
        if properties.scale:
            parts.append('Scale')
        if properties.properties:
            parts.append('Visual Transform')
        if properties.apply_delta:
            parts.append('Delta Transforms')
        if parts:
            return 'Apply ' + ', '.join(parts)
        return cls.bl_description

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        # --- Выходим из edit mode (flush bmesh → mesh, включаем memfile undo)
        restore_mode = None
        if context.mode != 'OBJECT':
            restore_mode = context.object.mode
            bpy.ops.object.mode_set('EXEC_DEFAULT', False, mode='OBJECT')

        # --- Memfile undo: снимок ВСЕХ данных (меш + каналы + режим)
        #     до внесения изменений. Один Ctrl+Z вернёт сюда.
        bpy.ops.ed.undo_push(message="Apply Transform")

        # --- Дельта-трансформации
        if self.apply_delta:
            for obj in context.selected_objects:
                obj.location += obj.delta_location
                obj.rotation_euler.x += obj.delta_rotation_euler.x
                obj.rotation_euler.y += obj.delta_rotation_euler.y
                obj.rotation_euler.z += obj.delta_rotation_euler.z
                obj.delta_rotation_euler = Euler()
                obj.delta_location = (0.0, 0.0, 0.0)

        apply_loc = self.location
        apply_rot = self.rotation
        apply_sca = self.scale
        flip = apply_sca and self.corrective_flip_normals

        # --- Bake visual transform (constraints и пр.)
        if self.properties:
            depsgraph = context.evaluated_depsgraph_get()
            for obj in context.selected_objects:
                ev = obj.evaluated_get(depsgraph)
                vmat = (obj.parent.matrix_world.inverted_safe() @ ev.matrix_world) if obj.parent else ev.matrix_world.copy()
                loc, rot, sca = vmat.decompose()
                obj.location = loc
                if obj.rotation_mode == 'QUATERNION':
                    obj.rotation_quaternion = rot
                elif obj.rotation_mode == 'AXIS_ANGLE':
                    axis, angle = rot.to_axis_angle()
                    obj.rotation_axis_angle = (angle, *axis)
                else:
                    obj.rotation_euler = rot.to_euler(obj.rotation_euler.order)
                obj.scale = sca

        # --- Применение трансформации к данным (mesh.transform в object mode)
        for obj in context.selected_objects:
            mat = _build_apply_matrix(obj, apply_loc, apply_rot, apply_sca)
            if mat == Matrix.Identity(4):
                continue

            _apply_to_data(obj, mat, flip)

            if obj.children:
                mat_inv = mat.inverted_safe()
                for child in obj.children:
                    child.matrix_parent_inverse = mat_inv @ child.matrix_parent_inverse

            if apply_loc:
                obj.location = (0.0, 0.0, 0.0)
            if apply_rot:
                _reset_rotation(obj)
            if apply_sca:
                obj.scale = (1.0, 1.0, 1.0)

        context.view_layer.update()

        # --- Возвращаемся в исходный режим
        if restore_mode is not None:
            bpy.ops.object.mode_set('EXEC_DEFAULT', False, mode=restore_mode)

        return {'FINISHED'}


classes = [
    OBJECT_OT_pt_transform_apply,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
