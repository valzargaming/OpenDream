"""Pure generated-source lexical guard; this does not replace C# compilation."""
import json
import re
import unittest
from control import PACKAGE, HELPER, target_sources

def csharp_code(text):
    # Remove comments and quoted content before counting structural braces.
    # This bounded lexer is only a guard for the frozen generated fixture files.
    return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '', text)

def require_balanced_braces(text):
    depth = 0
    for char in csharp_code(text):
        if char == '{': depth += 1
        if char == '}': depth -= 1
        if depth < 0: raise AssertionError('generated C# brace balance')
    if depth != 0: raise AssertionError('generated C# brace balance')

class GeneratedMutationSyntaxTests(unittest.TestCase):
    def test_all_frozen_generated_controls_keep_balanced_braces(self):
        controls = json.loads((PACKAGE / 'controls.json').read_text())
        self.assertEqual(len(controls), 9)
        for mode, spec in controls.items():
            with self.subTest(mode=mode):
                # target_sources also enforces the exact reviewed mutation hash.
                require_balanced_braces(target_sources(mode)[spec['path']].decode())

    def test_filter_control_disables_condition_preserves_its_block(self):
        source = target_sources('ignore-resource-filter')[HELPER].decode()
        self.assertRegex(csharp_code(source), r'if \(false\)\s*\{\s*_resourceExcluded\+\+; return null;\s*\}')
        positive = target_sources('positive')[HELPER].decode()
        self.assertIn('if (_exactResourcePath != null && !string.Equals(', positive)

    def test_actual_line_comment_failure_is_rejected(self):
        source = target_sources('ignore-resource-filter')[HELPER].decode()
        needle = 'if (false) /* negative control: all resources selected */'
        self.assertEqual(source.count(needle), 1)
        broken = source.replace(needle, 'if (false) // negative control: all resources selected')
        with self.assertRaisesRegex(AssertionError, 'generated C# brace balance'):
            require_balanced_braces(broken)

    def test_quoted_and_commented_braces_are_not_structure(self):
        require_balanced_braces('class A { string s = "} // {"; /* } */ // {\n }')
        with self.assertRaises(AssertionError):require_balanced_braces('class A { /* } */')

if __name__ == '__main__':unittest.main(verbosity=2)
