# Civ13 engine artifact provenance

This branch preserves OpenDream base `b1a452e7fefa36f8919bff38067c602d0bb4e1a5`
and RobustToolbox `af2a7d0406b410c4d960f0f4b34513651c6dc742`. It versions the
Civ13 movement and direction-copy corrections, their production-source probes,
and the Robust authentication-order patch. The dedicated workflow checks out
the exact PR head and does not pull newer engine dependencies.

Run `build.py --output <new-directory>` with .NET 10.0.401 and Python 3.12+.
`--prepare-only` freezes source and dependency hashes without compilation.
`--offline` forbids restore and requires previously prepared project assets.
Builds use one MSBuild node with compiler servers disabled. No test launches a
game, connects a client, installs files, changes settings or accesses accounts.

The receipt binds the exact source tree, dependency patch, SDK, logs and output
hashes. Tests require 211 glide assertions, two intended movement failures,
direction-copy assertions and an intended historical direction-copy failure.
Full client, Shared, server and authentication-loader builds follow the probes.
The candidate mount contains matching client/Shared assemblies and source
resources. The installed Gaia runtime has a separate spawn-pool patch at
`10360211767d6ea26fa20e1a32d2b2da84a1f9b1`; these outputs must never overwrite
that runtime DLL. No merge, installation, packaging release or runtime restart
is performed by this workflow.

Historical installed hashes `7c4f17e9...` (client mount) and `59454ebf...`
(Shared) match existing local build outputs, but have no exact engine CI receipt.
A new verified candidate may have different hashes. Installation needs a
reviewed manifest, rollback copies and the existing runtime owner's agreement.
Compilation and behavior probes do not establish authenticated joining,
rendering, gameplay, persistence or extraction-loop acceptance.
