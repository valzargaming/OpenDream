# Appearance registry investigation

The suspected retired-ID leak was not reproduced at source head
`10360211767d6ea26fa20e1a32d2b2da84a1f9b1`. No runtime change is proposed.

`ServerAppearanceSystem.Update` removes entries only when their weak proxy is
found in `_appearanceLookup`. A collected appearance followed by an equal live
replacement initially looks like it could prevent removal of the retired ID.
However, `ProxyWeakRef.Equals` first compares registered IDs. The retired proxy
therefore still finds itself after its target is collected, and the replacement
has a distinct registered ID. Removal releases the retired proxy and preserves
the live replacement.

Run from this checkout with a .NET 10 SDK:

```powershell
./tests/appearance_registry/run.ps1 -Dotnet '<absolute-dotnet-path>'
./tests/appearance_registry/run.ps1 -Dotnet '<absolute-dotnet-path>' -NegativeControl
```

The runner extracts the actual production registration, immutable AddAppearance,
removal loop and ProxyWeakRef bodies. Its stand-in appearance implements structural
equality and registered-ID finalization. Each of 100 cycles registers an appearance,
releases the send queue, forces collection/finalization, registers an equal live
replacement, and drains removal. Assertions require removal of the retired ID,
preservation of the replacement and an empty registry after final collection.
The stand-in and isolated single-thread runner do not exercise engine networking,
appearance payload construction, or PVS concurrency.

Verified on 2026-10-13 with .NET SDK 10.0.401:

- Production source: PASS, 100 cycles; final lookup and ID counts are zero.
- Negative control removing only the registered-ID equality guard: FAIL on the
  first cycle, `Retired metadata retained after replacement: lookup=2, IDs=2`.
- Production source SHA256:
  `DEF620562145C606621E5CD17CAFAF42211EB79E79680C358A699A1ACA8849E1`.

These results rule out the proposed normal-lifecycle metadata retention path.
The registry holds weak targets, so stale proxy/ID metadata would not itself root
appearance object graphs. This probe does not attribute Gaia's observed memory
growth, measure its heap, or establish the absence of other appearance leaks.
