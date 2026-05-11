# Put Rust toolchains, Cargo home, and (optionally) TEMP on D: to free C:.
# Run once from an elevated or normal PowerShell (User env vars; admin not required):
#   Set-ExecutionPolicy -Scope Process Bypass -Force
#   .\scripts\setup_rust_on_d.ps1
#
# Optional: copy existing %USERPROFILE%\.cargo and .rustup after closing rust/cargo processes:
#   .\scripts\setup_rust_on_d.ps1 -CopyFromDefaultProfile -SetUserTemp
#
# Default base folder: D:\GDNY_tuomi\rust-on-d   (override with -BaseDir)

param(
    [string]$BaseDir = "",
    [switch]$CopyFromDefaultProfile,
    [switch]$SetUserTemp
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($BaseDir)) {
    $BaseDir = "D:\GDNY_tuomi\rust-on-d"
}

$BaseDir = $BaseDir.TrimEnd('\', '/')
$cargoHome = Join-Path $BaseDir "cargo"
$rustupHome = Join-Path $BaseDir "rustup"
$tempDir = Join-Path $BaseDir "temp"
$cargoBin = Join-Path $cargoHome "bin"

New-Item -ItemType Directory -Force -Path $cargoHome, $rustupHome, $tempDir | Out-Null

if ($CopyFromDefaultProfile) {
    $srcCargo = Join-Path $env:USERPROFILE ".cargo"
    $srcRustup = Join-Path $env:USERPROFILE ".rustup"
    $robocopy = Join-Path $env:SystemRoot "System32\robocopy.exe"
    if (-not (Test-Path -LiteralPath $robocopy)) {
        throw "robocopy.exe not found at $robocopy"
    }

    if ((Test-Path -LiteralPath $srcCargo) -and -not (Test-Path -LiteralPath (Join-Path $cargoBin "cargo.exe"))) {
        Write-Host "Copying $srcCargo -> $cargoHome (robocopy)..." -ForegroundColor Cyan
        & $robocopy $srcCargo $cargoHome /E /COPY:DAT /R:2 /W:2 | Out-Null
        if ($LASTEXITCODE -ge 8) {
            throw "robocopy exited with code $LASTEXITCODE (>=8 means failure)"
        }
    }

    if ((Test-Path -LiteralPath $srcRustup) -and -not (Test-Path -LiteralPath (Join-Path $rustupHome "toolchains"))) {
        Write-Host "Copying $srcRustup -> $rustupHome (robocopy)..." -ForegroundColor Cyan
        & $robocopy $srcRustup $rustupHome /E /COPY:DAT /R:2 /W:2 | Out-Null
        if ($LASTEXITCODE -ge 8) {
            throw "robocopy exited with code $LASTEXITCODE (>=8 means failure)"
        }
    }
}

[Environment]::SetEnvironmentVariable("CARGO_HOME", $cargoHome, "User")
[Environment]::SetEnvironmentVariable("RUSTUP_HOME", $rustupHome, "User")

if ($SetUserTemp) {
    [Environment]::SetEnvironmentVariable("TEMP", $tempDir, "User")
    [Environment]::SetEnvironmentVariable("TMP", $tempDir, "User")
}

$normCargoBin = $cargoBin.TrimEnd('\')
$normOld = (Join-Path $env:USERPROFILE ".cargo\bin").TrimEnd('\')
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$parts = @()
if ($userPath) {
    $parts = $userPath.Split(";")
}
$kept = New-Object System.Collections.Generic.List[string]
foreach ($p in $parts) {
    if ([string]::IsNullOrWhiteSpace($p)) {
        continue
    }
    $n = $p.TrimEnd('\')
    if ($n.Equals($normOld, [System.StringComparison]::OrdinalIgnoreCase)) {
        continue
    }
    if ($n.Equals($normCargoBin, [System.StringComparison]::OrdinalIgnoreCase)) {
        continue
    }
    [void]$kept.Add($p)
}
$newUserPath = if ($kept.Count -gt 0) {
    "$cargoBin;" + ($kept -join ";")
} else {
    $cargoBin
}
[Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")

Write-Host ""
Write-Host "User environment updated:" -ForegroundColor Green
Write-Host "  CARGO_HOME=$cargoHome"
Write-Host "  RUSTUP_HOME=$rustupHome"
if ($SetUserTemp) {
    Write-Host "  TEMP/TMP=$tempDir"
}
Write-Host "  User PATH prepended with: $cargoBin"
Write-Host ""
Write-Host "Next: fully quit Cursor and all terminals, open a new window, then:" -ForegroundColor Yellow
Write-Host "  cargo --version" -ForegroundColor White
if (-not $CopyFromDefaultProfile) {
    $oldCargoExe = Join-Path $env:USERPROFILE ".cargo\bin\cargo.exe"
    if (Test-Path -LiteralPath $oldCargoExe) {
        Write-Host ""
        Write-Host "WARN: Rust is still on C: under your profile. New sessions will use empty D: dirs until you copy data." -ForegroundColor Yellow
        Write-Host "Re-run with -CopyFromDefaultProfile (close all cargo/rustup first), or copy .cargo + .rustup manually." -ForegroundColor Yellow
    }
} else {
    Write-Host "Copied existing profile directories when possible; you may delete the old C: folders after verifying cargo." -ForegroundColor DarkYellow
}
Write-Host ""
Write-Host "If tauri-cli is missing in the new CARGO_HOME, run:" -ForegroundColor Yellow
Write-Host '  cargo install tauri-cli --version "^1.6"' -ForegroundColor White
