import bpy
from mathutils import Quaternion, Vector, Matrix
from math import pi
import bmesh
from ..ilumetric.custom_math.bcurve import get_curve_points, get_selected_curve_points
from ..ilumetric.custom_math.bbone import get_bone_points, get_selected_bone_points


# orientations
def get_global_orient():
    x = Quaternion((0.0, 1.0, 0.0), pi/2)
    y = Quaternion((1.0, 0.0, 0.0), -pi/2)
    z = Quaternion((0.0, 0.0, 1.0), -pi/2)
    return x, y, z


def get_local_orient(context):
    rot = context.object.matrix_world.decompose()[1]
    x = rot @ Quaternion((0.0, 1.0, 0.0), pi/2)
    y = rot @ Quaternion((1.0, 0.0, 0.0), -pi/2)
    z = rot @ Quaternion((0.0, 0.0, 1.0), -pi/2)
    return x, y, z


def get_gimbal_orient(context):
    ob = context.object
    rot_mode = ob.rotation_mode

    if rot_mode == 'QUATERNION':
        x = Quaternion((0.0, 1.0, 0.0), pi/2)
        y = Quaternion((1.0, 0.0, 0.0), -pi/2)
        z = Quaternion((0.0, 0.0, 1.0), -pi/2)
    elif rot_mode in ['XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX']: # FIXME все euler modes (сейчас только XYZ)
        rot = ob.matrix_world.decompose()[1]
        x = rot @ Quaternion((0.0, 1.0, 0.0), pi/2)
        y = Quaternion((0.0, 0.0, 1.0), ob.rotation_euler[2]) @ Quaternion((1.0, 0.0, 0.0), -pi/2)
        z = Quaternion((0.0, 0.0, 1.0), -pi/2)
    elif rot_mode == 'AXIS_ANGLE':  # FIXME angle mode
        rot = ob.rotation_axis_angle
        axis_angle_rot = Quaternion(rot[1:], rot[0])
        x = axis_angle_rot @ Quaternion((0.0, 1.0, 0.0), pi/2)
        y = Quaternion((0.0, 0.0, 1.0), -pi/2) @ axis_angle_rot
        z = Quaternion((0.0, 0.0, 1.0), -pi/2)

    return x, y, z


def get_view_orient(context):
    view_inv = context.region_data.view_matrix.inverted()
    rot = view_inv.decompose()[1]
    x = rot @ Quaternion((0.0, 1.0, 0.0), pi/2)
    y = rot @ Quaternion((1.0, 0.0, 0.0), -pi/2)
    z = rot @ Quaternion((0.0, 0.0, 1.0), -pi/2)
    return x, y, z


def get_cursor_orient(context):
    cursor_mat = context.scene.cursor.matrix
    rot = cursor_mat.decompose()[1]
    x = rot @ Quaternion((0.0, 1.0, 0.0), pi/2)
    y = rot @ Quaternion((1.0, 0.0, 0.0), -pi/2)
    z = rot @ Quaternion((0.0, 0.0, 1.0), -pi/2)
    return x, y, z


def get_parent_orient(context):
    obj = context.object
    parent = obj.parent
    if parent:
        rot = parent.matrix_world.decompose()[1]
    else:
        rot = Quaternion()
    x = rot @ Quaternion((0.0, 1.0, 0.0), pi/2)
    y = rot @ Quaternion((1.0, 0.0, 0.0), -pi/2)
    z = rot @ Quaternion((0.0, 0.0, 1.0), -pi/2)
    return x, y, z


def get_custom_orient(context, matrix=None):
    if matrix:
        rot = matrix.decompose()[1]
    else:
        custom_mat = context.scene.transform_orientation_slots[0].custom_orientation.matrix.to_4x4()
        rot = custom_mat.decompose()[1]
    x = rot @ Quaternion((0.0, 1.0, 0.0), pi/2)
    y = rot @ Quaternion((1.0, 0.0, 0.0), -pi/2)
    z = rot @ Quaternion((0.0, 0.0, 1.0), -pi/2)
    return x, y, z


def get_orientation(context, orient=None):
    if orient is None:
        orient_slots = context.window.scene.transform_orientation_slots[0].type
    else:
        orient_slots = orient

    if orient_slots =='GLOBAL':
        x, y, z = get_global_orient()
    elif orient_slots == 'LOCAL':
        x, y, z = get_local_orient(context)
    elif orient_slots == 'GIMBAL':
        x, y, z = get_gimbal_orient(context)
    elif orient_slots == 'NORMAL':
        x, y, z = get_local_orient(context)
    elif orient_slots == 'VIEW':
        x, y, z = get_view_orient(context)
    elif orient_slots == 'CURSOR':
        x, y, z = get_cursor_orient(context)
    elif orient_slots == 'PARENT':
        x, y, z = get_parent_orient(context)
    else:
        x, y, z = get_custom_orient(context)

    return x, y, z


# positions
def median_point_object(context):
    sOb = context.selected_objects
    object_co = [obj.matrix_world.translation for obj in sOb]
    return sum(object_co, Vector()) / len(sOb)


def cursor_point(context):
    return context.scene.cursor.location


def bb_point_ob(context):
    sOb = context.selected_objects
    x = (max([o.matrix_world.translation.x for o in sOb]) + min([o.matrix_world.translation.x for o in sOb])) / 2
    y = (max([o.matrix_world.translation.y for o in sOb]) + min([o.matrix_world.translation.y for o in sOb])) / 2
    z = (max([o.matrix_world.translation.z for o in sOb]) + min([o.matrix_world.translation.z for o in sOb])) / 2
    return Vector((x, y, z))


def object_get_position(context):
    tra_PP = context.scene.tool_settings.transform_pivot_point
    if tra_PP == 'ACTIVE_ELEMENT':
        loc = context.object.matrix_world.translation
    elif tra_PP in {'MEDIAN_POINT', 'INDIVIDUAL_ORIGINS'}:
        loc = median_point_object(context)
    elif tra_PP == 'BOUNDING_BOX_CENTER':
        loc = bb_point_ob(context)
    else:
        loc = cursor_point(context)
    return loc


# bbox
def get_bbox(mat):
    context = bpy.context
    inv_mat = mat.inverted()

    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = -float('inf')

    def update_bounds(co_world):
        nonlocal min_x, min_y, min_z, max_x, max_y, max_z
        co_local = inv_mat @ co_world
        x, y, z = co_local.x, co_local.y, co_local.z
        if x < min_x: min_x = x
        if x > max_x: max_x = x
        if y < min_y: min_y = y
        if y > max_y: max_y = y
        if z < min_z: min_z = z
        if z > max_z: max_z = z

    for ob in context.selected_objects:
        mode = context.mode

        if mode == 'OBJECT':
            if ob.type == 'MESH':
                for v in ob.data.vertices:
                    update_bounds(ob.matrix_world @ v.co)
            elif ob.type in {'CURVE', 'SURFACE'}:
                for co in get_curve_points():
                    update_bounds(co)
            elif ob.type == 'ARMATURE':
                for co in get_bone_points():
                    update_bounds(co)
            else:
                for corner in ob.bound_box:
                    update_bounds(ob.matrix_world @ Vector(corner))

        elif mode == 'EDIT_MESH':
            bm = bmesh.from_edit_mesh(ob.data)
            for v in bm.verts:
                if v.select:
                    update_bounds(ob.matrix_world @ v.co)

        elif mode in {'EDIT_CURVE', 'EDIT_SURFACE'}:
            for co in get_selected_curve_points():
                update_bounds(co)

        elif mode in {'EDIT_ARMATURE', 'POSE'}:
            for co in get_selected_bone_points():
                update_bounds(co)

        else:
            for corner in ob.bound_box:
                update_bounds(ob.matrix_world @ Vector(corner))

    if min_x == float('inf'):
        zero = mat.translation
        return (zero, zero, zero, zero, zero, zero)

    xP = mat @ Vector((max_x, (max_y + min_y) / 2, (max_z + min_z) / 2))
    xN = mat @ Vector((min_x, (max_y + min_y) / 2, (max_z + min_z) / 2))
    yP = mat @ Vector(((max_x + min_x) / 2, max_y, (max_z + min_z) / 2))
    yN = mat @ Vector(((max_x + min_x) / 2, min_y, (max_z + min_z) / 2))
    zP = mat @ Vector(((max_x + min_x) / 2, (max_y + min_y) / 2, max_z))
    zN = mat @ Vector(((max_x + min_x) / 2, (max_y + min_y) / 2, min_z))

    return xP, xN, yP, yN, zP, zN


# final matrix
def get_matrix(context, orient=None):
    s = Vector((1.0, 1.0, 1.0))

    qX, qY, qZ = get_orientation(context, orient)
    l = object_get_position(context)

    mX = Matrix.LocRotScale(l, qX, s).normalized()
    mY = Matrix.LocRotScale(l, qY, s).normalized()
    mZ = Matrix.LocRotScale(l, qZ, s).normalized()

    return mX, mY, mZ

