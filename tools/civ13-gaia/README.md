# Immutable Gaia compile candidate

This workflow compiles a new candidate from Civ13 source
`b8a61dd5d9afed3a5716f62b27c280db4064a427`, with one explicitly overridden map
include: `maps/nomads/nomads_gaia.dmm`. The intended profile is Nomads Gaia Classic
Stone Age Start. Runtime profile/configuration agreement and actual startup are
separate acceptance gates; compilation cannot prove that configured mode.

The compiler is built at the exact engine PR head, RobustToolbox is pinned at
`af2a7d0406b410c4d960f0f4b34513651c6dc742`, SDK is 10.0.401, and compatibility is
516.1681. No additional preprocessor defines are injected; OPENDREAM comes from
the compiler. The receipt retains immutable source trees and hashes, DME/map
override, compiler bundle hashes, invocation, warnings and generated JSON hash.
The compiler is explicitly rebuilt before publication. CI seeds an invalid
stale compiler output and requires its replacement plus successful compilation.

No server/client is launched and no existing installation, saves or config is
changed. The old installed `FA0C1762...` JSON is not retrospectively attributed
to this source. A reviewed candidate needs a matching complete source tree,
runtime-owner timing agreement, rollback and genuine gameplay/persistence
acceptance before replacement. The separately patched Runtime `8CE99FE1...`
must be preserved.
