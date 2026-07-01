import bpy
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty
from mathutils import Quaternion
from ..utils.utils import activate
from ..preferences import ADDON_PACKAGE


class OBJECT_OT_pt_pivot_to_select(Operator):
    bl_idname = 'object.pt_pivot_to_select'
    bl_label = 'Pivot To Select'
    bl_description = "Move the pivot to the active object or selected elements"
    # Undo управляется ВРУЧНУЮ (см. pivot_apply.py). В Blender два раздельных
    # стека undo: edit-mode (только bmesh/вершины) и memfile (object mode — ВСЁ:
    # данные меша + obj.location/rotation/scale + режим). Установка origin меняет
    # И вершины, И obj.matrix_world. Если оставить авто-флаг 'UNDO' и запускать
    # оператор из Edit Mode, Blender пушит шаг в edit-стек, который НЕ хранит
    # каналы трансформации → при Ctrl+Z вершины откатываются, а origin остаётся
    # смещённым, и меш визуально «уезжает». Поэтому: убираем 'UNDO'. В Edit Mode
    # выходим в Object Mode и делаем memfile-push до изменений; в Object Mode
    # пушим после операции, ближе к стандартному object-mode 'UNDO'.
    bl_options = {'REGISTER'} # 'BLOCKING'

    # Свойство задаётся из UI. В Object Mode ограничивает перенос origin одной
    # координатой; в Edit Mode не используется.
    axis: EnumProperty(
        name='Axis',
        description='Object Mode: choose which coordinates match the active object',
        items=[
            ('X', 'X', 'Match only the X coordinate', '', 0),
            ('Y', 'Y', 'Match only the Y coordinate', '', 1),
            ('Z', 'Z', 'Match only the Z coordinate', '', 2),
            ('ALL', 'All', 'Match all coordinates', '', 3),
        ],
        default='ALL',
    )
    align: BoolProperty(name="Align", description="Align the pivot to the active object or selection normal", default=True)
    push_undo: BoolProperty(name="Push Undo", default=True, options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(self, context):
        return activate()

    def _object_axis_target(self, obj, active_loc):
        if self.axis == 'ALL':
            return active_loc.copy()

        axis_indices = {'X': 0, 'Y': 1, 'Z': 2}
        axis_index = axis_indices.get(self.axis)
        if axis_index is None:
            return active_loc.copy()

        loc, _rot, _sca = obj.matrix_world.decompose()
        target = loc.copy()
        target[axis_index] = active_loc[axis_index]
        return target

    def _selection_orientation_quat(self, context):
        """Кватернион ориентации по нормали выделения.

        Создаём временную transform-ориентацию, читаем её матрицу и тут же
        удаляем, возвращая пользовательскую ориентацию. Вызывается в Edit Mode
        ДО undo_push, поэтому сцена остаётся чистой в снимке undo.
        """
        scene = context.scene
        slots = scene.transform_orientation_slots[0]
        user_orient = slots.type
        quat = Quaternion()
        try:
            bpy.ops.transform.create_orientation('EXEC_DEFAULT', False,
                                                 name='Pivot_Transform', use=True, overwrite=True)
            custom = slots.custom_orientation
            if custom is not None:
                quat = custom.matrix.to_4x4().to_quaternion()
            slots.type = 'Pivot_Transform'
            bpy.ops.transform.delete_orientation('EXEC_DEFAULT', False)
        except Exception:
            pass
        finally:
            try:
                slots.type = user_orient
            except Exception:
                pass
        return quat

    def execute(self, context):
        scene = context.scene
        cursor = scene.cursor
        started_in_object_mode = context.mode == 'OBJECT'

        # --- Фаза 1: вычисляем цель (позиция + ориентация origin) БЕЗ постоянных
        #     изменений сцены. Всё, что трогаем здесь, восстанавливаем до undo_push,
        #     чтобы memfile-снимок отражал исходное состояние сцены.
        target_loc = None
        target_quat = Quaternion()  # по умолчанию — мировые оси (Align off)
        object_axis_targets = None

        if context.mode == 'OBJECT':
            active_obj = context.active_object
            loc, rot, _sca = active_obj.matrix_world.decompose()
            target_loc = loc
            if self.axis != 'ALL':
                object_axis_targets = [
                    (obj, self._object_axis_target(obj, loc))
                    for obj in context.selected_objects
                ]
            if self.align:
                target_quat = rot
        else:
            # Edit Mode: позиция — медиана выделения, ориентация — по нормали.
            cur_loc = cursor.location.copy()
            cur_mode = cursor.rotation_mode
            cur_eul = cursor.rotation_euler.copy()
            cur_quat = cursor.rotation_quaternion.copy()

            bpy.ops.view3d.snap_cursor_to_selected()
            target_loc = cursor.location.copy()
            if self.align:
                target_quat = self._selection_orientation_quat(context)

            # возвращаем курсор в исходное состояние ДО снимка undo
            cursor.location = cur_loc
            cursor.rotation_euler = cur_eul
            cursor.rotation_quaternion = cur_quat
            cursor.rotation_mode = cur_mode

        # --- Фаза 2: для Edit Mode выходим в Object Mode (flush bmesh → mesh) и
        #     делаем memfile undo-снимок ВСЕЙ сцены до изменений origin. В чистом
        #     Object Mode push делается после операции, ближе к обычному 'UNDO'.
        restore_mode = None
        if context.mode != 'OBJECT':
            restore_mode = context.object.mode
            bpy.ops.object.mode_set('EXEC_DEFAULT', False, mode='OBJECT')

        if self.push_undo and not started_in_object_mode:
            bpy.ops.ed.undo_push(message="Pivot To Select")

        # --- Фаза 3: ставим курсор в цель и применяем origin (location + rotation).
        utdo = scene.tool_settings.use_transform_data_origin
        cur_loc = cursor.location.copy()
        cur_mode = cursor.rotation_mode
        cur_eul = cursor.rotation_euler.copy()
        cur_quat = cursor.rotation_quaternion.copy()

        cursor.location = target_loc
        cursor.rotation_mode = 'QUATERNION'
        cursor.rotation_quaternion = target_quat

        # location: origin -> cursor
        if object_axis_targets:
            selected_objects = list(context.selected_objects)
            active_obj = context.view_layer.objects.active

            for obj in selected_objects:
                obj.select_set(False)

            for obj, obj_target in object_axis_targets:
                cursor.location = obj_target
                obj.select_set(True)
                context.view_layer.objects.active = obj
                bpy.ops.object.origin_set('EXEC_DEFAULT', False, type='ORIGIN_CURSOR', center='MEDIAN')
                obj.select_set(False)

            for obj in selected_objects:
                obj.select_set(True)
            context.view_layer.objects.active = active_obj
        else:
            bpy.ops.object.origin_set('EXEC_DEFAULT', False, type='ORIGIN_CURSOR', center='MEDIAN')

        # rotation: origin выравнивается по ориентации курсора, геометрия на месте
        scene.tool_settings.use_transform_data_origin = True
        bpy.ops.transform.transform('EXEC_DEFAULT', False, mode='ALIGN',
                                    orient_type='CURSOR', orient_matrix_type='CURSOR')
        scene.tool_settings.use_transform_data_origin = utdo

        # восстанавливаем курсор
        cursor.location = cur_loc
        cursor.rotation_euler = cur_eul
        cursor.rotation_quaternion = cur_quat
        cursor.rotation_mode = cur_mode

        # --- Фаза 4: возвращаем исходный режим
        if restore_mode is not None:
            bpy.ops.object.mode_set('EXEC_DEFAULT', False, mode=restore_mode)

        if self.push_undo and started_in_object_mode:
            bpy.ops.ed.undo_push(message="Pivot To Select")

        return {'FINISHED'}

    def invoke(self, context, event):
        props = context.preferences.addons[ADDON_PACKAGE].preferences
        if context.mode == 'OBJECT':
            self.axis = props.TS_axis
        self.align = props.align_to
        return self.execute(context)


classes = [
    OBJECT_OT_pt_pivot_to_select,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
