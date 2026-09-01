<#
Sparanalysen: en Opus-agent laser veckans anvandarspar och foreslar
forbattringar medan lararen sover.

Syskon till nattutforskaren (tools/nattutforskaren.ps1), men med OMVANT
forhallande till lararens data: nattutforskaren far ALDRIG rora den riktiga
databasen och kor darfor i sandlada - den har rutinen finns just FOR att lasa
den riktiga databasen (spar-tabellen, migration v28: vad lararen gjorde, vad
hon bad canvaschatten om, vad varven andrade). Darfor ar det tva skript och
tva schemalagda uppgifter, inte ett: att baka in en riktig-data-lasning i
nattutforskaren hade suddat ut dess viktigaste grans.

Kedjan: python -m tools.spar skriver veckans rapport till en arbetskatalog
utanfor repot, och claude CLI (Opus 5, i molnet) far lasa den plus koden och
skriva forslag.md. Ingenting committas, ingenting i repot rors: agenten har
bara Read/Glob/Grep pa repot (via --add-dir) och skriver i arbetskatalogen.

Rapporterna hamnar i ~\.claude\projects\E--Transkribera\sparanalysen\AAAA-MM-DD\
dar en vanlig session (och lararen) hittar dem pa morgonen.

Kor:
    powershell -NoProfile -File tools\sparanalysen.ps1
    powershell -NoProfile -File tools\sparanalysen.ps1 -InstalleraTask

-InstalleraTask registrerar "TranskriberaSparanalysen" mandagar 04:30 pa
ANVANDARNIVA - efter nattutforskaren (03:00 + max ~50 min), sa de aldrig kor
samtidigt mot samma claude-budget.

OBS: sparas som UTF-8 MED BOM och hall koden ren ASCII - samma skal som i
nattutforskaren (schtasks startar PowerShell 5.1 som laser BOM-los .ps1 som
ANSI).
#>
[CmdletBinding()]
param(
    [int]$Dagar = 7,
    [string]$Repo = 'E:\Transkribera',
    [string]$Rapportrot = (Join-Path $env:USERPROFILE '.claude\projects\E--Transkribera\sparanalysen'),
    # Analysen ar en lasning och en skrivning - langt billigare an en natts
    # utforskning. Taket ar en spargris, inte en budget.
    [double]$BudgetUSD = 3.0,
    # Bytbar for provkorning: en fejkad claude.cmd verifierar hela kedjan
    # (spar-export, prompt, arbetskatalog, slutkoder) utan att kosta ett
    # API-anrop. Tom strang = den riktiga.
    [string]$ClaudeBin = '',
    [switch]$InstalleraTask
)

$ErrorActionPreference = 'Stop'
$TASKNAMN = 'TranskriberaSparanalysen'

if ($InstalleraTask) {
    $skript = Join-Path $Repo 'tools\sparanalysen.ps1'
    $tr = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $skript + '"'
    schtasks /create /tn $TASKNAMN /tr $tr /sc WEEKLY /d MON /st 04:30 /f
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    schtasks /query /tn $TASKNAMN /fo LIST
    exit 0
}

$dag = Get-Date -Format 'yyyy-MM-dd'
$rapport = Join-Path $Rapportrot $dag
New-Item -ItemType Directory -Force -Path $rapport | Out-Null
$logg = Join-Path $rapport 'korning.log'

function Logga($text) {
    $rad = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $text
    Write-Host $rad
    Add-Content -Path $logg -Value $rad -Encoding utf8
}

Logga "Sparanalysen startar. Rapport: $rapport"

# -- Veckans spar -----------------------------------------------------------
# tools/spar.py laser den riktiga databasen (read-only i praktiken: v28 ar
# redan pa plats, sa connect() migrerar ingenting). Skrivs till fil i
# arbetskatalogen sa agenten kan LASA den i stallet for att fa den i prompten
# - rapporten kan vara lang, och en fil gar att citera ur med radnummer.
$sparfil = Join-Path $rapport 'spar-rapport.txt'
$tidigare = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
# cwd = repot: `-m tools.spar` slas upp fran katalogen skriptet kors i, och
# schtasks startar i System32.
Push-Location $Repo
& python -m tools.spar --dagar $Dagar 2>&1 |
    Out-File -FilePath $sparfil -Encoding utf8
$sparkod = $LASTEXITCODE
Pop-Location
$ErrorActionPreference = $tidigare
if ($sparkod -ne 0) {
    Logga "AVBRYTER: tools.spar gav slutkod $sparkod. Se spar-rapport.txt."
    exit 1
}
$radantal = (Get-Content $sparfil | Measure-Object -Line).Lines
Logga "Sparrapporten skriven ($radantal rader)."

# Tomma veckor kostar inga pengar: utan onskemal och utan mutationer finns
# inget att analysera, och en agent som far en tom rapport skriver en sida
# artigheter om den.
$innehall = Get-Content $sparfil -Raw -Encoding UTF8
if ($innehall -match '0 rader') {
    Logga "Veckan var tom - ingen analys behovs. Klart."
    Set-Content -Path (Join-Path $rapport 'forslag.md') `
        -Value "Inga spar den har veckan - appen anvandes inte." -Encoding utf8
    exit 0
}

# -- Prompten ---------------------------------------------------------------
$promptmall = Join-Path $Repo 'tools\sparanalysen-prompt.txt'
if (-not (Test-Path $promptmall)) {
    $promptmall = Join-Path $PSScriptRoot 'sparanalysen-prompt.txt'
}
$prompt = Get-Content -Path $promptmall -Raw -Encoding UTF8
$prompt = $prompt.Replace('{{SPARFIL}}', $sparfil)
$prompt = $prompt.Replace('{{REPO}}', $Repo)
$prompt = $prompt.Replace('{{DAGAR}}', "$Dagar")
$promptfil = Join-Path $rapport 'prompt.txt'
Set-Content -Path $promptfil -Value $prompt -Encoding utf8

# -- Agenten ----------------------------------------------------------------
# --model claude-opus-5: lararens uttryckliga val for just den har rutinen -
# forslagen ar produkten, och de ska komma fran den starkaste modellen.
# Verktygen ar lasande plus Write: arbetskatalogen ar cwd, sa forslag.md
# hamnar ratt av sig sjalv, och repot nas bara via --add-dir for LASNING
# (agenten far inga skal och ingen Edit - den kan citera kod, inte andra den).
$claude = $ClaudeBin
if (-not $claude) {
    $claude = Join-Path $env:APPDATA 'npm\claude.cmd'
    if (-not (Test-Path $claude)) { $claude = 'claude' }
}
$agentut = Join-Path $rapport 'agent.log'
$agenterr = Join-Path $rapport 'agent-fel.log'
$arg = @(
    '-p',
    '--output-format', 'text',
    '--model', 'claude-opus-5',
    '--strict-mcp-config',
    '--permission-mode', 'bypassPermissions',
    '--tools', 'Read,Write,Glob,Grep,TodoWrite',
    '--add-dir', ('"' + $Repo + '"'),
    '--max-budget-usd', "$BudgetUSD"
)
$agent = Start-Process -FilePath $claude -ArgumentList $arg `
    -WorkingDirectory $rapport -PassThru -WindowStyle Hidden `
    -RedirectStandardInput $promptfil `
    -RedirectStandardOutput $agentut -RedirectStandardError $agenterr
$null = $agent.Handle
# 20 minuter racker for att lasa en rapport och skriva en: en agent som
# haller pa langre har fastnat, inte tankt djupare.
Wait-Process -Id $agent.Id -Timeout 1200 -ErrorAction SilentlyContinue
$slutkod = 0
if (-not $agent.HasExited) {
    Logga "Agenten nadde tidstaket. Stoppar den."
    Stop-Process -Id $agent.Id -Force -ErrorAction SilentlyContinue
    $slutkod = 2
} else {
    $agent.WaitForExit()
    Logga "Agenten klar, slutkod $($agent.ExitCode)"
    if ($agent.ExitCode -ne 0) { $slutkod = $agent.ExitCode }
}

if (Test-Path (Join-Path $rapport 'forslag.md')) {
    Logga "forslag.md ligger klar."
} else {
    Logga "VARNING: agenten lamnade ingen forslag.md. Se agent.log."
    if ($slutkod -eq 0) { $slutkod = 3 }
}
exit $slutkod
