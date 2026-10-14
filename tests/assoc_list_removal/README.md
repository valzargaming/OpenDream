# Associative-list removal ownership

DreamAssocList owns both each key and its associated value. Removing a key
must release both owners after removing the dictionary entry. Previously only
the key was released, retaining removed values and their referenced objects.

The dedicated Explicit engine fixture runs in its own test host so native
library initialization does not collide with the ordinary GameTests server.
It runs 1000 removal cycles for datum/list values, object keys, key/value aliases,
self references and five compiled DM removal/operator routes. It checks the
remaining caller reference, final deletion, nested child deletion, reference
buckets, no-op removal and retained key order. Existing ordinary tests remain
enabled and unchanged.

CI builds the actual solution at the exact PR head using SDK 10.0.401. Positive
evidence requires the connected fixture to pass. The immutable baseline and a
separate omitted-value-release control must each fail exactly eighteen owner
assertions. A strict verifier rejects skipped/missing tests, wrong identities,
incorrect owner counts and unrelated runtime or runner failures. Artifacts
retain original sources, build/test logs, TRX, actual exit codes and binary
hashes with the tested assemblies and symbols. Every mode also runs the
unchanged NoRuntimesTest in its own test host, including the existing savefile
disposal and shared-file preservation checks.

Pure evidence controls can run without launching the engine:

```text
<verified-python> -m unittest discover -s tests/assoc_list_removal -p test_*.py -v
```

These tests establish bounded ownership behavior. They do not measure this
path's frequency on Gaia or prove the cause of its 12.5 GB memory observation.
