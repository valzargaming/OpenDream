using OpenDreamPackageTool;

internal static class SelectionProbe {
    private static void Require(bool condition, string marker) {
        if (!condition)
            throw new InvalidOperationException("PACKAGING ASSERTION: " + marker);
    }

    private static int Main() {
        var root = Path.Combine(Path.GetTempPath(), "opendream-packaging-" + Guid.NewGuid());
        var source = Path.Combine(root, "Content.Server");
        var dest = Path.Combine(root, "Assemblies");
        Directory.CreateDirectory(source);
        Directory.CreateDirectory(dest);
        try {
            // Creation order intentionally differs from lexical selection order.
            foreach (var filename in new[] { "OpenDreamRuntime.pdb", "Microsoft.CodeAnalysis.dll",
                         "OpenDreamRuntime.Zeta.dll", "OpenDreamRuntime.dll", "Unrelated.dll" })
                File.WriteAllText(Path.Combine(source, filename), filename);
            var selected = ContentAssemblySelection.Select(source, new[] { "OpenDreamRuntime" },
                new[] { "OpenDreamRuntime", "Microsoft" }, new[] { "Microsoft.CodeAnalysis" });
            Require(selected.Count(name => name == "OpenDreamRuntime.dll") == 1 &&
                    selected.Count(name => name == "OpenDreamRuntime.pdb") == 1, "unique-overlap");
            Require(selected.Contains("OpenDreamRuntime.Zeta.dll"), "source-relative-prefix");
            Require(!selected.Contains("Microsoft.CodeAnalysis.dll") && !selected.Contains("Unrelated.dll"),
                "existing-exclusions");
            Require(selected.SequenceEqual(new[] { "OpenDreamRuntime.Zeta.dll", "OpenDreamRuntime.dll",
                "OpenDreamRuntime.pdb" }), "deterministic-order");
            Require(selected.SequenceEqual(ContentAssemblySelection.Select(source,
                new[] { "OpenDreamRuntime" }, new[] { "OpenDreamRuntime", "Microsoft" },
                new[] { "Microsoft.CodeAnalysis" })), "repeatable-selection");
            foreach (var filename in selected)
                File.Copy(Path.Combine(source, filename), Path.Combine(dest, filename));
            Require(Directory.GetFiles(dest).Length == 3 && selected.All(filename =>
                File.ReadAllText(Path.Combine(dest, filename)) == filename), "copy-without-overwrite");

            var missing = ContentAssemblySelection.Select(source, new[] { "RequiredMissing" },
                Array.Empty<string>(), Array.Empty<string>());
            Require(missing.SequenceEqual(new[] { "RequiredMissing.dll" }), "required-missing-retained");
            var missingFailed = false;
            try {
                File.Copy(Path.Combine(source, missing[0]), Path.Combine(dest, missing[0]));
            } catch (FileNotFoundException) {
                missingFailed = true;
            }
            Require(missingFailed, "required-missing-copy-error");
            Require(!missing.Contains("RequiredMissing.pdb"), "optional-missing-pdb");

            var bases = ContentAssemblySelection.Select(source,
                new[] { "RequiredSecond", "RequiredFirst", "RequiredSecond" },
                Array.Empty<string>(), Array.Empty<string>());
            Require(bases.SequenceEqual(new[] { "RequiredSecond.dll", "RequiredFirst.dll" }),
                "base-order-and-uniqueness");
            Console.WriteLine("PACKAGING SELECTION PASSED: actual linked production helper; overlap, prefix, exclusions, order, copy, required missing, optional PDB");
            return 0;
        } catch (Exception error) {
            Console.Error.WriteLine(error);
            return 1;
        } finally {
            Directory.Delete(root, recursive: true);
        }
    }
}
