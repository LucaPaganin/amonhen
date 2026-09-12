#Requires -Version 5.1
# Confronta la revisione registrata in .pandino\install.json con upstream main.
# Non modifica nessuno dei due file.
#   exit 0  il kit registrato è aggiornato
#   exit 1  è disponibile un aggiornamento
#   exit 2  revisione locale mancante o malformata, oppure upstream non leggibile
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$manifest = Join-Path $PSScriptRoot 'install.json'
$installed = $null
if (Test-Path -LiteralPath $manifest) {
    try { $installed = (Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json).revision } catch { }
}

$upstream = $null
try {
    $upstream = (Invoke-RestMethod -Uri 'https://api.github.com/repos/wtfzambo/pandino/git/ref/heads/main' -TimeoutSec 10).object.sha
} catch { }

function Test-Sha([string]$v) { $v -and $v.Length -eq 40 -and $v -match '^[0-9a-fA-F]{40}$' }

if (-not (Test-Sha $installed)) {
    Write-Host 'revisione installata sconosciuta o malformata'
    if (Test-Sha $upstream) { Write-Host "upstream main: $upstream" }
    exit 2
}
if (-not (Test-Sha $upstream)) {
    Write-Host "installato: $installed"
    Write-Host 'upstream main non leggibile'
    exit 2
}
if ($installed.ToLower() -eq $upstream.ToLower()) {
    Write-Host "aggiornato: $installed"
    exit 0
}
Write-Host "installato: $installed"
Write-Host "upstream:   $upstream"
Write-Host "confronto:  https://github.com/wtfzambo/pandino/compare/$installed...$upstream"
exit 1
