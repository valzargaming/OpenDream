# Associative construction ownership regression

Run the two-mode workflow on the exact reviewed commit with SDK 10.0.401 and recursive submodules. `control.py` verifies committed source bytes and the full historical handler before modifying only `CreateAssociativeList`; receipts are rechecked after execution. Historical pins are raw Git blob bytes. The frozen audit checkout had CRLF bytes and is distinct from these LF Git inputs.

Positive requires exactly one executed passing `RejectedConstructionReleasesOwners`, exit 0, 48 exact owner/bucket rows, and one completion marker. Baseline requires exactly one executed failing test, exit 1, the same 48 original observation rows, and exactly 96 ordered failures: owner aggregate then list bucket for each case. List bucket growth is exactly 1000; datum buckets stay equal. Unknown diagnostics, frames, tests, skips or malformed evidence fail closed. Preserve original TRX/logs; unexpected NUnit spelling requires inspection, never weaker acceptance.

The matrix covers 1000 rejected constructions per case, invalid keys 0/99 at first/middle/last, datum/list payloads, object keys and aliases. `caught` catches within the constructing proc. The retained `uncaught` case ID means callee unwind into an outer bare catch; both return 17 with no global runtime. This suite does not cover globally unhandled exceptions. Twenty compiled success controls and post-failure stack reuse accompany the matrix. Explicit owners and cleanup isolate negative cases. Null-alias indexing uses the actual list length.

`GameTests.NoRuntimesTest` must independently pass in a fresh process for both modes using its unchanged strict verifier. Build logs/exits, prepared three sources/hashes, source receipt, original logs/TRX/exits, and test/runtime DLL/PDB hashes are artifacts.

`python -m unittest discover -s tests/assoc_list_construction -p 'test_*.py' -v` checks synthetic parser and source-control adversaries only. These checks do not execute DM or prove runtime behavior. Parent-curated fixture source supersedes the earlier detached global-uncaught draft. Parent owns Git pin confirmation, integration, native execution and exact-head CI.
