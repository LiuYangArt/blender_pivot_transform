from mathutils import Matrix, Vector
import numpy
from math import sqrt


def add_v3_v3(r, a):
    r[0] += a[0]
    r[1] += a[1]
    r[2] += a[2]


def add_v3_v3v3(a, b):
    r = Vector()
    r[0] = a[0] + b[0]
    r[1] = a[1] + b[1]
    r[2] = a[2] + b[2]
    return r


def sub_v3_v3(r, a):
    r[0] -= a[0]
    r[1] -= a[1]
    r[2] -= a[2]


def sub_v3_v3v3(r, a, b):
    r[0] = a[0] - b[0]
    r[1] = a[1] - b[1]
    r[2] = a[2] - b[2]


def cross_v3_v3v3(r, a, b):
    r[0] = a[1] * b[2] - a[2] * b[1]
    r[1] = a[2] * b[0] - a[0] * b[2]
    r[2] = a[0] * b[1] - a[1] * b[0]


def mul_mat3_m4_v3(M, v):
    r = Vector()
    x = v[0]
    y = v[1]
    r[0] = x * M[0][0] + y * M[1][0] + M[2][0] * r[2]
    r[1] = x * M[0][1] + y * M[1][1] + M[2][1] * r[2]
    r[2] = x * M[0][2] + y * M[1][2] + M[2][2] * r[2]
    return r


def copy_v3_v3(r, a):
    r[0] = a[0]
    r[1] = a[1]
    r[2] = a[2]


def is_zero_v3(v):
    return v[0] == 0.0 and v[1] == 0.0 and v[2] == 0.0


# --- math_vector_inline
def mul_v3_v3fl(r, a, f):
    r[0] = a[0] * f
    r[1] = a[1] * f
    r[2] = a[2] * f


def negate_v3_v3(r, a):
    r[0] = -a[0]
    r[1] = -a[1]
    r[2] = -a[2]


def normalize_v3_v3_length(r, a, unit_length):
    d = a.dot(a)
    if d > numpy.log1p(1.0e-35):
        d = sqrt(d)
        mul_v3_v3fl(r, a, unit_length/d)
        #print(numpy.log1p(1.0e-35))
    else:
        r.zero()
        d = 0.0
        #print(2)
    return d


def normalize_v3_v3(r, a):
    return normalize_v3_v3_length(r, a, 1.0)


def normalize_v3(n):
    return normalize_v3_v3(n, n)


def len_squared_v3v3(a, b):
    d = Vector()
    sub_v3_v3v3(d, b, a)
    return d.dot(d)


def len_v3(a):
    return sqrt( a.dot(a) )


def len_v3v3(a, b):
    d = Vector()
    sub_v3_v3v3(d, b, a)
    return len_v3(d)


# --- math_vector
def minmax_v3v3_v3(min_v, max_v, vec):
    if min_v[0] > vec[0]:
        min_v[0] = vec[0]

    if min_v[1] > vec[1]:
        min_v[1] = vec[1]

    if min_v[2] > vec[2]:
        min_v[2] = vec[2]


    if max_v[0] < vec[0]:
        max_v[0] = vec[0]

    if max_v[1] < vec[1]:
        max_v[1] = vec[1]

    if max_v[2] < vec[2]:
        max_v[2] = vec[2]


def axis_sort_v3(axis_values, order):
    v = axis_values
    if v[0] < v[1]:
        if v[2] < v[0]:
            order[0], order[2] = order[2], order[0]
    else:
        if v[1] < v[2]:
            order[0], order[1] = order[1], order[0]
        else:
            order[0], order[2] = order[2], order[0]


    if v[2] < v[1]:
        order[1], order[2] = order[2], order[1]


def mid_v3_v3v3(a, b):
    r = Vector()
    r[0] = 0.5 * (a[0] + b[0])
    r[1] = 0.5 * (a[1] + b[1])
    r[2] = 0.5 * (a[2] + b[2])
    return r


# --- math_geom
def normal_tri_v3(n, v1, v2, v3):
  n1 = Vector()
  n2 = Vector()

  n1[0] = v1[0] - v2[0]
  n2[0] = v2[0] - v3[0]
  n1[1] = v1[1] - v2[1]
  n2[1] = v2[1] - v3[1]
  n1[2] = v1[2] - v2[2]
  n2[2] = v2[2] - v3[2]
  n[0] = n1[1] * n2[2] - n1[2] * n2[1]
  n[1] = n1[2] * n2[0] - n1[0] * n2[2]
  n[2] = n1[0] * n2[1] - n1[1] * n2[0]

  return normalize_v3(n)


# --- Ref Board
def cMat_to_pMat(L):
    M = Matrix()
    M[0][0] = L[0]
    M[0][1] = L[1]
    M[0][2] = L[2]
    M[0][3] = L[12] #L[3]

    M[1][0] = L[4]
    M[1][1] = L[5]
    M[1][2] = L[6]
    M[1][3] = L[13] #L[7]

    M[2][0] = L[8]
    M[2][1] = L[9]
    M[2][2] = L[10]
    M[2][3] = L[14] # L[11]

    M[3][0] = L[3]
    M[3][1] = L[7]
    M[3][2] = L[11]
    M[3][3] = L[15]

    return M


def flatten_matrix(mx):  # --- Перевести Py матрицу в C
    return [i for col in mx.col for i in col]


def reshape_matrix(mat, x, y):
    import numpy as np
    try:
        return np.reshape(mat, (y, x))
    except ValueError:
        return None
