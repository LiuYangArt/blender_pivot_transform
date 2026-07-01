import bpy
import bmesh
from mathutils import Matrix, Vector
from .math import (
    copy_v3_v3,
    cross_v3_v3v3,
    is_zero_v3,
    negate_v3_v3,
    normalize_v3_v3,
    normalize_v3,
    )



def uniq_edge(lens):
    difs = [abs(lens[1] - lens[2])]
    difs.append(abs(lens[2] - lens[0]))
    difs.append(abs(lens[0] - lens[1]))

    eDic = {0:difs[0], 1:difs[1], 2:difs[2]}
    index = min(eDic, key=eDic.get)

    return index


def tangent(elem):
    loops = elem.loops
    edges = [l.edge for l in loops]
    lens = [e.calc_length() for e in edges]

    index = uniq_edge(lens)
    edge = edges[index]

    loop = [l for l in loops if l.edge == edge][0]

    return loop.vert.co - edge.other_vert(loop.vert).co


def get_active(el):
    ob_mat = bpy.context.object.matrix_world.copy()
    mw = ob_mat.transposed().inverted()


    if isinstance(el, bmesh.types.BMVert):
        normal = el.normal
        edges = el.link_edges
        loops = el.link_loops
        tang = Vector((0.0,0.0,1.0))



        if normal == tang or normal == Vector((0.0,0.0,-1.0)):
            tang = Vector((-1.0,0.0,0.0))

        if len(edges) >= 2:
            eBoundary = loops[0].edge if len(loops) > 0 else edges[0]

            if eBoundary.is_boundary and len(edges) == 2:
                vPair = [edges[0].other_vert(el), edges[1].other_vert(el)]

                if edges[0].link_loops[0].vert != el:
                    vPair[0], vPair[1] = vPair[1], vPair[0]

                dir01 = (ob_mat @ el.co - ob_mat @ vPair[0].co).normalized()
                dir02 = (ob_mat @ vPair[1].co - ob_mat @ el.co).normalized()
                plane = normal.cross(dir01 + dir02).normalized()
            else:
                plane = normal.cross(tang).normalized()
                plane = mw @ plane
        else:
            plane = normal.cross(tang).normalized()
            plane = mw @ plane

        # Covert to object space
        normal = mw @ normal

        tangent = normal.cross(plane).normalized()
        perpVec = tangent.cross(normal).normalized() # To make sure for right angles




    if isinstance(el, bmesh.types.BMEdge):
        v01, v02 = [v for v in el.verts]

        # Get  average normal
        avrNormal = ((v01.normal + v02.normal) * 0.5)

        # Covert to object space
        tangent = ob_mat @ Vector(v01.co) - ob_mat @ Vector(v02.co)
        avrNormal = mw @ avrNormal

        perpVec = tangent.cross(avrNormal).normalized()
        normal = tangent.cross(perpVec).normalized()
        normal.negate()

    if isinstance(el, bmesh.types.BMFace):
        normal = el.normal

        if len(el.verts) == 3:
            # OK for now # TODO fix occasional mismaches in some tris
            plane = tangent(el).normalized()

        elif len(el.verts) == 4:
            plane = el.calc_tangent_edge_pair().normalized() # OK
        else:
            plane = el.calc_tangent_edge().normalized() # OK

        # TODO does it work?
        if plane[0] == 0.0 and plane[1] == 0.0 and plane[2] == 0.0:
            plane[2] = 1.0

        # Covert to object space
        normal = mw @ normal
        plane = mw @ plane

        perpVec = normal.cross(plane).normalized()
        tangent = normal.cross(perpVec).normalized() # To make sure for right angles



    # To make sure is everything is normalized
    perpVec.normalize()
    tangent.normalize()
    normal.normalize()

    #print('perpVec', perpVec)
    #print('tangent', tangent)
    #print('normal', normal)

    return Matrix((perpVec, tangent, normal)).transposed().to_4x4()


def createSpaceNormal(mat, normal):
    tangent = Vector((0,0,1))

    copy_v3_v3(mat[2], normal)

    if normalize_v3(mat[2]) == 0:
        return False

    cross_v3_v3v3(mat[0], mat[2], tangent)
    if is_zero_v3(mat[0]):
        tangent = Vector((1,0,0))
        cross_v3_v3v3(mat[0], tangent, mat[2])

    cross_v3_v3v3(mat[1], mat[2], mat[0])

    return True


def createSpaceNormalTangent(mat, normal, tangent):
    if normalize_v3_v3(mat[2], normal) == 0.0:
        return False

    negate_v3_v3(mat[1], tangent)
    if is_zero_v3(mat[1]):
        mat[1][2] = 1.0

    cross_v3_v3v3(mat[0], mat[2], mat[1])

    if normalize_v3(mat[0]) == 0.0:
        return False

    cross_v3_v3v3(mat[1], mat[2], mat[0])
    normalize_v3(mat[1])

    return True
