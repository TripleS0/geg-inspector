param(
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [switch]$SkipTauri
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

. (Join-Path $PSScriptRoot "rust_path_helpers.ps1")

# 刷新当前会话的 Path（安装 rustup 后未重启终端时仍可找到 cargo）
$env:Path = @(
    [Environment]::GetEnvironmentVariable("Path", "Machine"),
    [Environment]::GetEnvironmentVariable("Path", "User"),
    $env:Path
) -join ";"

Sync-RustUserEnvVars

Write-Host "[1/3] Building frontend..." -ForegroundColor Cyan
if (-not $SkipFrontend) {
    npm --prefix (Join-Path $Root "frontend") install
    npm --prefix (Join-Path $Root "frontend") run build
} else {
    Write-Host "Skipped frontend build."
}

Write-Host "[2/3] Building backend.exe..." -ForegroundColor Cyan
if (-not $SkipBackend) {
    python (Join-Path $Root "scripts\build_backend.py")
} else {
    Write-Host "Skipped backend build."
}

Write-Host "[3/3] Building Tauri installer..." -ForegroundColor Cyan
if ($SkipTauri) {
    Write-Host "Skipped Tauri build." -ForegroundColor Yellow
    Write-Host "Done. frontend/dist and backend-dist/backend.exe are ready." -ForegroundColor Green
    Write-Host "Install Rust + tauri-cli, then re-run without -SkipTauri to build the installer." -ForegroundColor Green
    exit 0
}

$CargoExe = Get-CargoExePath
if (-not $CargoExe) {
    Write-Host ""
    Write-Host "ERROR: cargo not found. Install Rust (rustup) and tauri-cli, then retry." -ForegroundColor Red
    Write-Host "Steps:" -ForegroundColor Yellow
    Write-Host "  1. Install Rust from https://rustup.rs/ (Windows x64 default toolchain)." -ForegroundColor White
    Write-Host '  2. In a new terminal: cargo install tauri-cli --version "^1.6"' -ForegroundColor White
    Write-Host "  3. Re-run: powershell -File scripts/build_desktop.ps1" -ForegroundColor White
    Write-Host ""
    Write-Host "To build only frontend + backend (skip installer):" -ForegroundColor Yellow
    Write-Host "  powershell -File scripts/build_desktop.ps1 -SkipTauri" -ForegroundColor White
    Write-Host ""
    Write-Host "If Rust is installed but cargo fails in this terminal, run (same window, no nested powershell):" -ForegroundColor Yellow
    Write-Host "  .\scripts\ensure_cargo_in_path.ps1" -ForegroundColor White
    Write-Host "If C: is full, move Rust + TEMP to D: (once), then restart Cursor:" -ForegroundColor Yellow
    Write-Host "  .\scripts\setup_rust_on_d.ps1 -CopyFromDefaultProfile -SetUserTemp" -ForegroundColor White
    exit 1
}

Write-Host ('Using cargo: ' + $CargoExe) -ForegroundColor DarkGray
$TauriDir = Join-Path $Root 'src-tauri'
Push-Location $TauriDir
try {
    # Tauri CLI 2.x does not accept --manifest-path; building from src-tauri matches Tauri 1.x workflows.
    & $CargoExe tauri build
    if ($LASTEXITCODE -ne 0) {
        throw "cargo tauri build failed (exit $LASTEXITCODE). If you use Tauri 2 CLI with a Tauri 1 app, run: cargo install tauri-cli --version 1.6.6 --force"
    }
} finally {
    Pop-Location
}

Write-Host "Done. Installers are under src-tauri/target/release/bundle." -ForegroundColor Green
