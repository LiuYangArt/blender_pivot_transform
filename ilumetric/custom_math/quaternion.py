from mathutils import Matrix, Quaternion, Vector
from math import radians
from .calculate import (
    createSpaceNormalTangent,
)


def look_rotation(forward, up):
    forward = forward.normalized()
    up = up.normalized()
    right = up.cross(forward).normalized()                  # Вычисление вектора right как перекрестного произведения up и forward
    up = forward.cross(right).normalized()                  # Пересчитываем up для ортогональности
    rot_matrix = Matrix((right, up, forward)).transposed()  # Создание матрицы поворота
    return rot_matrix.to_quaternion()                       # Преобразование матрицы в кватернион


def normal_qat_from_two_point(p1, p2, pn1, pn2):
    obmat = Matrix()
    imat = obmat.inverted()
    mat = imat.transposed()

    normal = Vector()
    plane = Vector()
    plane.negate()

    avrNormal = ((pn1 + pn2) * 0.5)
    plane = obmat @ Vector(p1) - obmat @ Vector(p2)
    avrNormal = mat @ avrNormal
    perpVec = plane.cross(avrNormal).normalized()
    normal = plane.cross(perpVec).normalized()
    normal.negate()

    r_orientation_mat = Matrix()
    createSpaceNormalTangent(r_orientation_mat, normal, plane)

    r_orientation_mat.invert_safe()
    rot = r_orientation_mat.decompose()[1]

    return rot @ Quaternion((1.0, 0.0, 0.0), radians(90)).normalized()
