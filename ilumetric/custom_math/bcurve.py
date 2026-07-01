import bpy


def _point_selected(p):
    """Selection flag for a POLY/NURBS spline point.

    ``bpy.types.SplinePoint`` exposes ``select_control_point`` – there is no
    plain ``select`` (that only exists on mesh verts), so reading ``p.select``
    raises AttributeError and silently breaks curve/surface selection queries.
    Fall back to ``select`` defensively in case the API name ever changes.
    """
    sel = getattr(p, 'select_control_point', None)
    if sel is None:
        sel = getattr(p, 'select', False)
    return sel


def get_selected_curve_objs(edit_mode=True):
    if edit_mode:
        return [obj for obj in bpy.context.objects_in_mode_unique_data if obj.type in {'CURVE', 'SURFACE'}]
    else:
        return [obj for obj in bpy.context.selected_objects if obj.type in {'CURVE', 'SURFACE'}]


def get_curve_points():
    sObs = get_selected_curve_objs(edit_mode=False)
    points = []
    for ob in sObs:
        curve = ob.data
        for spline in curve.splines:
            if spline.type == 'BEZIER':
                for p in spline.bezier_points:
                    points.append(ob.matrix_world @ p.co)
            elif spline.type in {'POLY', 'NURBS'}:
                for p in spline.points:
                    points.append(ob.matrix_world @ p.co.xyz)
    return points


def get_selected_curve_points():
    sObs = get_selected_curve_objs()
    points = []
    for ob in sObs:
        curve = ob.data
        for spline in curve.splines:
            if spline.type == 'BEZIER':
                for p in spline.bezier_points:
                    if p.select_control_point:
                        points.append(ob.matrix_world @ p.co)
                    else:
                        if p.select_left_handle:
                            points.append(ob.matrix_world @ p.handle_left)
                        if p.select_right_handle:
                            points.append(ob.matrix_world @ p.handle_right)
            elif spline.type in {'POLY', 'NURBS'}:
                for p in spline.points:
                    if _point_selected(p):
                        points.append(ob.matrix_world @ p.co.xyz)
    return points


def get_selected_curve_points_el():
    sObs = get_selected_curve_objs()
    el = []
    for ob in sObs:
        curve = ob.data
        for spline in curve.splines:
            if spline.type == 'BEZIER':
                for p in spline.bezier_points:
                    if p.select_control_point:
                        el.append([ob, p, 'BEZIER'])
                    else:
                        if p.select_left_handle:
                            el.append([ob, p, 'L_HANDLE'])
                        if p.select_right_handle:
                            el.append([ob, p, 'R_HANDLE'])
            elif spline.type in {'POLY', 'NURBS'}:
                for p in spline.points:
                    if _point_selected(p):
                        el.append([ob, p, 'NURBS'])
    return el


# --- Select History
def update_list(list_h, list_a):
    # Добавление отсутствующих элементов из list_a в list_h
    for item in list_a:
        if item not in list_h:
            list_h.append(item)
    # Удаление элементов из list_h, которых нет в list_a
    list_h[:] = [item for item in list_h if item in list_a]


def compare_lists_by_length(list1, list2):
    diff = abs(len(list1) - len(list2))
    if diff == 0:
        return 0
    elif diff <= 1:
        return 1
    else:
        return 2


history_selected_curve_elements = ['ACTIVE', []]


def get_last_selected_point_curve_el():
    global history_selected_curve_elements

    selected_points = get_selected_curve_points_el()

    dif = compare_lists_by_length(history_selected_curve_elements[1], selected_points)
    update_list(history_selected_curve_elements[1], selected_points)
    if dif == 0:
        return history_selected_curve_elements[0], history_selected_curve_elements[1][-1]

    elif dif == 1:
        history_selected_curve_elements[0] = 'ACTIVE'
        return 'ACTIVE', history_selected_curve_elements[1][-1]
    else:
        history_selected_curve_elements[0] = 'MIDDLE'
        history_selected_curve_elements[1] = selected_points
        return 'MIDDLE', history_selected_curve_elements[1][-1]
