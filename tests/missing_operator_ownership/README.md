# Missing operator argument ownership

Source-only candidate at immutable fork master98ccff7f1e156193b41a2fe61f92559c25597a50. No engine checkout or constructor candidate has been edited; no compiler, native/game, CI, network, push or PR execution occurred. The draft workflow and patch are unapplied review artifacts.

## Production change and ownership contracts

DreamProcArguments.cs:17-28 increments each input owner; Dispose at54-57 decrements them. DreamObject.cs:567-576 accepts owned arguments but missing TryGetProc returns false without disposal. Add/Subtract/Multiply/Divide/Or/Index each create one fresh bundle; IndexAssign creates index/value owners. Their documented InvalidOperationException fallbacks remain the same. MultiplyRef creates independent *= and * bundles. DivideRef instead reuses one bundle for /= then /, so adding missing-branch disposal also requires reacquiring input for the second lookup.

The patch changes only these two production sites: dispose on missing lookup and use fresh DreamProcArguments(b) for each DivideRef attempt. On a defined lookup the existing CreateState path retains its ownership transfer. No general exception, deferred-result or cancellation handling is changed.

At98cc there is no OperatorModulus method. The shared-local-args special case is DivideRef. ModulusValues/ModulusModulusValues in DMOpcodeHandlers.cs:3121-3144 are numeric helpers that create no argument bundle. The only base bitwise helper here is OperatorOr; this change makes no claim about other bitwise paths.

## Actual connected fixture, not yet executed

NoRuntimesTest invokes SupportedOperatorFallbacksReleaseOwners then MissingOperatorArgumentsReleaseOwners immediately after the existing native fixture on the real server assertion thread. DMProject/code.dm adds ordinary datums with real operator bodies and global probes using actual +=-family assignment opcodes where appropriate:

- Only / defined: /= must take fallback and return caller payload.
- Only * defined: *= must take fallback and return caller payload.
- Defined /= and *= return73 while fallback / and * return19, proving assignment overload precedence.
- Defined + and [] return caller payload; []= returns its value without storing it, proving its discarded result owner is released.

Each probe runs1000 times using actual DreamThread.Run, tree, manager and reference manager. Before disposing the returned value, payload identity and liveness are checked. After result disposal, payload.RefCount must be1 and Deleted false. Each caller owner is released in finally; successful completion requires Deleted and actual LocateRef.IsNull. The first strict negative assertion remains primary; finally does not force-delete leaked owners.

The direct phase runs1000 iterations across all nine public missing-overload routes on a plain datum. It asserts overload absence before passing null parent state because that branch never reads parentState. It preserves exact InvalidOperationException type/message, requires caller refs1, and checks distinct index/value owners for IndexAssign. Final caller cleanup/bucket disappearance is checked. No ref-struct reflection is used.

## Exact positive and three controls

The production source input must have SHA-256 a458f9ffda727936fc3f54debfc4a9ee41f9f8088697bb002bc90104cfa7d82f. Immutable baseline DreamObject Git blob is c5fe66e1999976308e500dd43cf94e44d410589d with SHA-256 c5772b3635ba1da46215b4931f887cab51a3d46e63b15f6e0df85e8926306f86. Controls are independent disposable checkouts:

| Control | Mutation | First exact expected assertion |
|---|---|---|
| positive | unchanged candidate | one passed NoRuntimesTest, exit0 and both completed fixture markers |
| baseline | restore exact pinned baseline DreamObject.cs | Supported operator releases payload owner: operator_multiply_fallback_probe, payload.RefCount expected1/actual2 |
| missing-dispose | omit only missing-branch Dispose, keeping fresh DivideRef bundles | Supported operator releases payload owner: operator_divide_fallback_probe, payload.RefCount expected1/actual2 |
| divide-reuse | retain missing-branch Dispose, restore only shared DivideRef args | Supported operator releases payload owner: operator_divide_fallback_probe, payload.RefCount expected1/actual0 |

Negative3 is established from actual source contracts: a reused bundle has already lost its input owner at the first missing lookup. DMProcState.SetArgument (DMProc.cs:650 onward) increments the payload into the supported / frame, then Initialize at448-468 disposes the reused input a second time. This creates a one-owner deficit. Returned result ownership and outer frames keep payload alive before C# result disposal; balanced outer-frame/result cleanup ends at0 instead of caller1. DreamObject.DecRef at146-154 deletes at0; subsequent finally DecRef is a no-op on deleted objects. The exact0 outcome remains unobserved until connected execution. A different failure is not accepted as confirmation.

Baseline DivideRef's shared args is consumed once by its defined fallback, so it balances in the first division probe; baseline then fails multiplication because its first missing *= bundle is abandoned while a fresh * bundle is consumed. Missing-dispose candidate has independent division bundles, so its first missing /= owner is abandoned and the first probe fails at2. Fixture ordering makes each control's oracle deliberate.

## Verification and receipts

control.py reuses tests/native_argument_ownership/verify.py for negatives with custom marker, payload expression and exact SupportedOperatorFallbacksReleaseOwners/GameTests.MissingOperators.cs stack. It requires exactly one failed NoRuntimesTest TRX result, exit1 and no unrelated engine/runner errors. Positive verification requires one passed structured result, exact counters, no errors and both completion markers.

Every matrix row validates immutable baseline and reviewed fixture hashes. Its source receipt records actual checkout head, immutable baseline commit/blob/SHA, candidate production SHA, mutated SHA, fixture hashes and intended assertion. Verification requires the same actual checkout head and rebuilds exact expected mutation from that committed candidate before accepting the receipt and TRX.

The draft workflow follows the existing proc-initialization ownership workflow: exact PR head, full source/submodules, .NET10.0.401, Python3.12, serialized build and one connected NoRuntimesTest. Matrix is positive/baseline/missing-dispose/divide-reuse, with independent logs/TRX/source receipts uploaded. No workflow was submitted or triggered here.

Five pure-file Python tests passed: exact negative shapes, rejected coincidental failures/errors/exit codes, positive structured success/completion markers, exact production mutation inputs and provenance tampering. These tests neither compile nor run the engine. All DM/C# code and the actual three controls remain uncompiled/unexecuted; source reasoning is not runtime acceptance or memory-impact measurement.

Successor baseline is immutable fork master38c2ca104a2151e4223e1f889e2fc754a921921b, including merged constructor ownership. The baseline control mutates only missing-operator cleanup and DivideRef argument reacquisition. It cannot restore the old98cc whole production file. Constructor and proc fixture hooks are preserved. All connected fixtures, compilation and engine controls remain UNRUN in this source-only bundle.
