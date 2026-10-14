# Bounded idle list storage

The production pool keeps at most `opendream.list_pool_size` (default 256)
cleared `List<DreamValue>` objects. The prior admission rule had no upper backing
capacity limit. `Clear` releases element references but retains the array.
LIFO rental only calls `EnsureCapacity`, so a huge retired backing array can
also persist through subsequent medium rentals.

The new private 65,536-slot ceiling applies only at retirement. It preserves
the existing 2,048 threshold (strict `>` on return, `>=` on rent), count limit,
LIFO reuse, live lengths and associations. It neither trims arrays nor disables
ordinary pooling. Defaults bound pooled array payload to
`256 * 65536 * Unsafe.SizeOf<DreamValue>()`; native tests record actual struct
size. Live lists, externally retained deleted wrappers, dictionary capacity,
and other pools remain outside this bound. This is not live Gaia attribution.

The explicit, nonparallel NUnit fixture starts a temporary, minimal real
OpenDream world. It exercises production retirement and rentals, CLR weak
array/child release after full GC, exact count/capacity boundaries, real DM
Copy/Cut/iteration above the ceiling, C# associations and child reference counts,
LIFO reuse, and the existing count cap. Reflection observes private storage
without widening production APIs; original static pool entries are restored.

Comparable workloads use the same inputs in all variants: two warmups, eight
create/Resize/retire cycles at 32/4096/65536/65537/131072/350000 entries, plus a
350000-entry burst followed by a medium rental. They record thread allocations,
wall time, GC counts and retained capacities. Releasing large idle arrays can
increase allocation and CPU for repeated large lists; no RSS/speedup claim is
made. The 32 simultaneously live 131072-capacity retirement workload measures
retained payload independently from active list counts.

`control.py` source-binds the original to immutable Git commit
`8b46fd2a6dda5095df1d0fc8db7fd029cd186ba4`. The baseline must fail the capacity
assertion while passing semantics. The nonclearing control removes only Clear
and must fail managed child/empty-storage assertions. The no-pooling control
removes only return eligibility and must fail ceiling admission and medium
reuse. `verify.py` requires exact tests, assertion labels, metrics and fault-free
raw output; compiler/runtime faults are not expected-control success.

The workflow runs Linux and Windows positive plus Linux original and both
controls, preserving prepared source, original build/test logs, TRX and compiled
DLL/PDB hashes. Run pure checks with a verified interpreter:
`<python> -m unittest discover -s tests/list_pool_capacity -v`.
Replays must use `verify.py <original-directory> <mode> --output <derived-directory>`
to keep extracted original artifacts byte-identical.
