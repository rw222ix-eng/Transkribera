<#
Sparexporten: skriver spardata/spar.jsonl ur databasen och pushar den, sa att
sondagsrutinen i molnet (claude.ai/code/routines) har farsk data att lasa.

Exporten gar DAGLIGEN 05:00 lokal tid, inte bara sondagar. Fram till
2026-09-20 gick den sondagar 17:45, avstamd mot rutinens 18:00 UTC - men den
sondagen startades rutinen for hand pa formiddagen, laste en vecka gammal fil
och drog slutsatsen att appen statt oanvand. En daglig export ar aldrig mer an
ett dygn efter, oavsett nar rutinen far. Dagar utan ny anvandning ger ingen
commit (exporten ar deterministisk), sa det kostar inget.

Committar och pushar ENDAST spardata/spar.jsonl och spardata/exporterad.txt -
aldrig nagot annat som rakar ligga i arbetstradet. Misslyckas pushen (Macen har hunnit fore) provas
en rebase med autostash; gar inte det heller far nasta vecka ta det - en
missad export ar ett halls i statistiken, inte ett haveri.

Kor:
    powershell -NoProfile -File tools\spar_export.ps1
    powershell -NoProfile -File tools\spar_export.ps1 -InstalleraTask

OBS: UTF-8 MED BOM, ren ASCII i koden (samma skal som nattutforskaren:
schtasks startar PowerShell 5.1).
#>
[CmdletBinding()]
param(
    [string]$Repo = 'E:\Transkribera',
    [switch]$InstalleraTask
)

$ErrorActionPreference = 'Stop'
$TASKNAMN = 'TranskriberaSparexporten'

if ($InstalleraTask) {
    $skript = Join-Path $Repo 'tools\spar_export.ps1'
    $tr = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $skript + '"'
    schtasks /create /tn $TASKNAMN /tr $tr /sc DAILY /st 05:00 /f
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    schtasks /query /tn $TASKNAMN /fo LIST
    exit 0
}

function Nativ {
    param([string]$Fil, [string[]]$Argument)
    $tidigare = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Fil @Argument 2>&1 | ForEach-Object { Write-Host ("    " + $_) }
    } finally {
        $ErrorActionPreference = $tidigare
    }
    return $LASTEXITCODE
}

Push-Location $Repo
try {
    if ((Nativ 'python' @('-m', 'tools.spar_export')) -ne 0) {
        Write-Host 'AVBRYTER: exporten misslyckades.'
        exit 1
    }
    # Ingen andring, ingen commit: exporten ar deterministisk, sa en dag
    # utan anvandning ger exakt samma bytes (och ingen ny stampel). Preferensen sanks runt anropen -
    # PS 5.1 gor annars gits stderr till ett terminerande fel (se Nativ).
    $tidigare = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & git diff --quiet HEAD -- spardata/spar.jsonl 2>$null
    $andrad = ($LASTEXITCODE -ne 0)
    & git ls-files --error-unmatch spardata/spar.jsonl 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { $andrad = $true }   # forsta veckan: osparad fil
    $ErrorActionPreference = $tidigare
    if (-not $andrad) {
        Write-Host 'Ingen ny anvandning sedan sist - inget att pusha.'
        exit 0
    }
    Nativ 'git' @('add', 'spardata/spar.jsonl', 'spardata/exporterad.txt') | Out-Null
    $kod = Nativ 'git' @('commit', '-m', 'chore(spardata): dagens sparexport till sondagsrutinen', '--only', 'spardata/spar.jsonl', 'spardata/exporterad.txt')
    if ($kod -ne 0) { Write-Host 'AVBRYTER: commit misslyckades.'; exit 1 }
    if ((Nativ 'git' @('push')) -ne 0) {
        Write-Host 'Push avvisad - provar rebase.'
        if ((Nativ 'git' @('pull', '--rebase', '--autostash')) -eq 0) {
            if ((Nativ 'git' @('push')) -ne 0) { exit 1 }
        } else {
            exit 1
        }
    }
    Write-Host 'Sparexporten pushad.'
} finally {
    Pop-Location
}
