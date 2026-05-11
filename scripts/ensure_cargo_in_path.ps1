# Ensures cargo is on PATH for *this* PowerShell process and optionally fixes user PATH in registry.
#
# IMPORTANT: If you are already in PowerShell, run (same window):
#   .\scripts\ensure_cargo_in_path.ps1
# Do NOT use: powershell -File .\scripts\ensure_cargo_in_path.ps1
# The nested powershell is a child process — PATH fixes there do not apply to your current prompt.

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "rust_path_helpers.ps1")

$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$userPathNow = [Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = (@($machinePath, $userPathNow) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join ";"

Sync-RustUserEnvVars

$cargoExe = Get-CargoExePath
if (-not $cargoExe) {
    Write-Host ""
    Write-Host "NOT FOUND: cargo.exe (checked CARGO_HOME, then %USERPROFILE%\.cargo\bin)." -ForegroundColor Red
    Write-Host "Rust (rustup) is not installed for this Windows user, or install paths were moved." -ForegroundColor Yellow
    Write-Host "If C: is full, configure D: first:" -ForegroundColor Yellow
    Write-Host "  .\scripts\setup_rust_on_d.ps1 -CopyFromDefaultProfile -SetUserTemp" -ForegroundColor White
    Write-Host "Otherwise install from: https://rustup.rs/" -ForegroundColor White
    exit 1
}

$rustBin = Split-Path $cargoExe
$normRustBin = $rustBin.TrimEnd('\')

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$already = $false
if ($userPath) {
    foreach ($segment in $userPath.Split(";")) {
        if ($segment.TrimEnd('\').Equals($normRustBin, [System.StringComparison]::OrdinalIgnoreCase)) {
            $already = $true
            break
        }
    }
}

if (-not $already) {
    $newUserPath = if ([string]::IsNullOrEmpty($userPath)) { $rustBin } else { "$rustBin;$userPath" }
    [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    Write-Host "Added to user PATH: $rustBin" -ForegroundColor Green
    $env:Path = (@($machinePath, [Environment]::GetEnvironmentVariable("Path", "User")) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join ";"
    Sync-RustUserEnvVars
}

Write-Host ""
if (Get-Command cargo -ErrorAction SilentlyContinue) {
    cargo --version
} else {
    Write-Host "cargo still not on PATH in this process; invoking directly:" -ForegroundColor Yellow
    & $cargoExe --version
}

Write-Host ""
$invokedViaNestedPwsh = $false
if ($MyInvocation.Line) {
    $invokedViaNestedPwsh = $MyInvocation.Line -match 'powershell(\.exe)?\s+-(File|f)\b'
}
if ($invokedViaNestedPwsh) {
    Write-Host "You ran this via: powershell -File ..." -ForegroundColor Yellow
    Write-Host "That only fixed a child process. In THIS prompt, run (same window):" -ForegroundColor Yellow
    Write-Host "  .\scripts\ensure_cargo_in_path.ps1" -ForegroundColor White
    Write-Host "Or rebuild PATH from the registry in this window:" -ForegroundColor Yellow
    $paste = '$env:Path = (@([Environment]::GetEnvironmentVariable("Path","Machine"), [Environment]::GetEnvironmentVariable("Path","User")) | Where-Object { $_ }) -join ";"'
    Write-Host "  $paste" -ForegroundColor White
}
