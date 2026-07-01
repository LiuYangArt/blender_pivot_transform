import bpy
from bpy.types import Operator
from mathutils import Vector
from ..utils.utils import del_duplicate, cursorPivot, activate
from ..preferences import ADDON_PACKAGE
from bpy.props import EnumProperty, BoolProperty


def co_elements(obj, edit):
    co = []

    mw = obj.matrix_world

    if obj.type == 'MESH':
        co = [mw @ v.co for v in obj.data.vertices]
    elif obj.type == 'ARMATURE':
        coOld = []
        if edit:
            for bone in obj.data.bones:
                coOld.append(mw @ bone.head_local)
                coOld.append(mw @ bone.tail_local)
        else:
            for bone in obj.pose.bones:
                coOld.append(mw @ bone.head)
                coOld.append(mw @ bone.tail)

        co = del_duplicate(coOld)

    elif obj.type == 'CURVE':
        for s in obj.data.splines:
            for p in s.bezier_points:
                co.append(mw @ p.co)

    elif obj.type == 'SURFACE':
        for s in obj.data.splines:
            for p in s.points:
                co.append(mw @ p.co)

    elif obj.type == 'META':
        for e in obj.data.elements:
            co.append(mw @ e.co)

    elif obj.type == 'LATTICE':
        for p in obj.data.points:
            co.append(mw @ p.co)

    else:
        return False
    return co


class OBJECT_OT_pt_pivot_to_bottom(Operator):
    bl_idname = 'object.pt_pivot_to_bottom'
    bl_label = 'Pivot/Cursor To Bottom'
    bl_description = "Move the pivot or 3D cursor to the lowest point"
    # Undo управляется ВРУЧНУЮ (см. pivot_to_select.py / pivot_apply.py). Авто-флаг
    # 'UNDO' из Edit Mode пушит шаг в edit-стек (только bmesh), который НЕ хранит
    # obj.location/origin → при Ctrl+Z вершины откатываются, а origin остаётся
    # смещённым, и меш «уезжает». Выходим в Object Mode + один memfile-push до
    # изменений — он захватывает всё и даёт корректный однократный Ctrl+Z.
    bl_options = {'REGISTER'}

    drop_to_x: BoolProperty(name="Drop To X", default=False)
    drop_to_y: BoolProperty(name="Drop To Y", default=False)
    drop_to_z: BoolProperty(name="Drop To Z", default=False)

    mode: EnumProperty(
        name = 'Mode',
        items=[
            ("LOWEST_CENTER_POINT", "Lowest Median Center Point", "Use the center of the lowest bounding-box side"),
            ("LOWEST_ORIGIN_POINT", "Lowest Origin Point", "Keep origin X/Y and use the lowest geometry Z"),
            ("LOWEST_VERT_POINT", "Lowest Vertex Point", "Use the average position of the lowest vertices"),
            ],
            )
    use_modifier: BoolProperty(name="Use Modifier")
    drop_to_active: BoolProperty(name="Drop To Active", default=False)

    cursor: BoolProperty(name="3D Cursor", description="Move only the 3D cursor", default=False)

    @classmethod
    def poll(self, context):
        return activate()

    def execute(self, context):
        # --- Выходим в Object Mode (flush bmesh → mesh). co_elements() читает
        #     obj.data.vertices, поэтому выход из edit ОБЯЗАН быть до вычислений.
        #     `edit` сохраняет, был ли пользователь в Edit Mode (нужно для armature
        #     в co_elements: edit-кости vs pose-кости).
        restore_mode = None
        edit = False
        if context.object.mode != 'OBJECT':
            restore_mode = context.object.mode
            edit = (restore_mode == 'EDIT')
            bpy.ops.object.mode_set('EXEC_DEFAULT', False, mode='OBJECT')

        # --- memfile-снимок ВСЕЙ сцены до изменений (корректный Ctrl+Z)
        bpy.ops.ed.undo_push(message="Pivot To Bottom")

        activeObj = context.active_object
        selObject = context.selected_objects

        # снимаем выделение напрямую (без bpy.ops, чтобы не плодить шаги undo)
        for o in selObject:
            o.select_set(False)

        for obj in selObject:
            obj.select_set(state=True)

            # get
            if self.use_modifier and obj.type == 'MESH':
                depsgraph = context.evaluated_depsgraph_get()
                object_eval = obj.evaluated_get(depsgraph)
                co = co_elements(object_eval, edit=edit)
            else:
                co = co_elements(obj, edit=edit)

            # set
            if co:
                if self.mode == 'LOWEST_CENTER_POINT':
                    x = (min([v.x for v in co]) + max([v.x for v in co])) / 2
                    y = (min([v.y for v in co]) + max([v.y for v in co])) / 2
                    z = min([v.z for v in co])
                    global_origin = Vector((x, y, z))

                elif self.mode == 'LOWEST_ORIGIN_POINT':
                    loc = obj.location
                    x = loc[0]
                    y = loc[1]
                    z = min([v.z for v in co])
                    global_origin = Vector((x, y, z))

                elif self.mode == 'LOWEST_VERT_POINT':
                    z = min([v.z for v in co])
                    x = sum([v.x for v in co if v.z == z]) / len([v.x for v in co if v.z == z])
                    y = sum([v.y for v in co if v.z == z]) / len([v.y for v in co if v.z == z])
                    global_origin = Vector((x, y, z))

                if self.cursor:
                    context.scene.cursor.location = global_origin
                else:
                    cursorPivot(global_origin)
                    obj.select_set(state=False)

        # restore
        if self.cursor is False:
            for obj in selObject:
                obj.select_set(state=True)

                if self.drop_to_x:
                    obj.location[0] = 0.0
                if self.drop_to_y:
                    obj.location[1] = 0.0
                if self.drop_to_z:
                    obj.location[2] = 0.0

        context.view_layer.objects.active = activeObj

        if self.drop_to_active and self.cursor is False:
            props = context.preferences.addons[ADDON_PACKAGE].preferences
            bpy.ops.object.pt_pivot_to_select(
                'EXEC_DEFAULT',
                False,
                axis=props.TS_axis,
                align=props.align_to,
                push_undo=False,
            )

        # --- возвращаем исходный режим
        if restore_mode is not None:
            bpy.ops.object.mode_set('EXEC_DEFAULT', False, mode=restore_mode)

        return {'FINISHED'}

    def invoke(self, context, event):
        props = context.preferences.addons[ADDON_PACKAGE].preferences

        self.cursor = event.ctrl

        self.drop_to_x = props.drop_to_x
        self.drop_to_y = props.drop_to_y
        self.drop_to_z = props.drop_to_z

        self.mode = props.TB_mode

        self.use_modifier = props.TB_use_modifier
        self.drop_to_active = props.drop_to_active

        return self.execute(context)

    def draw(self, context):
        layout = self.layout
        row = layout.row( align = True )
        row.label(text="Drop To")
        row.prop(self, 'drop_to_x', text="X", toggle=True)
        row.prop(self, 'drop_to_y', text="Y", toggle=True)
        row.prop(self, 'drop_to_z', text="Z", toggle=True)
        layout.prop(self, 'mode')
        layout.prop(self, 'use_modifier')
        layout.prop(self, 'drop_to_active')
        layout.prop(self, 'cursor')


classes = [
    OBJECT_OT_pt_pivot_to_bottom,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
