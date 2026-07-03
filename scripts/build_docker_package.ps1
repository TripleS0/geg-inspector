#Requires -Version 5.1
# Build a zip package for end-user Docker deployment.
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutDir = Join-Path $Root "dist"
$ZipName = "geg-inspector-docker.zip"
$Staging = Join-Path $OutDir "geg-inspector-docker"

if (Test-Path $Staging) { Remove-Item -Recurse -Force $Staging }
New-Item -ItemType Directory -Force -Path $Staging, $OutDir | Out-Null

$Items = @(
    "README-DOCKER.md",
    "docker-compose.yml",
    "docker-compose.mirror.cn.yml",
    "start.bat", "stop.bat", "start-mirror.bat", "rebuild.bat", "rebuild-mirror.bat",
    "start.sh", "stop.sh", "start-mirror.sh",
    "requirements.txt",
    ".dockerignore",
    "backend",
    "frontend",
    "mock-data"
)

foreach ($item in $Items) {
    $src = Join-Path $Root $item
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination (Join-Path $Staging $item) -Recurse -Force
    }
}

$strip = @(
    (Join-Path $Staging "frontend\node_modules"),
    (Join-Path $Staging "frontend\dist"),
    (Join-Path $Staging "backend\tests")
)
foreach ($path in $strip) {
    if (Test-Path $path) { Remove-Item -Recurse -Force $path }
}

New-Item -ItemType Directory -Force -Path (Join-Path $Staging "data") | Out-Null

foreach ($bat in @("start.bat", "stop.bat", "start-mirror.bat", "rebuild.bat", "rebuild-mirror.bat")) {
    $path = Join-Path $Staging $bat
    if (Test-Path $path) {
        $text = [IO.File]::ReadAllText($path)
        $text = $text -replace "`r`n", "`n" -replace "`n", "`r`n"
        [IO.File]::WriteAllText($path, $text, [Text.UTF8Encoding]::new($false))
    }
}

$ZipPath = Join-Path $OutDir $ZipName
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path $Staging -DestinationPath $ZipPath -Force

Write-Host "交付包已生成: $ZipPath"
Write-Host "用户解压后双击 start-mirror.bat（国内）或 start.bat 即可启动。"
