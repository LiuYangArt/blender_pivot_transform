import bpy
from bpy.types import Operator
from mathutils import Matrix, Vector, Euler
from bpy.props import BoolProperty
import re

# скомпилировать регулярное выражение один раз
PATTERN = re.compile(r'(\d+)/\d+')


def bone_select():
    C = bpy.context

    if C.mode in {'EDIT_ARMATURE'}:
        viewlayer = C.view_layer
        collection = C.scene.statistics(viewlayer).split(" | ")

        verts_sel = collection[1]
        verts_str = verts_sel[6:].replace(',', '')
        verts_get = verts_str.split("/")[0]

        bone_sel = collection[2]
        bone_str = bone_sel[6:].replace(',', '')
        bone_get = bone_str.split("/")[0]

        verts, bones = int(verts_get), int(bone_get)

    elif C.mode in {'POSE'}:
        viewlayer = C.view_layer
        collection = C.scene.statistics(viewlayer).split(" | ")

        bone_sel = collection[1]
        bone_str = bone_sel[6:].replace(',', '')
        bone_get = bone_str.split("/")[0]

        verts, bones = 0, int(bone_get)

    else:
        verts, bones = 0, 0

    return verts, bones


def activate():
    context = bpy.context

    obj = context.object
    if obj is not None:
        if context.mode == 'OBJECT':
            return context.selected_objects

        elif context.mode in {'EDIT_MESH', 'EDIT_CURVE', 'EDIT_SURFACE', 'EDIT_ARMATURE', 'POSE'}:
            s = context.scene.statistics(context.view_layer)
            matches = PATTERN.findall(s)
            if matches:
                return int(matches[0]) > 0
            # elif context.mode == 'EDIT_ARMATURE':
            #     verts, bone = bone_select()
            #     if verts > 0:
            #         items = [ verts ]
            #     elif bone > 0:
            #         items = [ bone ]
            #     v = len(items)
            #     return v != 0

            # elif context.mode == 'POSE':
            #     bone = bone_select()[1]
            #     if bone > 0:
            #         items = [ bone ]
            #     v = len(items)
            #     return v != 0

            # elif context.mode == 'EDIT_CURVE':
            #     items = []
            #     for obj in context.selected_objects:
            #         for s in obj.data.splines:
            #             for p in s.bezier_points:
            #                 if p.select_control_point:
            #                     items.append(p)
            #                 else:
            #                     if p.select_left_handle:
            #                         items.append(p)
            #                     if p.select_right_handle:
            #                         items.append(p)
            #     v = len(items)
            #     return v != 0

        else:
            return False

    else:
        return False


# Delete Duplicate Vector
def del_duplicate(list):
    newList = []
    for i in list:
        if i not in newList:
            newList.append(i)
    return newList


# Change Pivot From Cursor
def cursorPivot(loc):
    context = bpy.context

    cursor_pos = context.scene.cursor.location.copy()
    context.scene.cursor.location = loc

    if context.mode == 'OBJECT':
        # вызываем операцию без добавления шага undo
        bpy.ops.object.origin_set('EXEC_DEFAULT', False, type='ORIGIN_CURSOR', center='MEDIAN')
        context.scene.cursor.location = cursor_pos

    else:
        bpy.ops.object.mode_set(mode='OBJECT')
        # вызываем операцию без добавления шага undo
        bpy.ops.object.origin_set('EXEC_DEFAULT', False, type='ORIGIN_CURSOR', center='MEDIAN')
        context.scene.cursor.location = cursor_pos
        bpy.ops.object.mode_set(mode='EDIT')






def set_pivot_location(
    context,
    location = None,
    cursor = False,
    undoPush = False,
    message = "Set Pivot Location",
    ):

    _cursor = context.scene.cursor
    if cursor is False:
        cursorPos = _cursor.location.copy()

    if location:
        _cursor.location = Vector(location)
    else:
        bpy.ops.view3d.snap_cursor_to_selected()

    edit_mode = False
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
        edit_mode = True

    # вызываем операцию без добавления шага undo
    bpy.ops.object.origin_set('EXEC_DEFAULT', False, type='ORIGIN_CURSOR', center='MEDIAN')

    if undoPush:
        bpy.ops.ed.undo_push(message=message)

    if edit_mode:
        bpy.ops.object.mode_set(mode='EDIT')

    if cursor is False:
        _cursor.location = cursorPos


def set_pivot_rotation(
    context,
    rotation = None,
    cursor = False,
    undoPush = False,
    message = "Set Pivot Rotation",
    ):

    _cursor = context.scene.cursor
    rotation_mode_orig = _cursor.rotation_mode
    cursor_rot_euler = _cursor.rotation_euler.copy()
    cursor_rot_quat = _cursor.rotation_quaternion.copy()

    userOrient = context.scene.transform_orientation_slots[0].type
    utdo = context.scene.tool_settings.use_transform_data_origin

    # --- Подготовка переданного вращения (поддержка Euler и Quaternion)
    rot_quat = None
    rot_euler = None
    if rotation is not None:
        from mathutils import Quaternion, Euler as _Euler
        if isinstance(rotation, Quaternion):
            rot_quat = rotation.copy()
        else:
            rot_euler = _Euler((rotation[0], rotation[1], rotation[2]), 'XYZ')

    # --- Устанавливаем вращение курсора
    if rot_quat is not None:
        _cursor.rotation_mode = 'QUATERNION'
        _cursor.rotation_quaternion = rot_quat
    elif rot_euler is not None:
        _cursor.rotation_mode = 'XYZ'
        _cursor.rotation_euler = rot_euler
    else:
        # rotation is None -> ориентируемся по текущему выделению/ориентиру
        pass

    if cursor is False:
        if rotation is None:
            bpy.ops.transform.create_orientation('EXEC_DEFAULT', False,  name = 'Pivot_Transform', use = True, overwrite = True )

        # --- Check Edit Mode
        editMode = False
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set( mode = 'OBJECT' )
            editMode = True


        # --- Set Pivot Rotation
        if rotation:
            context.scene.tool_settings.use_transform_data_origin = True
            bpy.ops.transform.transform('EXEC_DEFAULT', False,  mode = 'ALIGN', orient_type = 'CURSOR', orient_matrix_type = 'CURSOR' )
        else:
            context.scene.tool_settings.use_transform_data_origin = True
            bpy.ops.transform.transform('EXEC_DEFAULT', False,  mode = 'ALIGN', orient_type = 'Pivot_Transform', orient_matrix_type = 'Pivot_Transform' )


        # --- Restore UTDO
        context.scene.tool_settings.use_transform_data_origin = utdo

        # --- Update Undo
        if undoPush:
            bpy.ops.ed.undo_push( message = message )

        # --- Restore Mode
        if editMode:
            bpy.ops.object.mode_set( mode = 'EDIT' )

    else:
        _cursor.rotation_mode = 'QUATERNION'
        bpy.ops.transform.create_orientation('EXEC_DEFAULT', False,  name = 'Pivot_Transform', use = True, overwrite = True )
        mat = context.scene.transform_orientation_slots[0].custom_orientation.matrix.to_4x4()
        _cursor.rotation_quaternion = mat.decompose()[1]


    # --- Restore Cursor
    if cursor is False:
        _cursor.rotation_euler = cursor_rot_euler
        _cursor.rotation_quaternion = cursor_rot_quat
        _cursor.rotation_mode = rotation_mode_orig


    # --- Сброс к начальным настройкам пользовательских настроек
    if rotation is None:
        context.window.scene.transform_orientation_slots[0].type = 'Pivot_Transform'
        bpy.ops.transform.delete_orientation('EXEC_DEFAULT', False)
        context.window.scene.transform_orientation_slots[0].type = userOrient






# --- CURSOR TO ACTIVE
class OBJECT_OT_pt_cursor_to_active(Operator):
    bl_idname = 'object.pt_cursor_to_active'
    bl_label = '3D Cursor To Active'
    bl_description = 'Move and orient the 3D cursor to the selection'
    bl_options = {'UNDO', 'INTERNAL'} # 'REGISTER',


    position: BoolProperty(name='Position', default=True)
    rotation: BoolProperty(name='Rotation', default=True)
    to_pivot: BoolProperty(name='Snap To Pivot', default=True)


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        scene = bpy.context.window.scene
        cursor = scene.cursor

        self.init_mat = cursor.matrix
        self.init_orient = scene.transform_orientation_slots[0].type


    @staticmethod
    def cursor_orient(self, context):
        scene = context.window.scene
        cursor = scene.cursor
        cursor_pos = cursor.location.copy()
        name = 'GizmoPRO-3D_Cursor'
        scene.transform_orientation_slots[0].type = 'NORMAL'
        bpy.ops.transform.create_orientation('EXEC_DEFAULT', False, name=name, use=True, overwrite=True)
        user_matrix = scene.transform_orientation_slots[0].custom_orientation.matrix.to_4x4()
        cursor.matrix = Matrix.Translation(cursor_pos) @ user_matrix
        scene.transform_orientation_slots[0].type = name
        bpy.ops.transform.delete_orientation('EXEC_DEFAULT', False)
        scene.transform_orientation_slots[0].type = self.init_orient


    def execute(self, context):
        scene = context.window.scene
        cursor = scene.cursor
        cursor.matrix = self.init_mat

        s = context.scene.statistics(context.view_layer)
        matches = PATTERN.findall(s)

        if self.position:
            objs = context.selected_objects
            if context.mode=='EDIT_MESH' and len(objs)>0:
                if matches and int(matches[0]) == 0:
                    loc = [o.location for o in objs]
                    mid = sum(loc, Vector()) / len(loc)
                    cursor.location = mid
                else:
                    bpy.ops.view3d.snap_cursor_to_selected()
            else:
                bpy.ops.view3d.snap_cursor_to_selected()

        if self.rotation:
            objs = context.selected_objects
            if context.mode=='EDIT_MESH' and len(objs)>0:
                if matches and int(matches[0]) == 0:
                    l = cursor.location.copy()
                    q = context.active_object.matrix_world.decompose()[1]
                    s = Vector((1,1,1))
                    cursor.matrix = Matrix.LocRotScale(l, q, s)
                else:
                    self.cursor_orient(self, context)
            else:
                self.cursor_orient(self, context)
        return {'FINISHED'}


    def invoke(self, context, event):
        if event.ctrl and event.shift:
            self.position = True
            self.rotation = True
        elif event.ctrl:
            self.position = False
            self.rotation = True
        elif event.shift:
            self.position = True
            self.rotation = False
        else:
            self.position = True
            self.rotation = True
        return self.execute(context)

# --- ALIGN FROM VIEW
class OBJECT_OT_pt_align_from_view(Operator):
    bl_idname = 'object.pt_align_from_view'
    bl_label = '3D Cursor Align From View'
    bl_description = 'Align the 3D cursor to the current view'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def execute(self, context):
        cursor = context.scene.cursor
        rotation_mode = cursor.rotation_mode
        cursor.rotation_mode = 'QUATERNION'
        cursor.rotation_quaternion =  context.region_data.view_rotation
        cursor.rotation_mode = rotation_mode
        return {'FINISHED'}


# --- RESET 3D CURSOR
class OBJECT_OT_pt_reset_cursor(Operator):
    bl_idname = 'object.pt_reset_cursor'
    bl_label = 'Reset 3D Cursor'
    bl_description = 'Reset the 3D cursor; Ctrl applies the cursor transform to selected objects'
    bl_options = {'UNDO'} # 'REGISTER',

    loc: BoolProperty( name = 'Location', default = True )
    rot: BoolProperty( name = 'Position', default = True )


    @classmethod
    def description(self, context, properties):
        if properties.loc and properties.rot:
            return 'Reset cursor location and rotation; Ctrl applies both to selected objects'
        elif properties.loc:
            return 'Reset cursor location; Ctrl moves selected objects to the cursor'
        elif properties.rot:
            return 'Reset cursor rotation; Ctrl rotates selected objects to the cursor'
        return self.bl_description


    def invoke(self, context, event):

        if self.loc:
            if event.ctrl:
                cursorLoc = context.scene.cursor.location
                objs = context.selected_objects
                for ob in objs:
                    ob.location = cursorLoc
            else:
                context.scene.cursor.location = Vector()

        if self.rot:
            cursor = context.scene.cursor
            cursorMode = cursor.rotation_mode
            cursor.rotation_mode = 'XYZ'

            if event.ctrl:
                objs = context.selected_objects
                for ob in objs:
                    obMode = ob.rotation_mode
                    ob.rotation_mode = 'XYZ'
                    ob.rotation_euler = cursor.rotation_euler
                    ob.rotation_mode = obMode
            else:
                cursor.rotation_euler = Euler()

            cursor.rotation_mode = cursorMode
        return {'FINISHED'}




classes = [
    OBJECT_OT_pt_cursor_to_active,
    OBJECT_OT_pt_align_from_view,
    OBJECT_OT_pt_reset_cursor,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
