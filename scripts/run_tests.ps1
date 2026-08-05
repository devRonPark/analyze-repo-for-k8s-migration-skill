[CmdletBinding()]
param(
    [switch] $NoCache,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $PytestArgs
)

$ErrorActionPreference = "Continue"
$worktreeRoot = (Get-Location).Path
$cleanupFailures = @()
$legacyTempRoots = @()
Get-ChildItem -Path $worktreeRoot -Force -Directory -Filter ".pytest-temp-*" -ErrorAction SilentlyContinue |
    ForEach-Object { $legacyTempRoots += $_ }
Get-ChildItem -Path $worktreeRoot -Force -Directory -Filter "pytest-cache-files-*" -ErrorAction SilentlyContinue |
    ForEach-Object { $legacyTempRoots += $_ }
if (Test-Path -Path (Join-Path $worktreeRoot ".task3-test-temp")) {
    $legacyTempRoots += Get-Item -Path (Join-Path $worktreeRoot ".task3-test-temp") -Force
}
foreach ($legacyTempRoot in $legacyTempRoots) {
    if (($legacyTempRoot.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        $cleanupFailures += "refusing reparse-point residue: $($legacyTempRoot.FullName)"
        continue
    }
    $resolvedLegacyRoot = (Resolve-Path -Path $legacyTempRoot.FullName -ErrorAction Stop).Path
    if (-not $resolvedLegacyRoot.StartsWith($worktreeRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove path outside worktree: $resolvedLegacyRoot"
    }
    try {
        Remove-Item -LiteralPath $resolvedLegacyRoot -Recurse -Force -ErrorAction Stop
    } catch {
        $cleanupFailures += "worktree residue cleanup failed: $resolvedLegacyRoot :: $($_.Exception.Message)"
    }
}
if ($cleanupFailures.Count -gt 0) {
    $cleanupFailures | ForEach-Object { Write-Error $_ }
    exit 2
}
$argsForPytest = @("-p", "no:cacheprovider") + $PytestArgs
$output = @()
$exitCode = 1
try {
    $output = & python -m pytest @argsForPytest 2>&1
    $exitCode = $LASTEXITCODE
} finally {
    $output | Write-Output
    $endResidues = @()
    Get-ChildItem -Path $worktreeRoot -Force -Directory -Filter ".pytest-temp-*" -ErrorAction SilentlyContinue |
        ForEach-Object { $endResidues += $_ }
    Get-ChildItem -Path $worktreeRoot -Force -Directory -Filter "pytest-cache-files-*" -ErrorAction SilentlyContinue |
        ForEach-Object { $endResidues += $_ }
    if (Test-Path -Path (Join-Path $worktreeRoot ".task3-test-temp")) {
        $endResidues += Get-Item -Path (Join-Path $worktreeRoot ".task3-test-temp") -Force
    }
    foreach ($endResidue in $endResidues) {
        if (($endResidue.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            $cleanupFailures += "refusing reparse-point residue: $($endResidue.FullName)"
            continue
        }
        $resolvedEndResidue = (Resolve-Path -Path $endResidue.FullName -ErrorAction Stop).Path
        if (-not $resolvedEndResidue.StartsWith($worktreeRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            $cleanupFailures += "refusing path outside worktree: $resolvedEndResidue"
            continue
        }
        try {
            Remove-Item -LiteralPath $resolvedEndResidue -Recurse -Force -ErrorAction Stop
        } catch {
            $cleanupFailures += "worktree residue cleanup failed: $resolvedEndResidue :: $($_.Exception.Message)"
        }
    }
}

if ($cleanupFailures.Count -gt 0) {
    $cleanupFailures | ForEach-Object { Write-Error $_ }
    if ($exitCode -eq 0) { $exitCode = 2 }
}

if ($exitCode -ne 0 -and ($output -match "WinError 5") -and ($output -match "tempfile|TemporaryDirectory|\\tmp")) {
    Write-Error "managed Windows sandbox tempfile ACL 오류입니다. docs/testing.md의 owner-scoped clear 및 권한 승인 절차를 확인하세요."
    exit 2
}

exit $exitCode
