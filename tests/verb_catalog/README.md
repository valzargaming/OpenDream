The client receives a session-wide append-only catalog and incremental registrations.
An incremental event may arrive before the initial catalog contains the same ID.
Both handlers must upsert IDs. A catalog updates its included IDs without clearing
newer registrations beyond its snapshot; session shutdown clears all state.

Run `run.py --dotnet <absolute .NET 10 SDK path> --all-controls --output <directory>`.
The package-free fixture extracts the actual three handlers, Shutdown and network
event definitions. UI refresh and VerbInfo are inert adapters. Thirteen assertions
cover message ordering, duplicate events, older/empty snapshots, active verb removal,
shutdown and reconnect. Three source omissions must fail their intended runtime
assertion; compilation failure never counts as success.

This verifies deterministic handler behavior, not a connected session or server
memory stability. The repository integration test remains a separate CI check.
