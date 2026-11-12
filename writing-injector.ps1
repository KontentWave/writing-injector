[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Generate,
    [AllowEmptyCollection()]
    [AllowEmptyString()]
    [ValidateNotNull()]
    [string[]]$CliArgs = @()
)

$arguments = [System.Collections.Generic.List[string]]::new()
if ($CliArgs.Count -eq 0) {
    if ($Generate) {
        [Console]::Error.WriteLine('[FAIL] -Generate requires a nonempty -CliArgs array.')
        exit 2
    }
    $arguments.Add('--help')
}
elseif (-not $Generate) {
    $offlineMode = $false
    # Only complete CLI options before '--' count, not flag-shaped text inside values.
    foreach ($argument in $CliArgs) {
        if ($argument -ceq '--') { break }
        if ($argument -cin @('-h', '--help', '--dry-run', '--lint-only') -or
            $argument.StartsWith('--lint-only=', [StringComparison]::Ordinal)) {
            $offlineMode = $true
            break
        }
    }
    if (-not $offlineMode) { $arguments.Add('--dry-run') }
}
foreach ($argument in $CliArgs) { $arguments.Add($argument) }

$executable = Join-Path $PSScriptRoot '.venv\Scripts\zafo-inject.exe'
if (-not [IO.File]::Exists($executable)) {
    [Console]::Error.WriteLine('[FAIL] The launcher requires .venv\Scripts\zafo-inject.exe beside it.')
    exit 2
}
$location = Get-Location
if ($location.Provider.Name -ne 'FileSystem') {
    [Console]::Error.WriteLine('[FAIL] Run the launcher from a PowerShell filesystem location.')
    exit 2
}

$process = [Diagnostics.Process]::new()
try {
    $process.StartInfo.FileName = $executable
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.WorkingDirectory = $location.ProviderPath
    foreach ($argument in $arguments) { $process.StartInfo.ArgumentList.Add($argument) }
    if (-not $process.Start()) {
        throw [InvalidOperationException]::new('The CLI process did not start.')
    }
    $process.WaitForExit()
    $exitCode = $process.ExitCode
}
catch [System.ComponentModel.Win32Exception], [InvalidOperationException], [ArgumentException] {
    [Console]::Error.WriteLine('[FAIL] Unable to launch the shared CLI.')
    $exitCode = 2
}
finally {
    $process.Dispose()
}
exit $exitCode
