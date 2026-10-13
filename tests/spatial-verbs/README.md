# Spatial verb regressions

`generate.py` copies the current production client verb enumerator, server
authorization method and shared visibility helpers verbatim into an offline
probe. ViewAlgorithm and ViewRange are linked directly. Map/entity/transport
adapters are inert; the range adapter is distance-only and does not test all
range builtin semantics. The probe exercises all eight spatial accessibility
variants, connected/absent mob guards, radius/grid limits, opaque obstruction,
temporary list release and view/oview center handling.

CI requires a passing probe and two failures: the old inverted client guard
must reject nearby verbs, and the old server view-to-range route must wrongly
permit an occluded target. Generated copies are under obj and regenerated for
every run. Full engine builds and existing tests provide real type coverage.
These offline controls do not prove an authenticated player joined Civ13,
rendered a verb, invoked it successfully or completed any gameplay loop.
