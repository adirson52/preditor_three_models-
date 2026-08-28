$ErrorActionPreference = 'Stop'
$dashboardDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    Write-Host 'Python nao foi encontrado. Instale o Python 3 para iniciar o servidor local.' -ForegroundColor Red
    Read-Host 'Pressione Enter para sair'
    exit 1
}
$port = 8767
$url = "http://127.0.0.1:$port/index.html"
Write-Host "Dashboard offline: $url" -ForegroundColor Green
Write-Host 'Mantenha esta janela aberta durante a navegacao.'
Start-Process $url
Set-Location -LiteralPath $dashboardDir
python -m http.server $port --bind 127.0.0.1
