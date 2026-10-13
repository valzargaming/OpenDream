# Procedure initialization ownership

The production factories accept owned `DreamProcArguments`. A rejected factory
has not pushed a state onto its thread, so thread disposal cannot release its
input or a partially initialized frame. Async frames physically store 128
arguments; DM frames share 256 slots between effective arguments (including
declared missing arguments) and compiled locals. Null DM procedures retain their
existing argument-disposal path and do not use these frame slots.

The guards dispose rejected input before taking a pool slot, instance/usr owners,
or an operand-stack rental. Supported calls retain their existing initialization.
Async overflow preserves `ArgumentException` with `destination`; DM overflow
preserves `IndexOutOfRangeException`. Insufficient shared argument/local space is
rejected before procedure execution rather than failing later during local
access or frame disposal.

`GameTests.ProcInitialization.cs` uses actual engine objects, factories, DM
execution and reference-manager buckets on the existing connected server. It
repeats 1000 async 128/129, DM 256/257 and compiled-local budget boundaries,
checks real DM `arglist` catches and executes supported boundary calls. Four
isolated CI controls restore immutable factories or omit only input disposal;
structured TRX verification accepts only the exact retained-owner assertion and
rejects unrelated runtimes, build failures, or coincident test failures.

These tests are not evidence that Gaia exercised oversized calls or that the
whole server has stopped leaking. Positive runtime and omission controls remain
unrun until their exact commit workflow completes.
