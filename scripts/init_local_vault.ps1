#requires -Version 7.0
[CmdletBinding()]
param(
    [string]$VaultDir = $(if ($env:ZAFO_VAULT_DIR) { $env:ZAFO_VAULT_DIR } else {
        Join-Path $HOME 'zafo-local'
    }),
    [string]$LexiconPath = (Join-Path $PSScriptRoot '..\..\zafo-shorts\blog\docs\SLOVAK_LEXICON.md'),
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

function Get-AbsolutePath([string]$Path) {
    $providerPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
    return [IO.Path]::GetFullPath($providerPath)
}

function Get-CanonicalPath([string]$Path) {
    $full = Get-AbsolutePath $Path
    if (Test-Path -LiteralPath $full) {
        $item = Get-Item -LiteralPath $full -Force
        if ($item.LinkType) {
            return $item.ResolveLinkTarget($true).FullName
        }
    }
    $parent = Split-Path -Parent $full
    if ($parent -and $parent -ne $full) {
        return Join-Path (Get-CanonicalPath $parent) (Split-Path -Leaf $full)
    }
    return $full
}

function Assert-SafePath([string]$Path) {
    $full = Get-AbsolutePath $Path
    $canonical = Get-CanonicalPath $full
    if ([IO.Path]::GetPathRoot($full).Replace('\\?\', '') -ieq 'D:\' -or
        [IO.Path]::GetPathRoot($canonical).Replace('\\?\', '') -ieq 'D:\') {
        throw 'All of drive D: is forbidden for vault storage.'
    }
    $workspace = Get-CanonicalPath (Split-Path -Parent $PSScriptRoot)
    if ($canonical -ieq $workspace -or
        $canonical.StartsWith($workspace.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Vault storage must be outside the workspace.'
    }
    if ($canonical -match '(?i)(^|\\)(Google Drive|GoogleDrive|My Drive|Shared drives|\.shortcut-targets-by-id)(\\|$)') {
        throw 'Google Drive storage is forbidden.'
    }
    if ($env:GOOGLE_DRIVE_DIR) {
        $cloud = Get-CanonicalPath $env:GOOGLE_DRIVE_DIR
        if ($canonical -ieq $cloud -or
            $canonical.StartsWith($cloud.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Configured Google Drive storage is forbidden.'
        }
    }
    $ancestor = $canonical
    while ($ancestor) {
        if (Test-Path -LiteralPath $ancestor -PathType Container) {
            $markers = Get-ChildItem -LiteralPath $ancestor -File -Force |
                Where-Object { $_.Extension -in '.gdoc', '.code-workspace' } |
                Select-Object -First 1
            if ($markers) { throw 'Vault storage has cloud or workspace markers.' }
        }
        $parent = Split-Path -Parent $ancestor
        if ($parent -eq $ancestor) { break }
        $ancestor = $parent
    }
    return $canonical
}

try {
    $vault = Assert-SafePath $VaultDir
    $output = Assert-SafePath (Join-Path $vault 'output')
    if ($output -ine (Join-Path $vault 'output')) { throw 'Output must not be redirected by links.' }
    $envPath = Assert-SafePath (Join-Path $vault '.env')
    $addonPath = Assert-SafePath (Join-Path $vault 'TIER4_ADDON.txt')
    if ($envPath -ine (Join-Path $vault '.env') -or
        $addonPath -ine (Join-Path $vault 'TIER4_ADDON.txt')) {
        throw 'Vault files must not be redirected by links.'
    }
    $writeAddon = $Force -or -not (Test-Path -LiteralPath $addonPath) -or
        [string]::IsNullOrWhiteSpace([IO.File]::ReadAllText($addonPath))
    $addon = $null
    if ($writeAddon) {
        $lexicon = [IO.File]::ReadAllText((Get-CanonicalPath $LexiconPath))
        $inSection = $false
        $outerFence = ''
        $fence = ''
        $complete = $false
        $sectionLevel = 0
        $lines = [Collections.Generic.List[string]]::new()
        foreach ($line in [regex]::Split($lexicon, '\r?\n')) {
            if (-not $inSection) {
                if ($outerFence) {
                    if ($line -match '^ {0,3}(`{3,}|~{3,})\s*$' -and
                        $Matches[1][0] -eq $outerFence[0] -and
                        $Matches[1].Length -ge $outerFence.Length) {
                        $outerFence = ''
                    }
                } elseif ($line -match '^ {0,3}(`{3,}|~{3,})') {
                    $outerFence = $Matches[1]
                } elseif ($line -match '^(#{1,6})\s+(?:§\s*)?6(?:\\?\.[\s\S]*|[ ):\t][\s\S]*|$)') {
                    $inSection = $true
                    $sectionLevel = $Matches[1].Length
                }
                continue
            }
            if (-not $fence) {
                if ($line -match '^(#{1,6})\s+' -and $Matches[1].Length -le $sectionLevel) { break }
                if ($line -match '^ {0,3}(`{3,}|~{3,})') { $fence = $Matches[1] }
            } elseif ($line -match '^ {0,3}(`{3,}|~{3,})\s*$' -and
                      $Matches[1][0] -eq $fence[0] -and $Matches[1].Length -ge $fence.Length) {
                $complete = $true
                break
            } else {
                $lines.Add($line)
            }
        }
        $addon = ($lines -join "`n").Trim() + "`n"
        if (-not $complete -or [string]::IsNullOrWhiteSpace($addon)) {
            throw 'Lexicon section 6 must contain a nonempty fenced addon skeleton.'
        }
    }
    [IO.Directory]::CreateDirectory($output) | Out-Null
    $encoding = [Text.UTF8Encoding]::new($false)
    if ($Force -or -not (Test-Path -LiteralPath $envPath)) {
        [IO.File]::WriteAllText($envPath, "OPENROUTER_API_KEY=`n", $encoding)
    }
    if ($writeAddon) { [IO.File]::WriteAllText($addonPath, $addon, $encoding) }
    Write-Output '[PASS] Vault initialized. Existing filled files preserved unless -Force was supplied.'
    exit 0
} catch {
    Write-Error -Message '[FAIL] Vault initialization failed. Check path boundaries, permissions, and lexicon format.' -ErrorAction Continue
    exit 2
}
