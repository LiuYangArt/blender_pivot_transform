import bpy


def get_selected_bone_objs(edit_mode=True):
    if edit_mode:
        return [obj for obj in bpy.context.objects_in_mode_unique_data if obj.type == 'ARMATURE']
    else:
        return [obj for obj in bpy.context.selected_objects if obj.type == 'ARMATURE']


def remove_duplicate_positions(points, tolerance=1e-5):
    unique_points = []
    for point in points:
        if not any((point - up).length < tolerance for up in unique_points):
            unique_points.append(point)
    return unique_points


def get_bone_points():
    selected_objs = get_selected_bone_objs(edit_mode=False)
    points = []
    for obj in selected_objs:
        armature = obj.data
        if bpy.context.mode == 'OBJECT':
            for pbone in obj.pose.bones:
                points.append(obj.matrix_world @ pbone.head)
                points.append(obj.matrix_world @ pbone.tail)
        elif bpy.context.mode == 'POSE':
            for pbone in obj.pose.bones:
                points.append(obj.matrix_world @ pbone.head)
                points.append(obj.matrix_world @ pbone.tail)
        elif bpy.context.mode == 'EDIT_ARMATURE':
            for eb in armature.edit_bones:
                points.append(obj.matrix_world @ eb.head)
                points.append(obj.matrix_world @ eb.tail)

    return points


def get_selected_bone_points():
    selected_objs = get_selected_bone_objs()
    points = []
    for obj in selected_objs:
        armature = obj.data
        if bpy.context.mode == 'POSE':
            for pbone in obj.pose.bones:
                if pbone.bone.select:
                    points.append(obj.matrix_world @ pbone.head)
                    points.append(obj.matrix_world @ pbone.tail)
        elif bpy.context.mode == 'EDIT_ARMATURE':
            for eb in armature.edit_bones:
                if eb.select_head or eb.select_tail:
                    if eb.select_head:
                        points.append(obj.matrix_world @ eb.head)
                    if eb.select_tail:
                        points.append(obj.matrix_world @ eb.tail)
    return points


def get_active_bone_el():
    if bpy.context.mode == 'POSE':
        return bpy.context.active_pose_bone
    elif bpy.context.mode == 'EDIT_ARMATURE':
        return bpy.context.active_bone


def get_main_parent_bones_head_positions():
    obj = bpy.context.object #active_object
    main_parents = []
    for pbone in bpy.context.selected_pose_bones:
        if pbone.parent is None or pbone.parent not in bpy.context.selected_pose_bones:
            main_parents.append(obj.matrix_world @ pbone.head)
    return main_parents
