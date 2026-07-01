import bpy


def get_hotkey_entry_item(km, kmi_name, kmi_value, properties):
    for i, km_item in enumerate(km.keymap_items):
        if km.keymap_items.keys()[i] == kmi_name:
            if properties == 'name':
                if km.keymap_items[i].properties.name == kmi_value:
                    return km_item
            elif properties == 'tab':
                if km.keymap_items[i].properties.tab == kmi_value:
                    return km_item
            elif properties == 'none':
                return km_item
    return None


pt_keymaps = []

# Описатели созданных нами keymap-айтемов: (keymap_name, space_type, operator_idname, properties.name).
# На unregister мы заново находим айтемы по этим данным в ЖИВОМ keyconfig, а не разыменовываем
# сохранённые в pt_keymaps указатели — они к моменту выхода из Blender могут быть висячими
# (keyconfig пересобирается за сессию, а Python-обёртки кеймапов Blender не инвалидирует).
_kmi_specs = (
    ('3D View', 'VIEW_3D', 'wm.call_menu_pie', 'VIEW3D_MT_pie_pivot'),
    ('3D View', 'VIEW_3D', 'wm.tool_set_by_id', 'pivot.transform'),
    ('3D View', 'VIEW_3D', 'wm.tool_set_by_id', 'pivot.cursor'),
)


def _remove_registered_keymap_items(key_conf):
    if key_conf is None:
        return

    for km_name, _space_type, operator_idname, prop_name in _kmi_specs:
        km = key_conf.keymaps.get(km_name)
        if km is None:
            continue

        for kmi in list(km.keymap_items):
            if kmi.idname != operator_idname:
                continue
            props = kmi.properties
            if props is not None and getattr(props, 'name', None) == prop_name:
                km.keymap_items.remove(kmi)


def register():
    wm = bpy.context.window_manager
    pt_keymaps.clear()

    # Remove stale entries from older versions that registered into the add-on
    # keyconfig, and avoid duplicates when the add-on is reloaded in-place.
    _remove_registered_keymap_items(wm.keyconfigs.addon)
    _remove_registered_keymap_items(wm.keyconfigs.user)

    # Use the user keyconfig so Blender's normal Keymap search can find these
    # shortcuts and the active keyconfig receives them reliably.
    key_conf = wm.keyconfigs.user or wm.keyconfigs.addon
    if not key_conf:
        return

    km = key_conf.keymaps.get('3D View')
    if km is None:
        km = key_conf.keymaps.new(name='3D View', space_type='VIEW_3D')

    kmi = km.keymap_items.new('wm.call_menu_pie', type='A', value='PRESS', ctrl=False, alt=True, shift=True, head=True)
    kmi.properties.name = 'VIEW3D_MT_pie_pivot'
    pt_keymaps.append((km, kmi))

    kmi = km.keymap_items.new('wm.tool_set_by_id', type='D', value='PRESS', ctrl=False, alt=False, shift=False, head=True)
    kmi.properties.name = 'pivot.transform'
    kmi.properties.cycle = True
    kmi.active = True
    pt_keymaps.append((km, kmi))

    # 3D Cursor tool — отдельный инструмент, свой хотkey. Выключен по умолчанию:
    # пользователь включает и при желании переназначает клавишу в настройках аддона.
    kmi = km.keymap_items.new('wm.tool_set_by_id', type='D', value='PRESS', ctrl=False, alt=True, shift=True, head=True)
    kmi.properties.name = 'pivot.cursor'
    kmi.active = False
    pt_keymaps.append((km, kmi))


def unregister():
    pt_keymaps.clear()

    wm = bpy.context.window_manager
    if wm is None:
        return

    _remove_registered_keymap_items(wm.keyconfigs.user)
    _remove_registered_keymap_items(wm.keyconfigs.addon)
