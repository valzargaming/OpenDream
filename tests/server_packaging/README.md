# Server packaging selection regression

SelectionProbe.csproj links the actual production ContentAssemblySelection helper. It uses temporary source/destination files to test selection and File.Copy without engine dependencies. Production CopyContentAssemblies passes its existing required, extra-prefix and exclusion arrays into that helper. Mandatory DLLs stay selected even when missing; optional PDBs only enter when present.

The server-packaging-selection workflow runs positive and three omission controls against an exact PR head. It tests the Python verifier, writes a source receipt, separately compiles the linked probe, then runs with --no-build. A build failure skips runtime verification and cannot count as a successful control. Always-retained artifacts include verifier/build/run logs, the source receipt, actual tested helper and frozen source contract.

control.py applies one uniquely anchored mutation: dedup removes extras/base DLL/PDB uniqueness, prefix restores complete-path prefix matching, required filters missing required DLLs. Strict verification requires exit1 and exactly one expected assertion, with only the actual Require/Main SelectionProbe.cs stack. Positive requires exit0 and the exact completion line. Unrelated output, errors, assertion counts and source drift are rejected. Candidate input hashes authenticate against the exact commit; the immutable ebc7 baseline hash is separately recorded. Linux checkout bytes are required for receipt-to-Git byte identity checks; this workflow runs Ubuntu.

Python-only checks: python -m unittest discover -s tests/server_packaging -p test_control.py -v

Remote probe build/run: dotnet build tests/server_packaging/SelectionProbe.csproj -c Release; dotnet run --project tests/server_packaging/SelectionProbe.csproj -c Release --no-build

These checks cover assembly selection and copy contracts only. The real package tool build and generated release artifact inventory remain separate acceptance checks. No engine leak, runtime compatibility, deployment or Gaia attribution follows from probe success.
