import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def _attribute_chain(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return '.'.join(reversed(parts))


def _attribute_chains(path):
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    return {
        _attribute_chain(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }


class KeymapSafetyTest(unittest.TestCase):
    def test_addon_does_not_modify_user_keyconfig(self):
        for name in ('keymaps.py', 'preferences.py'):
            with self.subTest(file=name):
                chains = _attribute_chains(ROOT / name)
                self.assertNotIn('wm.keyconfigs.user', chains)


if __name__ == '__main__':
    unittest.main()
