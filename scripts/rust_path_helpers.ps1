function Sync-RustUserEnvVars {
    foreach ($k in @("CARGO_HOME", "RUSTUP_HOME")) {
        $v = [Environment]::GetEnvironmentVariable($k, "User")
        if ($v) { Set-Item -Path "env:$k" -Value $v }
    }
}

function Get-CargoExePath {
    $cmd = Get-Command cargo -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        return $cmd.Source
    }

    $cargoHome = $env:CARGO_HOME
    if (-not $cargoHome) {
        $cargoHome = [Environment]::GetEnvironmentVariable("CARGO_HOME", "User")
    }
    if ($cargoHome) {
        $p = Join-Path $cargoHome "bin\cargo.exe"
        if (Test-Path -LiteralPath $p) {
            return (Resolve-Path -LiteralPath $p).Path
        }
    }

    $p = Join-Path $env:USERPROFILE ".cargo\bin\cargo.exe"
    if (Test-Path -LiteralPath $p) {
        return (Resolve-Path -LiteralPath $p).Path
    }
    return $null
}
