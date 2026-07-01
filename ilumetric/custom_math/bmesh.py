from mathutils import Vector
import bmesh
from .math import (
    sub_v3_v3v3,
    mid_v3_v3v3,
    sub_v3_v3,
    len_squared_v3v3,
    axis_sort_v3,
)


def is_edge_boundary(e):
    # Граничным считается ребро, у которого ровно одна грань в link_faces
    return len(e.link_faces) == 1


# --- bmesh_polygon
def vert_tri_find_unique_edge(verts):
    difs = Vector()

    i_next = 0
    while i_next < 3:
        if i_next == 0:
            i_prev = 1
            i_curr = 2

        elif i_next == 1:
            i_prev = 2
            i_curr = 0

        elif i_next == 2:
            i_prev = 0
            i_curr = 1


        co = verts[i_curr].co
        co_other = [ verts[i_prev].co, verts[i_next].co ]



        proj_dir = mid_v3_v3v3(co_other[0], co_other[1])
        sub_v3_v3(proj_dir, co)

        proj_pair = [ Vector(), Vector() ]
        proj_pair[0] = co_other[0].project(proj_dir)
        proj_pair[1] = co_other[1].project(proj_dir)

        difs[i_next] = len_squared_v3v3(proj_pair[0], proj_pair[1])

        i_next += 1


    ''' lens = Vector(
        (
            len_v3v3(verts[0].co, verts[1].co),
            len_v3v3(verts[1].co, verts[2].co),
            len_v3v3(verts[2].co, verts[0].co),
        )
    )

    difs = Vector(
        (
            abs(lens[1] - lens[2]),
            abs(lens[2] - lens[0]),
            abs(lens[0] - lens[1]),
        )
    ) '''

    order = Vector((0,1,2))
    axis_sort_v3(difs, order)

    return order[0]


def vert_tri_calc_tangent_edge(verts): # BM
    i = vert_tri_find_unique_edge(verts)
    i = int(i)

    r_tangent = Vector()
    sub_v3_v3v3(r_tangent, verts[i].co, verts[(i + 1) % 3].co)

    r_tangent.normalize()
    return r_tangent


def face_as_array_vert_tri(f):
    r_verts = []
    l = f.loops[0]

    r_verts.append(l.vert)

    l = l.link_loop_next
    r_verts.append(l.vert)

    l = l.link_loop_next
    r_verts.append(l.vert)

    return r_verts


def bm_face_calc_tangent_auto(f):
    """
    Аналог BM_face_calc_tangent_auto для меша.
    Для треугольника, квадрата и n-гона разные стратегии.
    """

    r_tangent = Vector()
    if len(f.verts) == 3:
        verts = face_as_array_vert_tri(f)
        r_tangent = vert_tri_calc_tangent_edge(verts)

    elif len(f.verts) == 4:
        r_tangent = f.calc_tangent_edge_pair()

    else:
        r_tangent = f.calc_tangent_edge()

    return r_tangent


def bm_editselection_normal(ele):
    """
    Аналог BM_editselection_normal для меша.
    Возвращает Vector нормали элемента (вершина/ребро/грань).
    """
    if isinstance(ele, bmesh.types.BMVert):
        # Для вершины просто возвращаем нормаль вершины.
        return ele.normal.copy()
    elif isinstance(ele, bmesh.types.BMEdge):
        # Для ребра: r_normal = (1.no + v2.no)
        r_normal = ele.verts[0].normal + ele.verts[1].normal
        plane = ele.verts[1].co - ele.verts[0].co

        # Коррекция нормали для ребра:
        # vec = r_normal × plane
        vec = r_normal.cross(plane)
        # r_normal = plane × vec
        r_normal = plane.cross(vec)
        r_normal.normalize()
        return r_normal
    elif isinstance(ele, bmesh.types.BMFace):
        # Для грани просто возвращаем её нормаль.
        return ele.normal.copy()
    else:
        # Неизвестный тип
        return Vector((0.0, 0.0, 0.0))


def bm_editselection_plane(ele, prev_ele=None):
    """
    Аналог BM_editselection_plane для меша.
    Возвращает Vector "плоскости" для элемента.
    Если prev_ele указан, то для вершины используется этот элемент для формирования вектора.
    """
    if isinstance(ele, bmesh.types.BMVert):
        eve = ele
        if prev_ele is not None:
            vec = bm_editselection_center(prev_ele)
            r_plane = vec - eve.co
        else:
            # Если предыдущего элемента нет, формируем фиктивный вектор, перпендикулярный нормали вершины.
            eve_no = eve.normal
            vec = Vector((0.0,0.0,0.0))
            if abs(eve_no.x) < 0.5:
                vec.x = 1.0
            elif abs(eve_no.y) < 0.5:
                vec.y = 1.0
            else:
                vec.z = 1.0
            r_plane = eve_no.cross(vec)

        r_plane.normalize()
        return r_plane

    elif isinstance(ele, bmesh.types.BMEdge):
        eed = ele
        # Если ребро граничное:
        if len(eed.link_faces) == 1:
            # Используем петлю: l и l.next
            l = eed.link_faces[0].loops[0]
            # Ищем какую петлю взять для корректной логики
            # В C-коде используется eed->l->v и eed->l->next->v
            # Здесь можно попробовать найти loop, соответствующий eed
            loop_for_edge = None
            for loop in eed.link_faces[0].loops:
                if loop.edge == eed:
                    loop_for_edge = loop
                    break
            if loop_for_edge is not None:
                r_plane = loop_for_edge.vert.co - loop_for_edge.link_loop_next.vert.co
            else:
                # fallback: просто направление ребра
                v1co = eed.verts[0].co
                v2co = eed.verts[1].co
                r_plane = (v2co - v1co) if (v2co.y > v1co.y) else (v1co - v2co)
        else:
            # Не граничное ребро. Логика из C-кода: выбирать направление в зависимости от позиции по Y.
            v1co = eed.verts[0].co
            v2co = eed.verts[1].co
            if v2co.y > v1co.y:
                r_plane = v2co - v1co
            else:
                r_plane = v1co - v2co

        r_plane.normalize()
        return r_plane

    elif isinstance(ele, bmesh.types.BMFace):
        efa = ele
        r_plane = bm_face_calc_tangent_auto(efa)
        return r_plane

    return Vector((0.0, 0.0, 0.0))



##################################
def bm_editselection_center(ele):
    """
    Вспомогательная функция для вычисления центра элемента.
    Центр вершины — её координаты.
    Центр ребра — среднее координат вершин.
    Центр грани — медианный центр (f.calc_center_median()).
    """
    if isinstance(ele, bmesh.types.BMVert):
        return ele.co.copy()
    elif isinstance(ele, bmesh.types.BMEdge):
        return (ele.verts[0].co + ele.verts[1].co) * 0.5
    elif isinstance(ele, bmesh.types.BMFace):
        return ele.calc_center_median()
    return Vector((0.0,0.0,0.0))


def bm_vert_tri_calc_tangent_edge(v_co):
    """
    Аналог BM_vert_tri_calc_tangent_edge.
    Возвращаем тангенциальный вектор для треугольника.
    Простой способ: взять самое длинное ребро.
    """
    edges = [
        (v_co[1]-v_co[0]),
        (v_co[2]-v_co[1]),
        (v_co[0]-v_co[2])
    ]
    longest_edge = max(edges, key=lambda e: e.length)
    return longest_edge.normalized()


def bm_face_calc_tangent_edge_pair(v_co):
    """
    Аналог BM_face_calc_tangent_edge_pair для четырехугольника.
    Определяем пару противоположных рёбер с наибольшей суммарной длиной.
    К примеру:
    Пары: (v0v1 + v2v3) и (v1v2 + v3v0)
    """
    e1 = (v_co[1]-v_co[0])
    e2 = (v_co[2]-v_co[1])
    e3 = (v_co[3]-v_co[2])
    e4 = (v_co[0]-v_co[3])

    pair1_length = e1.length + e3.length
    pair2_length = e2.length + e4.length

    if pair1_length >= pair2_length:
        # Возьмём сумму векторов двух противоположных рёбер
        return (e1 + e3).normalized()
    else:
        return (e2 + e4).normalized()


def bm_face_calc_tangent_edge(v_co):
    """
    Аналог BM_face_calc_tangent_edge для n-gon.
    Берём самое длинное ребро n-угольника.
    """
    max_length = -1.0
    best_vec = Vector((0,0,0))
    count = len(v_co)
    for i in range(count):
        e_vec = v_co[(i+1) % count] - v_co[i]
        length = e_vec.length
        if length > max_length:
            max_length = length
            best_vec = e_vec
    return best_vec.normalized()
##########################################



# --- bmesh_marking
# --- Get the active mesh element (with active-face fallback)
def select_history_active_get(bm):
    ese_last = bm.select_history.active
    bm.faces.ensure_lookup_table()
    efa = bm.faces.active

    if ese_last:
        # --- If there is an active face, use it over the last selected face
        if isinstance(ese_last, bmesh.types.BMFace):
            if efa:
                return efa
            else:
                return ese_last
        else:
            return ese_last

    elif efa:
        # --- no edit-selection, fallback to active face
        sv = set([v for v in bm.verts if v.select])
        svf = set([v for v in efa.verts])

        if svf.issubset(sv):
            return efa
        else:
            return None
    else:
        return None
