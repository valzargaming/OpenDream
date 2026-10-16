using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Robust.Client.NativeByond;

/// <summary>
/// Windows native BYOND observation. Executables and a CI-built helper are operator-configured.
/// Opens the registered BYOND URI handler to use its logged-in account; never reads credentials.
/// </summary>
internal sealed class FileNativeObserverHost : INativeObserverHost {
    public Task<INativeObservation> StartAsync(NativeObserverOptions options, NativeIdentityRequest request,
        CancellationToken cancellation) => Task.Run<INativeObservation>(() => Start(options, request, cancellation), cancellation);

    private static INativeObservation Start(NativeObserverOptions options, NativeIdentityRequest request,
        CancellationToken cancellation) {
        if (!OperatingSystem.IsWindows() || !Path.IsPathFullyQualified(options.ByondBin) ||
            !Path.IsPathFullyQualified(options.ObserverDirectory))
            throw new InvalidOperationException("Configure the Windows BYOND bin and native observer artifact directories.");
        var daemonPath = Path.Combine(options.ByondBin, "DreamDaemon.exe");
        if (!File.Exists(daemonPath)) throw new FileNotFoundException("Native DreamDaemon is unavailable.");
        var manifestPath = Path.Combine(options.ObserverDirectory, "native-observer.json");
        using var manifest = ReadJson(manifestPath, 65536);
        var root = manifest.RootElement;
        if (root.GetProperty("schema").GetInt32() != 1 || root.GetProperty("byond_version").GetString() != "516.1681")
            throw new InvalidDataException("Native observer artifact has an unsupported manifest.");
        var files = root.GetProperty("files");
        var parent = Path.Combine(Path.GetTempPath(), "opendream-native-observation");
        Directory.CreateDirectory(parent);
        var directory = Path.Combine(parent, Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        Process? daemon = null;
        try {
            foreach (var name in new[] { "bridge.dmb", "bridge.rsc" }) {
                cancellation.ThrowIfCancellationRequested();
                var source = Path.Combine(options.ObserverDirectory, name);
                var declared = files.GetProperty(name);
                if (name == "bridge.rsc" && declared.ValueKind == JsonValueKind.Null) {
                    if (File.Exists(source)) throw new InvalidDataException("Unbound native observer RSC is present.");
                    continue;
                }
                var info = new FileInfo(source);
                if (!info.Exists || info.Length > 4 * 1024 * 1024) throw new InvalidDataException("Invalid native helper size.");
                // Verify the exact bytes copied, avoiding a second read of mutable artifact files.
                using var input = new FileStream(source, FileMode.Open, FileAccess.Read, FileShare.Read);
                if (input.Length > 4 * 1024 * 1024) throw new InvalidDataException("Invalid native helper size.");
                var bytes = new byte[(int)input.Length];
                input.ReadExactly(bytes);
                var digest = Convert.ToHexString(SHA256.HashData(bytes));
                if (!string.Equals(digest, declared.GetString(), StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("Native observer artifact hash mismatch.");
                File.WriteAllBytes(Path.Combine(directory, name), bytes);
            }
            File.WriteAllText(Path.Combine(directory, "bridge-request.json"), JsonSerializer.Serialize(new {
                epoch = request.Epoch.ToString("D"), nonce = request.Nonce
            }));
            cancellation.ThrowIfCancellationRequested();
            var start = new ProcessStartInfo(daemonPath) {
                WorkingDirectory = directory, UseShellExecute = false, CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            };
            foreach (var argument in new[] { "bridge.dmb", "0", "-safe", "-quiet", "-nowebclient", "-ip", "127.0.0.1", "-log", "observer.log" })
                start.ArgumentList.Add(argument);
            daemon = Process.Start(start) ?? throw new InvalidOperationException("Native observer could not start.");
            return new Observation(parent, directory, daemon);
        } catch {
            try {
                if (daemon != null) {
                    try { if (!daemon.HasExited) daemon.Kill(entireProcessTree: true); } finally { daemon.Dispose(); }
                }
            } finally { RemoveOwnedDirectory(parent, directory); }
            throw;
        }
    }

    private static JsonDocument ReadJson(string path, int maximum) {
        using var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        if (input.Length <= 0 || input.Length > maximum) throw new InvalidDataException("Native report size is invalid.");
        var bytes = new byte[(int)input.Length];
        input.ReadExactly(bytes);
        return JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 4 });
    }

    private static void RemoveOwnedDirectory(string parent, string directory) {
        var resolved = Path.GetFullPath(directory);
        if (!string.Equals(Path.GetDirectoryName(resolved), Path.GetFullPath(parent), StringComparison.OrdinalIgnoreCase) ||
            !Guid.TryParseExact(Path.GetFileName(resolved), "N", out _))
            throw new InvalidOperationException("Refusing native observer cleanup outside its unique directory.");
        if (Directory.Exists(resolved)) Directory.Delete(resolved, recursive: true);
    }

    private sealed class Observation(string parent, string directory, Process daemon) : INativeObservation {
        private bool _disposed;

        public async Task<NativeIdentityReport?> ReadAsync(NativeIdentityRequest request, CancellationToken cancellation) {
            // The daemon chooses and binds its own free loopback port, then records readiness.
            var readyPath = Path.Combine(directory, "native-ready.json");
            using (var ready = await WaitJsonAsync(readyPath, cancellation).ConfigureAwait(false)) {
                if (ready == null) return null;
                var root = ready.RootElement;
                if (root.GetProperty("epoch").GetString() != request.Epoch.ToString("D") ||
                    root.GetProperty("nonce").GetString() != request.Nonce) return null;
                var port = root.GetProperty("port").GetInt32();
                if (port < 1 || port > ushort.MaxValue) return null;
                cancellation.ThrowIfCancellationRequested();
                // The shell's BYOND handler selects the actual logged-in native account.
                // Dispose only this launch handle: the handler may delegate to an existing pager.
                using var launch = Process.Start(new ProcessStartInfo($"byond://127.0.0.1:{port}?nonce={request.Nonce}") {
                    UseShellExecute = true
                });
            }
            var reportPath = Path.Combine(directory, "native-report.json");
            using var report = await WaitJsonAsync(reportPath, cancellation).ConfigureAwait(false);
            if (report == null) return null;
            var fields = report.RootElement;
            if (fields.ValueKind != JsonValueKind.Object) return null;
            var count = 0;
            foreach (var field in fields.EnumerateObject()) {
                if (field.Name is not ("epoch" or "nonce" or "key" or "cid")) return null;
                count++;
            }
            if (count != 4 || !Guid.TryParseExact(fields.GetProperty("epoch").GetString(), "D", out var epoch)) return null;
            return new NativeIdentityReport(epoch, fields.GetProperty("nonce").GetString()!,
                fields.GetProperty("key").GetString()!, fields.GetProperty("cid").GetString()!);
        }

        private async Task<JsonDocument?> WaitJsonAsync(string path, CancellationToken cancellation) {
            while (true) {
                cancellation.ThrowIfCancellationRequested();
                try {
                    if (File.Exists(path)) return ReadJson(path, 8192);
                } catch (IOException) { // Native file output may still be in progress.
                } catch (JsonException) {
                }
                if (daemon.HasExited) return null;
                await Task.Delay(50, cancellation).ConfigureAwait(false);
            }
        }

        public async ValueTask DisposeAsync() {
            if (_disposed) return;
            _disposed = true;
            try {
                if (!daemon.HasExited) {
                    daemon.Kill(entireProcessTree: true);
                    using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(5));
                    await daemon.WaitForExitAsync(stop.Token).ConfigureAwait(false);
                }
            } finally {
                daemon.Dispose();
                RemoveOwnedDirectory(parent, directory);
            }
        }
    }
}
