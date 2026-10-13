param(
    [Parameter(Mandatory=$true)][string]$Dotnet,
    [switch]$NegativeControl
)
$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$source = Get-Content -LiteralPath (Join-Path $repository 'OpenDreamRuntime/Rendering/ServerAppearanceSystem.cs') -Raw
function Extract-Block([string]$Text, [string]$Marker) {
    $start = $Text.IndexOf($Marker, [StringComparison]::Ordinal)
    if ($start -lt 0) { throw "Production block missing: $Marker" }
    $open = $Text.IndexOf('{', $start)
    $depth = 1
    for ($cursor = $open + 1; $cursor -lt $Text.Length; $cursor++) {
        if ($Text[$cursor] -eq '{') { $depth++ }
        if ($Text[$cursor] -eq '}') { $depth-- }
        if ($depth -eq 0) { return $Text.Substring($start, $cursor - $start + 1) }
    }
    throw "Unterminated production block: $Marker"
}
$register = Extract-Block $source 'private void RegisterAppearance('
$add = Extract-Block $source 'public ImmutableAppearance AddAppearance(ImmutableAppearance'
$remove = Extract-Block $source 'while (_appearanceRemovalQueue.TryDequeue('
$proxy = Extract-Block $source 'internal sealed class ProxyWeakRef'
if ($NegativeControl) {
    $identityGuard = '        if\(_registeredId is not null && _registeredId == proxy\._registeredId\)\r?\n            return true;\r?\n'
    if ([regex]::Matches($proxy, $identityGuard).Count -ne 1) { throw 'Expected exactly one production identity guard' }
    $proxy = [regex]::Replace($proxy, $identityGuard, '')
}
$probeTemp = Join-Path ([IO.Path]::GetTempPath()) ('opendream-appearance-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $probeTemp | Out-Null
try {
    $generated = @"
using System.Diagnostics.CodeAnalysis;
public sealed class ProductionRegistry {
    private readonly HashSet<ProxyWeakRef> _appearanceLookup = new();
    private readonly Dictionary<uint, ProxyWeakRef> _idToAppearance = new();
    private readonly List<ImmutableAppearance> _appearanceSendQueue = new();
    private readonly Queue<uint> _appearanceRemovalQueue = new();
    private readonly object _lock = new();
    private uint _counter;
    public int LookupCount => _appearanceLookup.Count;
    public int IdCount => _idToAppearance.Count;
    public bool HasId(uint id) => _idToAppearance.ContainsKey(id);
    public void ClearSendQueue() => _appearanceSendQueue.Clear();
    public void Retire(uint id) { lock (_lock) _appearanceRemovalQueue.Enqueue(id); }
    public void Drain() { lock (_lock) { $remove } }
    $register
    $add
}
$proxy
"@
    Set-Content -LiteralPath (Join-Path $probeTemp 'Registry.cs') -Value $generated
    & $Dotnet run --project (Join-Path $PSScriptRoot 'RegistryProbe.csproj') --configuration Release --property:ImportDirectoryPackagesProps=false --property:ProbeGeneratedDirectory=$probeTemp --property:BaseIntermediateOutputPath="$probeTemp/obj/" --property:OutputPath="$probeTemp/bin/" --verbosity quiet
    if ($LASTEXITCODE -ne 0) { throw 'Appearance registry probe failed' }
} finally {
    $resolvedTemp = (Resolve-Path -LiteralPath $probeTemp).Path
    if (!$resolvedTemp.StartsWith([IO.Path]::GetTempPath(), [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe temporary cleanup target' }
    Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
}
