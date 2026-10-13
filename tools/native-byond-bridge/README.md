# Native BYOND observation

The Windows client uses a separately compiled, finite native BYOND world to observe
the logged-in native client's read-only key and computer_id. Connecting opens the
registered `byond://` handler. The connection screen explains that this may leave
the current native BYOND game before the player connects. BYOND must already be
installed and logged in. The
observer rejects guests, accepts only loopback clients and never reads passwords or
account credential storage. This is a client report, without spoof-resistance claims.

The isolated native workflow compiles with BYOND 516.1681 and packages bridge.dmb,
native-observer.json and bridge.rsc when emitted, binding output/source hashes to the exact commit.
Resource-free worlds can have no RSC; the manifest explicitly binds that absence.
Unpack these together in an operator-chosen directory. In the client's configuration:

```toml
[opendream]
native_byond_bin = 'C:\Program Files (x86)\BYOND\bin'
native_observer_directory = 'C:\OpenDream\native-observer'
```

Both paths must be absolute. Missing configuration/artifacts fail the connection.
No helper is downloaded, compiled or installed automatically by the client. The
daemon binds loopback to its own available port, runs in safe mode in a unique temporary
directory, has a 60-second lifetime and is hidden. Every completion, error, replacement
and disconnect cancels/releases its owned world. Cleanup does not stop existing games
or a native pager. Native launch may open a native client window for the observation.

To require native identity on a server, use the accompanying example configuration.
The server issues a fresh challenge on the actual connected channel, validates its
epoch/session generation/nonce and consumes a single report immediately before DM
client creation. DM client key and CID then come from the accepted native report,
preserving CID text exactly. Robust's network username is not the native key. There
is no hash/volume-ID/native-identity fallback in required mode. Optional server mode
retains historical behavior for other codebases and isolated tests.

Actual native account/CID parity and a real authenticated admin join/save have not
been established by injected tests or compilation. Do not activate or deploy this
path until those acceptance gates pass. Player identity is not MCP administrator
authorization.
