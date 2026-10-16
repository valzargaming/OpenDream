"""Authenticate only reviewed additive fixture dependencies; no native invocation."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
FROZEN_HASHES = {'list-original.cs': 'c5c3baed5e30333ce63fcd38e2be40d5b3cc07bda4c900171e8da84d0a588e55', 'numeric-original.py': 'acc92ade2f46f0911a5ece1d1691de19a183dc09540afeca1bda4e002b440a5a', 'numeric-composed.py': '20127d2a5fadfbce3ae3561b77b3ba5bb6e2651c07a7527ed6bcc886d4a22104', 'attributes-base.txt': 'bc56fc6d4eccdb7efc0a9d3e89ac0fcc5945ec22c2749c0ef5038f3d672500a5', 'attributes-list.txt': 'fdb9c3c71829da1aca39dcbc6ab59bc82ba552872b3401afcadc02beabea4cfc', 'attributes-cache.txt': '58af3dc05d8ab0532982e769ad40ec02b51cfcd648fc4faac9f5884c3f2d2a4d', 'project-original.txt': 'aeaee5ef044c58f1c79da81a3ad2a4efd3f0583c577aa19af16a711d1828706f', 'project-composed.txt': '7d2ed2e3871ebe160b8b2324d980ea9192725b226dca2d1d752236ae490114a3', 'missing-original.py': 'a30b8e1f59f23e34288340651d279c198913f3e11039ec593b2317ce0a6c7497', 'missing-composed.py': 'ef7052ca814fac0a75f534ba93821a79020a1c8b9f83515c3c1ffc3955d20fac'}
BASE = '8b46fd2a6dda5095df1d0fc8db7fd029cd186ba4'
LIST_HEAD = '12fc9410a7f68b89d2dd796fa9f77900bbb076d1'
CACHE_HEAD = '383c5c98b3a1a4a4cd28ae029a624fbf00190cad'
LIST = 'OpenDreamRuntime/Objects/Types/DreamList.cs'
NUMERIC = 'tests/numeric_list_ownership/control.py'
CAP_DECL = b'    // Bound idle backing storage without limiting the size of live DM lists.\n    private const int MaximumPooledCapacity = 65_536;\n'
POOL_DECL = b'    private static readonly Stack<List<DreamValue>> ListPool = new();\n'
OLD_GUARD = b'_values.Capacity > DreamManager.ListPoolThreshold && ListPool.Count < DreamManager.ListPoolSize'
CAP_GUARD = b'_values.Capacity > DreamManager.ListPoolThreshold && _values.Capacity <= MaximumPooledCapacity\n            && ListPool.Count < DreamManager.ListPoolSize'

def sha(raw): return hashlib.sha256(raw).hexdigest()

def frozen():
    values = {name:(HERE/'frozen_dependencies'/name).read_bytes().replace(b'\r\n',b'\n') for name in FROZEN_HASHES}
    assert all(sha(raw) == FROZEN_HASHES[name] for name,raw in values.items()), 'frozen dependency drift'
    return values

def compositions():
    values = frozen()
    original = values['list-original.cs']
    assert original.count(POOL_DECL) == original.count(OLD_GUARD) == 1 and b'MaximumPooledCapacity' not in original
    composed = original.replace(POOL_DECL, POOL_DECL+CAP_DECL, 1).replace(OLD_GUARD,CAP_GUARD,1)
    base = values['attributes-base.txt']; listed = values['attributes-list.txt']; cached = values['attributes-cache.txt']
    assert listed.startswith(base) and cached.startswith(base)
    return {
        # Prior accepted fixture-only compositions; frozen originals remain bound.
        'Content.IntegrationTests/Content.IntegrationTests.csproj':(values['project-original.txt'],values['project-composed.txt'],'4e6e4c4dd523230ca94ffe39d04812592a3b8615',BASE),
        'tests/missing_operator_ownership/control.py':(values['missing-original.py'],values['missing-composed.py'],'53554597f7b594ea8a75570240d69d7d3003d56f',BASE),
        LIST:(original,composed,BASE,LIST_HEAD),
        NUMERIC:(values['numeric-original.py'],values['numeric-composed.py'],BASE,LIST_HEAD),
        '.gitattributes':(cached,listed+cached[len(base):],CACHE_HEAD,LIST_HEAD),
    }

def record(path):
    original,candidate,original_commit,composition_commit = compositions()[path]
    return dict(original_sha256=sha(original),candidate_sha256=sha(candidate),
                original_commit=original_commit,composition_commit=composition_commit)

def authenticate(path, raw):
    # Windows checkouts may convert text endings; no other normalization is allowed.
    assert raw.replace(b'\r\n',b'\n') == compositions()[path][1], 'unreviewed composed dependency: '+path

def validate(root, spec):
    entries = spec.get('dependency_compositions',{})
    assert entries, 'missing dependency composition provenance'
    sources = spec.get('expected_sources',spec.get('sources',{}))
    for path, provenance in entries.items():
        assert provenance == record(path), 'changed frozen/composed provenance'
        assert sources[path] == provenance['candidate_sha256'], 'candidate pin differs from composition'
        authenticate(path,(root/path).read_bytes())
