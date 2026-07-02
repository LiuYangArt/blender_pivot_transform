# Keymap deletion postmortem

## Symptom

After enabling Pivot Transform, closing Blender could remove many existing user keymap entries.

## Root cause

The add-on registered its shortcuts in `wm.keyconfigs.user`, then `unregister()` scanned the live user keyconfig and removed entries matching the same operator/property pair. If the user had customized or duplicated matching shortcuts, they were indistinguishable from add-on-created entries and could be deleted on shutdown.

## Fix

- Register add-on shortcuts only in `wm.keyconfigs.addon`.
- Remove add-on shortcuts only from `wm.keyconfigs.addon`.
- Show the add-on keyconfig in preferences instead of the persistent user keyconfig.

## Verification

- `python -B -m py_compile keymaps.py preferences.py __init__.py`
- `python -B -m unittest discover -s tests`
- `git diff --check`

## Regression coverage

`tests/test_keymap_safety.py` statically verifies that keymap registration and preferences code do not access `wm.keyconfigs.user`.
