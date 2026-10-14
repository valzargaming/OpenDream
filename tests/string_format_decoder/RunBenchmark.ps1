[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$DotnetPath,
    [Parameter(Mandatory)][string]$BuildRoot,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [ValidateRange(2,4)][int]$Flushes = 3,
    [ValidateRange(10,90)][int]$PerProcessSeconds = 90,
    [ValidateRange(30,600)][int]$TotalSeconds = 300,
    [ValidateRange(67108864,2147483648)][long]$MemoryCapBytes = 2147483648
)
# Prepared only. Requires root's exclusive native queue authorization.
# Compile each Variant into BuildRoot/<variant> BEFORE this runner is invoked.
$ErrorActionPreference = 'Stop'
$dotnet = (Resolve-Path -LiteralPath $DotnetPath).Path
if ([IO.Path]::GetFileName($dotnet) -notin @('dotnet.exe','dotnet')) { throw 'Expected explicit trusted dotnet executable' }
$buildDirectory = (Resolve-Path -LiteralPath $BuildRoot).Path
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$variants = @('baseline','decoder')
foreach ($variant in $variants) {
    if (-not (Test-Path -LiteralPath (Join-Path $buildDirectory "$variant/Benchmark.dll"))) { throw "Missing $variant build" }
}
$totalTimer = [Diagnostics.Stopwatch]::StartNew()
$receipts = [Collections.Generic.List[object]]::new()
$reference = @{}
foreach ($size in @(1,16,64)) {
    foreach ($variant in $variants) {
        if ($totalTimer.Elapsed.TotalSeconds -ge $TotalSeconds) { throw 'Total wall cap reached before launch' }
        $dll = Join-Path $buildDirectory "$variant/Benchmark.dll"
        $start = [Diagnostics.ProcessStartInfo]::new()
        $start.FileName = $dotnet
        $start.ArgumentList.Add($dll)
        $start.ArgumentList.Add([string]$size)
        $start.ArgumentList.Add([string]$Flushes)
        $start.UseShellExecute = $false
        $start.CreateNoWindow = $true
        $start.RedirectStandardOutput = $true
        $start.RedirectStandardError = $true
        $process = [Diagnostics.Process]::new()
        $process.StartInfo = $start
        $runTimer = [Diagnostics.Stopwatch]::StartNew()
        $peakPrivate = 0L
        $peakWorking = 0L
        $capReason = $null
        $started = $false
        try {
            if (-not $process.Start()) { throw 'Process start failed' }
            $started = $true
            $stdoutTask = $process.StandardOutput.ReadToEndAsync()
            $stderrTask = $process.StandardError.ReadToEndAsync()
            while (-not $process.WaitForExit(100)) {
                $process.Refresh()
                $peakPrivate = [Math]::Max($peakPrivate, $process.PrivateMemorySize64)
                $peakWorking = [Math]::Max($peakWorking, $process.WorkingSet64)
                if ($peakPrivate -gt $MemoryCapBytes -or $peakWorking -gt $MemoryCapBytes) { $capReason = 'memory' }
                if ($runTimer.Elapsed.TotalSeconds -ge $PerProcessSeconds) { $capReason = 'process-wall' }
                if ($totalTimer.Elapsed.TotalSeconds -ge $TotalSeconds) { $capReason = 'total-wall' }
                if ($capReason) {
                    $process.Kill($true)
                    break
                }
            }
            $process.WaitForExit()
            $stdout = $stdoutTask.GetAwaiter().GetResult()
            $stderr = $stderrTask.GetAwaiter().GetResult()
            [IO.File]::WriteAllText((Join-Path $outputPath "$variant-$size.jsonl"), $stdout)
            [IO.File]::WriteAllText((Join-Path $outputPath "$variant-$size.stderr.txt"), $stderr)
            $receipt = [pscustomobject]@{
                variant = $variant; payloadMiB = $size; exitCode = $process.ExitCode
                capReason = $capReason; wallSeconds = $runTimer.Elapsed.TotalSeconds
                sampledPeakPrivateBytes = $peakPrivate; sampledPeakWorkingSetBytes = $peakWorking
                memoryCapBytes = $MemoryCapBytes; sampleIntervalMilliseconds = 100
                dllSha256 = (Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
                dotnetPath = $dotnet
            }
            $receipts.Add($receipt)
            $receipts | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputPath 'process-receipts.json') -Encoding utf8
            if ($capReason -or $process.ExitCode -ne 0 -or $stderr.Trim()) { throw "Rejected $variant/$size run: exit=$($process.ExitCode), cap=$capReason, stderr=$stderr" }
            $rows = @($stdout -split '\r?\n' | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
            if ($rows.Count -ne $Flushes) { throw 'Missing measured flush rows' }
            for ($iteration = 0; $iteration -lt $rows.Count; $iteration++) {
                $row = $rows[$iteration]
                if ($row.variant -ne 'decoder-resource-seam' -or $row.requestedPayloadMiB -ne $size -or $row.flushCount -ne 1 -or $row.iteration -ne $iteration) { throw 'Workload/flush-count mismatch' }
                $key = "$size/$iteration"
                $fingerprint = "$($row.members):$($row.outputBytes):$($row.sha256)"
                if ($variant -eq 'baseline') { $reference[$key] = $fingerprint }
                elseif ($reference[$key] -ne $fingerprint) { throw 'Cross-variant member/byte/hash mismatch' }
            }
        } finally {
            if ($started -and -not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
            $process.Dispose()
        }
    }
}
Write-Output 'Completed bounded source-seam benchmark; inspect receipts and per-run metrics before making claims.'
