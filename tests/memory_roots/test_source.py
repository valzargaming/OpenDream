"""Pure production extraction checks; never invokes the SDK."""
import pathlib, unittest
from run import body, pool_capacity_declaration
ROOT = pathlib.Path(__file__).resolve().parents[2]
class Tests(unittest.TestCase):
    def test_actual_cap_dependency_is_extracted(self):
        source = (ROOT/'OpenDreamRuntime/Objects/Types/DreamList.cs').read_text()
        declaration = pool_capacity_declaration(source)
        self.assertEqual(declaration, '    private const int MaximumPooledCapacity = 65_536;')
        deletion = body(source, 'protected override void HandleDeletion(')
        self.assertIn('_values.Capacity <= MaximumPooledCapacity', deletion)
        self.assertIn('value.DecRef();', deletion)
        self.assertIn('_values.Clear();', deletion)
    def test_missing_or_duplicate_declaration_rejected(self):
        declaration = '    private const int MaximumPooledCapacity = 65_536;'
        for source in ['', declaration+'\n'+declaration, declaration.replace('const', 'static')]:
            with self.assertRaises(ValueError): pool_capacity_declaration(source)
if __name__ == '__main__': unittest.main()
