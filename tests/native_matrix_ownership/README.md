# Native matrix and synchronous initialization ownership

The production changes release the native matrix creator only on propagated InitSpawn failure and dispose copied creation arguments in the direct NoConstructors branch's finally. The constructor-bearing branch is unchanged.

The explicit standalone suite uses compiled DM and real ContentIntegrationTest server services. Run FastRejectionsAndTransfers and ConstructorModePreservesRuntimeDelivery in separate dotnet test processes, because BYOND API initialization is process-global. Ordinary GameTests.NoRuntimesTest also requires a fresh process.

Fast cases cover 28 kind/position combinations x 100 actual native calls. Null/string isolate matrix creator retention; datum/list and repeated six-position aliases measure copied caller owners. Baseline, omitted creator and omitted arguments controls assert exact real retention counts rather than treating arbitrary test failure as proof. Generic RejectingDatum directly exercises InitSpawn with two copied caller operands to demonstrate the common contract independently of matrix. Controls clean observed leaks only after asserting their actual ownership and bucket signatures.

Success tests exercise zero/six arguments, clone independence, first-matrix six-argument clone semantics, local-result lifetime and final buckets. The constructor-mode project forces /matrix/New and observes one successful callback, one actual runtime delivered through world.Error and existing partial returned matrix. The deliberate world.Error adapter logs its precise exception name. It does not suppress unexpected diagnostics: C# asserts actual OnException type/message/count, and parser rejects every unrelated engine error. This establishes delivery into the actual error machinery, not compatibility of the default world's logger output.

The workflow follows the existing associative ownership suite: exact selected head/source binding, prepared-source receipt, full original build log, isolated test processes, original TRX/runtime logs, binary hashes and artifact upload. Source preparation mutates only the disposable CI checkout. Baseline/control modes are passing observation tests whose oracles require specific retention; positive requires zero retained matrices and exact released operand counts. Fresh ordinary NoRuntimes is required in every mode.

Pure unit tests exercise exact source mutations and hostile TRX/log shapes. They do not launch the engine and do not establish native acceptance. Until actual compiler, native and workflow results exist, this remains a detached candidate.
