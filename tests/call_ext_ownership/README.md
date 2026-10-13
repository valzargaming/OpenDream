# External-call ownership candidate

SOURCE ONLY against immutable 98ccff7f1e156193b41a2fe61f92559c25597a50. Unapplied, unpublished, no engine edits. No compiler, engine, native DLL, network or CI execution. Prior candidate bundles are preserved.

Both ABI consumers acquire a scoped disposable copy before resolving the entry point. Successful BYOND result still disposes before input ownership; successful string allocation cleanup remains in its existing finally. Removed the original input disposal in each consumer, preventing double disposal. CallExt itself does not acquire another owner or dispose the passed bundle.

Actual DM probes attempt ordinary string-source call statements with symbol@failure and byond:symbol@failure. DllHelper rejects @ before GetDll or native code. DMProcState.CatchException converts managed exceptions via DreamManager.CreateException; CreateException sets exception.name to the exact managed Message. Returning this name is a string and does not retain payload. C# connected fixture asserts the exact message, caller ref1/liveness after each of 1000 invocations per ABI, finally releases caller ownership, and verifies real LocateRef null. It runs after the existing native ownership fixture within NoRuntimesTest's server assertion thread.

Compiler spelling acceptance, real DM catch behavior, and all reference/bucket assertions are UNRUN. Exact managed exception type is established by DllHelper source, while the DM fixture checks its exported message only. LastDMException must remain null after the actual caught call.

Independent controls omit only stringArguments or byondArguments scope, preserving the other ABI's cleanup. The first affected iteration must fail the exact payload.RefCount expected1 actual2 assertion; wrong error, unrelated stack, engine diagnostic, additional failure, or absent completion is rejected. Controls and verification require immutable source/fixture hashes, pinned baseline blob, actual checkout HEAD and mutation receipts. The draft workflow is not installed or triggered.

Successful callback/conversion/result parity for native ABI is UNRUN and unsupported by this rejection-only fixture. No external library is invented or loaded. Scope proves only the source fix and planned deterministic resolver-rejection contract; broader ABI acceptance needs separate authorized tests.

Successor baseline is immutable fork master38c2ca104a2151e4223e1f889e2fc754a921921b, preserving merged constructor/proc/native hooks. CallExt production bytes and blob are unchanged since98cc. Two omission controls remain independent. No operator candidate is integrated. Connected engine/compiler/CI/native callback parity are UNRUN.
