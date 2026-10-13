# Client prompt and connection ownership

The existing connected `GameTests.NoRuntimesTest` executes production PromptList,
client statobj assignment, mob transitions and disconnect cleanup on a real engine
server. It checks 1000 repetitions of filtered-empty, cancel/null, negative and
out-of-range response, selected-value and non-cancellable fallback cases. It also
checks empty lists, filtered index mapping, statobj self assignment/replacement,
separate mob/statobj owners, pending list/plain prompt completion, custom camera
release, repeated disconnect, final datum deletion and reference-bucket removal.

The omission workflow builds the actual engine before executing each control.
It restores the immutable pre-fix PromptList method or removes one cleanup/index
guard, then accepts only the exact intended NUnit assertion in one structured TRX
test result. Compilation errors, runtime errors and unrelated failures are rejected
by the existing strict native-argument verifier. Controls mutate CI copies only.

This measures retained object owners and gameplay result contracts. It does not
measure live-server RSS, allocation frequency, ordinary client rendering or prove
that these paths explain Gaia's current growth. All runtime tests remain remote;
no game save, production process, native launcher or external hook is exercised.
