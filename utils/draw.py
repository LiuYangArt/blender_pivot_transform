import bpy
from math import sin, cos, pi, sqrt
from mathutils import Matrix, Vector



def draw_cross(x=1, y=1):
    l = 0.4
    """ co = [
        (x, 0, 0), (-x, 0, 0),
        (0, y, 0), (0, -y, 0),
        ] """
    co = [
        (x, 0, 0), (l, 0, 0),
        (-l, 0, 0), (-x, 0, 0),
        (0, y, 0), (0, l, 0),
        (0, -l, 0), (0, -y, 0),
        ]
    return co


def draw_box(scale=1):
    verts = [
        (-1.0000, -1.0000, 1.0000), (-1.0000, 1.0000, -1.0000), (-1.0000, -1.0000, -1.0000),
        (-1.0000, 1.0000, 1.0000), (1.0000, 1.0000, -1.0000), (-1.0000, 1.0000, -1.0000),
        (1.0000, 1.0000, 1.0000), (1.0000, -1.0000, -1.0000), (1.0000, 1.0000, -1.0000),
        (1.0000, -1.0000, 1.0000), (-1.0000, -1.0000, -1.0000), (1.0000, -1.0000, -1.0000),
        (1.0000, 1.0000, -1.0000), (-1.0000, -1.0000, -1.0000), (-1.0000, 1.0000, -1.0000),
        (-1.0000, 1.0000, 1.0000), (1.0000, -1.0000, 1.0000), (1.0000, 1.0000, 1.0000),
        (-1.0000, -1.0000, 1.0000), (-1.0000, 1.0000, 1.0000), (-1.0000, 1.0000, -1.0000),
        (-1.0000, 1.0000, 1.0000), (1.0000, 1.0000, 1.0000), (1.0000, 1.0000, -1.0000),
        (1.0000, 1.0000, 1.0000), (1.0000, -1.0000, 1.0000), (1.0000, -1.0000, -1.0000),
        (1.0000, -1.0000, 1.0000), (-1.0000, -1.0000, 1.0000), (-1.0000, -1.0000, -1.0000),
        (1.0000, 1.0000, -1.0000), (1.0000, -1.0000, -1.0000), (-1.0000, -1.0000, -1.0000),
        (-1.0000, 1.0000, 1.0000), (-1.0000, -1.0000, 1.0000), (1.0000, -1.0000, 1.0000),
    ]

    # apply size
    for i, v in enumerate(verts):
        verts[i] = v[0] * scale, v[1] * scale, v[2] * scale


    #print(faces[:])
    return verts


def draw_circle_2d(segments=60):
    mx = 0
    my = 0
    radius = 1


    prefs = bpy.context.preferences.system
    radius = radius * (prefs.dpi * prefs.pixel_size / 72)

    vertices = [(radius * cos(i * 2 * pi / segments) + mx,
                 radius * sin(i * 2 * pi / segments) + my)
                 for i in range(segments + 1)]
    return vertices



def draw_circle_3d(position, radius, segments=60, matrix=None):
    mx = position[0]
    my = position[1]
    mz = position[2]

    prefs = bpy.context.preferences.system
    radius = radius * (prefs.dpi * prefs.pixel_size / 72)

    if matrix == None:
        vertices = [(radius * cos(i * 2 * pi / segments) + mx,
                    radius * sin(i * 2 * pi / segments) + my,
                    mz)
                    for i in range(segments + 1)]
    else:
        #qat = bpy.context.region_data.view_matrix.inverted().decompose()[1]
        vertices = [Vector((radius * cos(i * 2 * pi / segments) + mx,
                                     radius * sin(i * 2 * pi / segments) + my,
                                     mz))
                for i in range(segments + 1)]

    return vertices



def draw_circle_2d_filled():
    mx = 0
    my = 0
    radius = 1

    prefs = bpy.context.preferences.system
    radius = radius * (prefs.dpi * prefs.pixel_size / 72)
    sides = 32
    vertices = [(radius * cos(i * 2 * pi / sides) + mx,
                 radius * sin(i * 2 * pi / sides) + my)
                 for i in range(sides + 1)]

    return vertices



def draw_ring_2d(position, outRad, inerRad):
    mx = position[0]
    my = position[1]


    sides = 60


    ring1 = []
    ring2 = []
    verts = []
    faces = []

    for i in range(sides):
        grad = (360 * i / sides) * pi / 180
        ring1.append([outRad * cos(grad) + mx, outRad * sin(grad) + my])
        ring2.append([inerRad * cos(grad) + mx, inerRad * sin(grad) + my])


        end = sides - 1
        if i == end:
            faces.append([i, i+1, i+sides])
            faces.append([i, i+1, i-i])
        else:
            faces.append([i, i+1, i+1+sides])
            faces.append([i, i+sides, i+1+sides])

    verts.extend(ring1)
    verts.extend(ring2)

    return verts












# classes = []


# def register():
#     for cls in classes:
#         bpy.utils.register_class(cls)


# def unregister():
#     for cls in reversed(classes):
#         bpy.utils.unregister_class(cls)