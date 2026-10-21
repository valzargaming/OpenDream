namespace OpenDreamPackageTool;

internal static class ContentAssemblySelection {
    // Return source-relative filenames once, in deterministic copy order.
    internal static IReadOnlyList<string> Select(string sourceDir, IEnumerable<string> contentAssemblies,
        IEnumerable<string> extraPrefixes, IEnumerable<string> excludedPrefixes) {
        var files = new List<string>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var extras = extraPrefixes.ToArray();
        var excluded = excludedPrefixes.ToArray();

        foreach (var filename in Directory.EnumerateFiles(sourceDir)
                     .Select(Path.GetFileName).OrderBy(name => name, StringComparer.Ordinal)) {
            if (filename is not null &&
                extras.Any(prefix => filename.StartsWith(prefix, StringComparison.Ordinal)) &&
                !excluded.Any(prefix => filename.StartsWith(prefix, StringComparison.Ordinal)) &&
                seen.Add(filename))
                files.Add(filename);
        }

        foreach (var assembly in contentAssemblies) {
            var dll = assembly + ".dll";
            // Required DLLs stay in the copy list even when absent: File.Copy must fail.
            if (seen.Add(dll))
                files.Add(dll);
            var pdb = assembly + ".pdb";
            if (File.Exists(Path.Combine(sourceDir, pdb)) && seen.Add(pdb))
                files.Add(pdb);
        }

        return files;
    }
}
