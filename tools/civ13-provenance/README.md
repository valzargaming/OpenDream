# Civ13 engine artifact provenance

This branch preserves OpenDream base `b1a452e7fefa36f8919bff38067c602d0bb4e1a5`
and RobustToolbox `af2a7d0406b410c4d960f0f4b34513651c6dc742`. It versions the
Civ13 movement and direction-copy corrections, their production-source probes,
and the Robust authentication-order patch. The dedicated workflow checks out
the exact PR head and does not pull newer engine dependencies.

Run `build.py --output <new-directory>` with .NET 10.0.401 and Python 3.12+.
`--prepare-only` freezes source and dependency hashes without compilation.
Full builds restore their declared dependencies and must not be used in a local
no-restore resource slot. Untracked source/resources (including ignored files)
are rejected; the complete Robust diff must equal the declared auth patch.
Every recursive dependency must match its pinned gitlink, have unchanged tracked
inputs, and pass the same ignored/untracked input check before inventory.
Builds use one MSBuild node with compiler servers disabled. No test launches a
game, connects a client, installs files, changes settings or accesses accounts.

The receipt binds the exact source tree, dependency patch, SDK, logs and output
hashes. Tests require 211 glide assertions, two intended movement failures,
direction-copy assertions and an intended historical direction-copy failure.
Full client, Shared, server and authentication-loader builds follow the probes.
The loader is then rebuilt/published with optimized `Tools` configuration and
`RobustToolsBuild=true`, matching the existing authenticated launcher capability.
Release omits `launchauth`: CI requires that Release negative control to fail
the metadata contract, and the Tools loader to retain the command type, getter,
Execute method and SQLite reference. Complete loader/WebView dependency bundles
are hashed separately. This does not read accounts or prove authenticated join.
Spatial verb production-body assertions and two intended historical failures
also run before the final rebuild. A Runtime DLL candidate is now retained
with its exact source/hash receipt for the server authorization change.
The candidate mount contains matching client/Shared assemblies and source
resources. The installed Gaia runtime has a separate spawn-pool patch at
`10360211767d6ea26fa20e1a32d2b2da84a1f9b1`; these outputs must never overwrite
that runtime DLL without a separate reviewed runtime candidate/rollback and
the exclusive runtime owner's tested replacement slot. The current source
retains the merged spawn-pool patch. No installation, packaging release or runtime restart
is performed by this workflow.

Historical installed hashes `7c4f17e9...` (client mount) and `59454ebf...`
(Shared) match existing local build outputs, but have no exact engine CI receipt.
A new verified candidate may have different hashes. Installation needs a
reviewed manifest, rollback copies and the existing runtime owner's agreement.
Compilation and behavior probes do not establish authenticated joining,
rendering, gameplay, persistence or extraction-loop acceptance.
