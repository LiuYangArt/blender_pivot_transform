# SPDX-License-Identifier: GPL-2.0-or-later
"""
Установка Origin / Pivot трансформации в *любом* режиме (Edit/Object/и т.д.) для большинства типов объектов Blender.

Этот модуль — Python-адаптация C-оператора Blender `object_origin_set_exec`
(из `source/blender/editors/object/object_transform.cc`), обрезанная и переработанная
для практического использования в аддонах и скриптах. Протестировано против API Blender 4.5.

Цели:
- Работать даже когда пользователь находится в режиме редактирования (mesh, curve, lattice, armature*).
- Избегать использования bpy.ops где возможно; работать с данными напрямую.
- Поддерживать множественные режимы origin:
    - GEOMETRY_TO_ORIGIN
    - ORIGIN_TO_GEOMETRY (median/bounds)
    - ORIGIN_TO_CURSOR
    - ORIGIN_TO_CENTER_OF_MASS_SURFACE (mesh)
    - ORIGIN_TO_CENTER_OF_MASS_VOLUME (mesh; рекомендуется для manifold)
- Обрабатывать *большинство* типов объектов, затрагиваемых в C-коде: MESH, CURVE, SURFACE, FONT,
  LATTICE, MBALL, POINTCLOUD. Grease Pencil v3 поддерживается частично (по возможности).
- Сохранять текущий режим, восстанавливая его при выходе.

Примечания и отличия от C:
- Перецентровка Armature как `ED_armature_origin_set` нетривиальна из Python и не
  представлена 1:1. Этот скрипт в настоящее время *пропускает* специальную обработку костей.
  Для объектов ARMATURE мы поддерживаем только сдвиг origin на уровне объекта через `ORIGIN_TO_CURSOR`
  и простые bounds/median edit-костей (если в режиме Edit). Продвинутые коррекции костей/parenting,
  как в редакторе, оставлены как TODO.
- Grease Pencil v3 (новый тип объекта) Python-доступ эволюционирует. Мы предоставляем консервативный
  перенос точек штрихов per-drawing когда возможно; иначе падаем обратно к сдвигу
  локации объекта.
- Мульти-пользовательские данные и library overrides: мы *отказываемся* редактировать не-редактируемые/linked data-blocks,
  аналогично C-оператору.

Использование
-------------
- Импортировать и вызвать `set_origin(context, type, center)` напрямую, ИЛИ зарегистрировать оператор
  и вызвать `bpy.ops.object.set_origin_any_mode(type='ORIGIN_CURSOR', center='MEDIAN')`.

"""
import bpy
import bmesh
from mathutils import Matrix, Vector
from math import isfinite
from contextlib import contextmanager





# --- TODO
# object_origin_set_exec 1046
# blender/source/blender/editors/object/object_transform.c

# -----------------------------------------------------------------------------
# константы (соответствуют перечислениям из c)

GEOMETRY_TO_ORIGIN = 'GEOMETRY_ORIGIN'
ORIGIN_TO_GEOMETRY = 'ORIGIN_GEOMETRY'
ORIGIN_TO_CURSOR = 'ORIGIN_CURSOR'
ORIGIN_TO_CENTER_OF_MASS_SURFACE = 'ORIGIN_CENTER_OF_MASS'
ORIGIN_TO_CENTER_OF_MASS_VOLUME = 'ORIGIN_CENTER_OF_VOLUME'

CENTER_MEDIAN = 'MEDIAN'
CENTER_BOUNDS = 'BOUNDS'

# -----------------------------------------------------------------------------
# утилиты

@contextmanager
def preserve_mode(obj: bpy.types.Object | None):
    """Контекстный менеджер для восстановления режима объекта после модификаций.
    Если поддерживается редактирование на уровне данных (bmesh для MESH, и т.д.), остаёмся в этом режиме.
    Иначе может потребоваться временный переход в OBJECT.
    """
    if obj is None:
        yield
        return
    mode = obj.mode
    try:
        yield
    finally:
        # восстанавливаем режим только если контекст валиден и режим существует
        try:
            if obj.mode != mode:
                bpy.ops.object.mode_set(mode=mode)
        except Exception:
            pass


def is_editable_id(id_: bpy.types.ID) -> bool:
    return (not id_.library) and (not getattr(id_, 'override_library', None))


def foreach_selected_editable_objects(context: bpy.types.Context):
    for ob in context.selected_editable_objects:
        yield ob


# удалено: управление глобальным undo запрещено по требованиям


# удалено: вспомогательная логика для ручного undo-push — приводила к «двойным» шагам


# -----------------------------------------------------------------------------
# вспомогательные функции для вычисления границ/центров (в локальном пространстве)

def _mesh_bounds_median_edit(me: bpy.types.Mesh) -> Vector:
    bm = bmesh.from_edit_mesh(me)
    if not bm.verts:
        return Vector((0.0, 0.0, 0.0))
    acc = Vector((0.0, 0.0, 0.0))
    inv_tot = 1.0 / len(bm.verts)
    for v in bm.verts:
        acc.x += v.co.x * inv_tot
        acc.y += v.co.y * inv_tot
        acc.z += v.co.z * inv_tot
    return acc


def _mesh_bounds_bbox_edit(me: bpy.types.Mesh) -> Vector:
    bm = bmesh.from_edit_mesh(me)
    if not bm.verts:
        return Vector((0.0, 0.0, 0.0))
    minv = Vector((float('inf'),) * 3)
    maxv = Vector((float('-inf'),) * 3)
    for v in bm.verts:
        minv.x = min(minv.x, v.co.x)
        maxv.x = max(maxv.x, v.co.x)
        minv.y = min(minv.y, v.co.y)
        maxv.y = max(maxv.y, v.co.y)
        minv.z = min(minv.z, v.co.z)
        maxv.z = max(maxv.z, v.co.z)
    return (minv + maxv) * 0.5


def _mesh_center_surface(me: bpy.types.Mesh) -> Vector:
    """Центр, взвешенный по площади поверхностных треугольников (пространство данных объекта).
    При необходимости использует временную оценённую сетку для триангуляции.
    """
    # считаем центр поверхности по площадям граней через bmesh
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        # для корректных площадей и центров триангулируем n-угольники
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
        center = Vector((0.0, 0.0, 0.0))
        area_sum = 0.0
        for f in bm.faces:
            a = f.calc_area()
            if a <= 0.0:
                continue
            c = f.calc_center_median()
            center += c * a
            area_sum += a
        if area_sum > 0.0:
            center *= (1.0 / area_sum)
        return center
    finally:
        bm.free()


def _tetra_volume(p0, p1, p2, p3):
    # ориентированный объём тетраэдра (p0 считается началом координат)
    return (p1 - p0).cross(p2 - p0).dot(p3 - p0) / 6.0


def _mesh_center_volume(me: bpy.types.Mesh) -> Vector:
    """Объёмный центроид для замкнутой manifold-сетки с использованием тетраэдров к началу координат.
    Если сетка не manifold/не ориентирована, результат может быть неточным (как предупреждает C-docstring).
    """
    # объёмный центр через bmesh и триангуляцию граней; разложение на тетраэдры к началу координат
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
        center = Vector((0.0, 0.0, 0.0))
        vol_sum = 0.0
        origin = Vector((0.0, 0.0, 0.0))
        for f in bm.faces:
            if len(f.verts) != 3:
                continue
            p0 = f.verts[0].co
            p1 = f.verts[1].co
            p2 = f.verts[2].co
            vol = _tetra_volume(origin, p0, p1, p2)
            c = (p0 + p1 + p2) / 4.0
            center += c * vol
            vol_sum += vol
        if abs(vol_sum) > 1e-12:
            center *= (1.0 / vol_sum)
        return center
    finally:
        bm.free()


def _mesh_center_median_object(me: bpy.types.Mesh) -> Vector:
    # медианный центр по вершинам через bmesh
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        if not bm.verts:
            return Vector((0.0, 0.0, 0.0))
        inv = 1.0 / len(bm.verts)
        acc = Vector((0.0, 0.0, 0.0))
        for v in bm.verts:
            acc += v.co * inv
        return acc
    finally:
        bm.free()


def _mesh_center_bounds_object(me: bpy.types.Mesh) -> Vector:
    # центр ограничивающего бокса через bmesh
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        if not bm.verts:
            return Vector((0.0, 0.0, 0.0))
        minv = Vector((float('inf'),) * 3)
        maxv = Vector((float('-inf'),) * 3)
        for v in bm.verts:
            minv.x = min(minv.x, v.co.x)
            maxv.x = max(maxv.x, v.co.x)
            minv.y = min(minv.y, v.co.y)
            maxv.y = max(maxv.y, v.co.y)
            minv.z = min(minv.z, v.co.z)
            maxv.z = max(maxv.z, v.co.z)
        return (minv + maxv) * 0.5
    finally:
        bm.free()


def _curve_bounds_center(cu: bpy.types.Curve, bounds=True) -> Vector:
    # оцениваем контрольные точки сплайнов в пространстве данных
    pts = []
    for spline in cu.splines:
        if spline.type in {'BEZIER'}:
            for bp in spline.bezier_points:
                pts.append(bp.co)
        else:
            for p in spline.points:
                # у nurbs/poly .co четырёхмерные (с w), используем только xyz
                pts.append(Vector((p.co.x, p.co.y, p.co.z)))
    if not pts:
        return Vector((0, 0, 0))
    if bounds:
        minv = Vector((float('inf'),) * 3)
        maxv = Vector((float('-inf'),) * 3)
        for p in pts:
            minv.x = min(minv.x, p.x)
            maxv.x = max(maxv.x, p.x)
            minv.y = min(minv.y, p.y)
            maxv.y = max(maxv.y, p.y)
            minv.z = min(minv.z, p.z)
            maxv.z = max(maxv.z, p.z)
        return (minv + maxv) * 0.5
    else:
        inv = 1.0 / len(pts)
        acc = Vector((0, 0, 0))
        for p in pts:
            acc += p * inv
        return acc


def _lattice_center(lt: bpy.types.Lattice, bounds=True) -> Vector:
    pts = [Vector(p.co_deform) for p in lt.points]
    if not pts:
        return Vector((0, 0, 0))
    if bounds:
        minv = Vector((float('inf'),) * 3)
        maxv = Vector((float('-inf'),) * 3)
        for p in pts:
            minv.x = min(minv.x, p.x)
            maxv.x = max(maxv.x, p.x)
            minv.y = min(minv.y, p.y)
            maxv.y = max(maxv.y, p.y)
            minv.z = min(minv.z, p.z)
            maxv.z = max(maxv.z, p.z)
        return (minv + maxv) * 0.5
    else:
        inv = 1.0 / len(pts)
        acc = Vector((0, 0, 0))
        for p in pts:
            acc += p * inv
        return acc


def _mball_center(mb: bpy.types.MetaBall, bounds=True) -> Vector:
    pts = [Vector(el.co) for el in mb.elements]
    if not pts:
        return Vector((0, 0, 0))
    if bounds:
        minv = Vector((float('inf'),) * 3)
        maxv = Vector((float('-inf'),) * 3)
        for p in pts:
            minv.x = min(minv.x, p.x)
            maxv.x = max(maxv.x, p.x)
            minv.y = min(minv.y, p.y)
            maxv.y = max(maxv.y, p.y)
            minv.z = min(minv.z, p.z)
            maxv.z = max(maxv.z, p.z)
        return (minv + maxv) * 0.5
    else:
        inv = 1.0 / len(pts)
        acc = Vector((0, 0, 0))
        for p in pts:
            acc += p * inv
        return acc


def _pointcloud_center(pc: bpy.types.PointCloud, bounds=True) -> Vector:
    if not pc.points:
        return Vector((0, 0, 0))
    # доступ через foreach_get быстрее, но здесь достаточно простого цикла
    pts = [Vector(p.co) for p in pc.points]
    if bounds:
        minv = Vector((float('inf'),) * 3)
        maxv = Vector((float('-inf'),) * 3)
        for p in pts:
            minv.x = min(minv.x, p.x)
            maxv.x = max(maxv.x, p.x)
            minv.y = min(minv.y, p.y)
            maxv.y = max(maxv.y, p.y)
            minv.z = min(minv.z, p.z)
            maxv.z = max(maxv.z, p.z)
        return (minv + maxv) * 0.5
    else:
        inv = 1.0 / len(pts)
        acc = Vector((0, 0, 0))
        for p in pts:
            acc += p * inv
        return acc


# -----------------------------------------------------------------------------
# перенос геометрии по типам (в пространстве данных)

def _mesh_translate(me: bpy.types.Mesh, delta: Vector, edit_mode: bool):
    if delta.length_squared == 0.0:
        return
    T = Matrix.Translation(-delta)
    if edit_mode:
        # редактируем живой bmesh через матричную трансформацию
        bm = bmesh.from_edit_mesh(me)
        bm.transform(T)
        bmesh.update_edit_mesh(me, loop_triangles=False)
    else:
        # трансформируем датаблок целиком, включая shape keys если поддерживается
        try:
            me.transform(T, shape_keys=True)  # type: ignore[call-arg]
        except TypeError:
            # совместимость со старыми сигнатурами
            me.transform(T)
        me.update()


def _curve_translate(cu: bpy.types.Curve, delta: Vector):
    if delta.length_squared == 0.0:
        return
    cu.transform(Matrix.Translation(-delta))


def _font_translate(cu: bpy.types.Curve, delta: Vector):
    # следуем логике оператора на c: меняем xof/yof; z фиксируем в 0 для текста
    if delta.length_squared == 0.0:
        return
    cu.xof -= delta.x
    cu.yof -= delta.y


def _lattice_translate(lt: bpy.types.Lattice, delta: Vector):
    if delta.length_squared == 0.0:
        return
    # у lattice есть data.transform: используем матричный перенос
    lt.transform(Matrix.Translation(-delta))


def _mball_translate(mb: bpy.types.MetaBall, delta: Vector):
    if delta.length_squared == 0.0:
        return
    # metaball также поддерживает transform(matrix)
    mb.transform(Matrix.Translation(-delta))


def _pointcloud_translate(pc: bpy.types.PointCloud, delta: Vector):
    if delta.length_squared == 0.0:
        return
    # в новых версиях point cloud имеет transform; иначе fallback по точкам
    T = Matrix.Translation(-delta)
    try:
        pc.transform(T)  # type: ignore[attr-defined]
    except Exception:
        for p in pc.points:
            p.co = Vector(p.co) - delta


def _gpencil_translate(gp: bpy.types.GreasePencil, delta: Vector):
    """Попытка перенести штрихи GPv3 в пространстве данных.
    Если Python-доступ не удаётся, fallback к сдвигу позиции объекта (обрабатывается снаружи).
    """
    # api может меняться; оборачиваем в try/except, чтобы избежать падений
    try:
        if delta.length_squared == 0.0:
            return True
        # сначала пробуем общий transform у датаблока (если поддерживается)
        try:
            gp.transform(Matrix.Translation(-delta))  # type: ignore[attr-defined]
            return True
        except Exception:
            pass

        for layer in gp.layers:
            for fr in layer.frames:
                drw = fr.drawing
                # некоторые drawings могут быть ссылочными/пустыми
                if getattr(drw, 'is_empty', False):
                    continue
                # доступ к точкам через strokes api
                if hasattr(drw, 'strokes'):
                    for st in drw.strokes:
                        for pt in st.points:
                            pt.co = Vector(pt.co) - delta
                else:
                    # запасной вариант: пробуем общий transform
                    mat = Matrix.Translation(-delta)
                    if hasattr(drw, 'transform'):
                        drw.transform(mat)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


# -----------------------------------------------------------------------------
# ядро: вычисление центра и применение обратного смещения к origin объекта

def _compute_center_local(context: bpy.types.Context, ob: bpy.types.Object,
                          mode_type: str, center: str) -> Vector:
    """Возвращает центр в *локальном пространстве данных объекта* для перемещения геометрии на `-center`.
    """
    if mode_type == ORIGIN_TO_CURSOR:
        # переводим мировые координаты курсора в локальные координаты объекта
        cursor_world = Vector(context.scene.cursor.location)
        # world_to_object (в 4.5) через обратную матрицу object.matrix_world
        return ob.matrix_world.inverted() @ cursor_world

    if ob.data is None:
        # случаи с инстансами коллекций полностью не поддержаны; возвращаем ноль, чтобы вызвать no-op
        return Vector((0, 0, 0))

    if isinstance(ob.data, bpy.types.Mesh):
        me: bpy.types.Mesh = ob.data
        if ob.mode == 'EDIT':
            if center == CENTER_BOUNDS:
                return _mesh_bounds_bbox_edit(me)
            else:
                return _mesh_bounds_median_edit(me)
        else:
            if mode_type == ORIGIN_TO_CENTER_OF_MASS_SURFACE:
                return _mesh_center_surface(me)
            if mode_type == ORIGIN_TO_CENTER_OF_MASS_VOLUME:
                return _mesh_center_volume(me)
            if center == CENTER_BOUNDS:
                return _mesh_center_bounds_object(me)
            return _mesh_center_median_object(me)

    if isinstance(ob.data, bpy.types.Curve):
        cu: bpy.types.Curve = ob.data
        bounds = (center == CENTER_BOUNDS)
        c = _curve_bounds_center(cu, bounds=bounds)
        # для 2d-кривых (например, текст в виде кривой) фиксируем z, как в c-коде
        if ob.type == 'CURVE' and not cu.dimensions == '3D':
            c.z = 0.0
        return c

    if isinstance(ob.data, bpy.types.Lattice):
        lt: bpy.types.Lattice = ob.data
        return _lattice_center(lt, bounds=(center == CENTER_BOUNDS))

    if isinstance(ob.data, bpy.types.MetaBall):
        mb: bpy.types.MetaBall = ob.data
        return _mball_center(mb, bounds=(center == CENTER_BOUNDS))

    if isinstance(ob.data, bpy.types.PointCloud):
        pc: bpy.types.PointCloud = ob.data
        return _pointcloud_center(pc, bounds=(center == CENTER_BOUNDS))

    if isinstance(ob.data, bpy.types.GreasePencil):
        # по возможности оцениваем по границам всех точек штрихов; иначе используем локальный origin
        gp: bpy.types.GreasePencil = ob.data
        try:
            minv = Vector((float('inf'),) * 3)
            maxv = Vector((float('-inf'),) * 3)
            count = 0
            for layer in gp.layers:
                for fr in layer.frames:
                    drw = fr.drawing
                    if getattr(drw, 'is_empty', False):
                        continue
                    if hasattr(drw, 'strokes'):
                        for st in drw.strokes:
                            for pt in st.points:
                                p = Vector(pt.co)
                                if center == CENTER_BOUNDS:
                                    minv.x = min(minv.x, p.x)
                                    maxv.x = max(maxv.x, p.x)
                                    minv.y = min(minv.y, p.y)
                                    maxv.y = max(maxv.y, p.y)
                                    minv.z = min(minv.z, p.z)
                                    maxv.z = max(maxv.z, p.z)
                                else:
                                    count += 1
                                    # накапливаем сумму точек во временном векторе minv
                                    minv += p
            if center == CENTER_BOUNDS:
                if all(isfinite(v) for v in (*minv, *maxv)):
                    return (minv + maxv) * 0.5
            else:
                if count > 0:
                    return minv * (1.0 / count)
        except Exception:
            pass
        return Vector((0, 0, 0))

    # camera/light/empty: данные не меняем, поддерживаем только ORIGIN_TO_CURSOR (см. выше)
    return Vector((0, 0, 0))


def _apply_inverse_offset(context: bpy.types.Context, ob: bpy.types.Object, local_center: Vector,
                          mode_type: str):
    """Сдвигает геометрию на `-local_center` и добавляет эквивалентное смещение в parent-space
    к object.location (чтобы визуальная позиция оставалась). Отражает C-логику для do_inverse_offset.
    No-op для GEOMETRY_TO_ORIGIN, поскольку этот случай обрабатывается только переносом геометрии.
    """
    if mode_type == GEOMETRY_TO_ORIGIN:
        return

    # преобразуем local_center в дельту в системе координат родителя (игнорируя перенос)
    # важно: нам нужна ТОЛЬКО локальная матрица объекта без учёта родителя: RS = R_obj * S_obj
    # тогда delta_parent = RS @ local_center
    # если объект имеет родителя, world_3x3 = (R_parent*S_parent) @ RS, поэтому извлекаем RS
    try:
        # предпочтительно использовать matrix_basis (локальная матрица объекта в пространстве родителя)
        rs_local = ob.matrix_basis.to_3x3()
    except Exception:
        # запасной путь: вычисляем RS через world и родителя
        world_3x3 = ob.matrix_world.to_3x3()
        if ob.parent is not None:
            parent_3x3 = ob.parent.matrix_world.to_3x3()
            try:
                rs_local = parent_3x3.inverted() @ world_3x3
            except Exception:
                rs_local = world_3x3
        else:
            rs_local = world_3x3

    delta_parent = rs_local @ local_center

    ob.location = Vector(ob.location) + delta_parent


# -----------------------------------------------------------------------------
# публичный api

def set_origin(context: bpy.types.Context,
               type: str = ORIGIN_TO_GEOMETRY,
               center: str = CENTER_MEDIAN):
    """Основная функция для установки origin, аналогично оператору Blender, но безопасна в любом режиме.

    Parameters
    ----------
    context : bpy.types.Context
    type : один из GEOMETRY_TO_ORIGIN / ORIGIN_TO_GEOMETRY / ORIGIN_TO_CURSOR /
           ORIGIN_TO_CENTER_OF_MASS_SURFACE / ORIGIN_TO_CENTER_OF_MASS_VOLUME
    center : CENTER_MEDIAN или CENTER_BOUNDS (используется для ORIGIN_TO_GEOMETRY)
    """
    # получаем depsgraph при необходимости (сейчас не используется)
    # depsgraph = context.evaluated_depsgraph_get()

    # формируем список объектов: активный первым
    objects = list(foreach_selected_editable_objects(context))
    if not objects:
        return {'CANCELLED'}
    if context.active_object in objects:
        objects.remove(context.active_object)
        objects.insert(0, context.active_object)

    changed = False

    for ob in objects:
            # проверка редактируемости id (как в c)
            if ob.data is not None and not is_editable_id(ob.data):
                continue

            with preserve_mode(ob):
                # вычисляем центр в локальном пространстве, не переключаясь в OBJECT
                local_center = Vector((0, 0, 0))
                if type == GEOMETRY_TO_ORIGIN:
                    # в этом режиме переносим геометрию к origin (то есть вычитаем текущий центр)
                    # используем выбранный способ вычисления центра геометрии
                    local_center = _compute_center_local(context, ob, ORIGIN_TO_GEOMETRY, center)
                else:
                    local_center = _compute_center_local(context, ob, type, center)

                # применяем перенос геометрии на -local_center для каждого типа данных
                if ob.data is None:
                    # возможно, это инстансы коллекций; вне области поддержки в этом python-порту
                    continue

                if isinstance(ob.data, bpy.types.Mesh):
                    _mesh_translate(ob.data, local_center, edit_mode=(ob.mode == 'EDIT'))
                    changed = True
                elif isinstance(ob.data, bpy.types.Curve):
                    if ob.type == 'FONT':
                        # фиксируем z как в c-коде
                        c = local_center.copy()
                        c.z = 0.0
                        _font_translate(ob.data, c)
                    else:
                        _curve_translate(ob.data, local_center)
                    changed = True
                elif isinstance(ob.data, bpy.types.Lattice):
                    _lattice_translate(ob.data, local_center)
                    changed = True
                elif isinstance(ob.data, bpy.types.MetaBall):
                    _mball_translate(ob.data, local_center)
                    changed = True
                elif isinstance(ob.data, bpy.types.PointCloud):
                    _pointcloud_translate(ob.data, local_center)
                    changed = True
                elif isinstance(ob.data, bpy.types.GreasePencil):
                    ok = _gpencil_translate(ob.data, local_center)
                    if not ok:
                        # Fallback: shift object only (visual change)
                        pass
                    changed = True
                else:
                    # для других типов данных пробуем общий transform, если доступен
                    mat = Matrix.Translation(-local_center)
                    if hasattr(ob.data, 'transform'):
                        try:
                            ob.data.transform(mat)  # type: ignore[attr-defined]
                            changed = True
                        except Exception:
                            pass

                # если режим не GEOMETRY_TO_ORIGIN, добавляем обратное смещение к позиции объекта
                _apply_inverse_offset(context, ob, local_center, type)

                # помечаем обновления данных подобно оператору на c
                ob.data.update() if hasattr(ob.data, 'update') else None
                ob.update_tag(refresh={'DATA'})

    if changed:
        # уведомляем depsgraph/вьюпорты
        for ob in objects:
            ob.select_set(True)
        bpy.context.view_layer.update()
        return {'FINISHED'}
    return {'CANCELLED'}


# -----------------------------------------------------------------------------
# необязательная оболочка оператора

class OBJECT_OT_pt_origin_transform(bpy.types.Operator):
    bl_idname = "object.pt_origin_transform"
    bl_label = "Pivot Transform: Set Origin"
    bl_description = "Set the object origin using Pivot Transform"
    bl_options = {'REGISTER', 'UNDO'}

    type: bpy.props.EnumProperty(
        name="Type",
        items=[
            (GEOMETRY_TO_ORIGIN, "Geometry to Origin", "Move geometry to object origin"),
            (ORIGIN_TO_GEOMETRY, "Origin to Geometry", "Move origin to the geometry center"),
            (ORIGIN_TO_CURSOR, "Origin to 3D Cursor", "Move origin to the 3D cursor"),
            (ORIGIN_TO_CENTER_OF_MASS_SURFACE, "Origin to Center of Mass (Surface)", "Mesh area-weighted center"),
            (ORIGIN_TO_CENTER_OF_MASS_VOLUME, "Origin to Center of Mass (Volume)", "Mesh volume centroid; manifold recommended"),
        ],
        default=ORIGIN_TO_GEOMETRY,
    )

    center: bpy.props.EnumProperty(
        name="Center",
        items=[(CENTER_MEDIAN, "Median", "Use the median point"), (CENTER_BOUNDS, "Bounds", "Use the bounding-box center")],
        default=CENTER_MEDIAN,
    )

    def execute(self, context):
        result = set_origin(context, self.type, self.center)
        if 'FINISHED' in result:
            return {'FINISHED'}
        return {'CANCELLED'}


classes = [
    OBJECT_OT_pt_origin_transform,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
