<#
Nattutforskaren: en Claude med Playwright som klickar sonder appen medan
lararen sover.

OBS OM TECKNEN I FILEN: skriptet kors av Windows PowerShell 5.1 (schtasks
startar powershell.exe), och 5.1 laser en .ps1 utan BOM som ANSI. Filen maste
darfor sparas som UTF-8 MED BOM, annars blir a-ring och a-umlaut fel. Just den
har filen halls dessutom pa ren ASCII i koden for sakerhets skull.

Sviterna prover det NAGON har tankt pa. Fuzzningen (tests/test_api_fuzz.py)
prover API-ytan. Kvar finns det ingen av dem nar: en manniska som har brattom,
dubbelklickar, byter vy mitt i en laddning och trycker bakat. Skriptet slapper
loss en sadan mot en sandladeserver varje natt och lamnar en rapport med
reprosteg plus ett Playwright-specutkast per bekraftat fynd, alltsa nagot som
gar att lagga in i e2e/ pa morgonen, inte bara en text att lasa.

Tre granser som INTE far suddas ut:

* Egen klon. Korningen sker i %LOCALAPPDATA%\transkribera-natt, aldrig i
  E:\Transkribera. Nattens agent ska inte kunna rora ett arbetstrad som
  lararen (eller en annan session) star mitt i.
* Egen sandlada. Servern startas av e2e/testserver.py: tom bas under temp,
  fejkad claude (FEJK_CLAUDE=auto), ingen ElevenLabs-nyckel. Ingen riktig
  transkribering, ingen betald generering.
* Rapporten hamnar UTANFOR repot, under
  ~\.claude\projects\E--Transkribera\nattutforskaren\AAAA-MM-DD\. Skriptet
  committar aldrig nagot; en nattlig commit ar precis vad ingen vill vakna till.

Kor:
    powershell -NoProfile -File tools\nattutforskaren.ps1
    powershell -NoProfile -File tools\nattutforskaren.ps1 -TidsbudgetMinuter 5
    powershell -NoProfile -File tools\nattutforskaren.ps1 -InstalleraTask

-InstalleraTask registrerar den schemalagda uppgiften
"TranskriberaNattutforskaren" kl. 03:00 varje natt pa ANVANDARNIVA (ingen
forhojning, ingen /RU SYSTEM: den kor nar lararen ar inloggad, vilket hennes
maskin ar. En task som kraver admin hade behovt ett losenord i klartext).
#>
[CmdletBinding()]
param(
    # Hur lange utforskaren far halla pa. Gar in i BADE prompten (sa agenten
    # sjalv kan prioritera) och i en hard timeout (sa en agent som fastnar inte
    # kor till frukost).
    [int]$TidsbudgetMinuter = 45,
    # Inte 8751 (e2e) och inte 8752 (soaken): nattkorningen ska kunna ligga
    # parallellt med en glomd svit utan att de tar varandras port eller bas.
    # ValidateRange for att en provkorning pa port 1 gick igenom halsokollen
    # (uvicorn band porten, HTTP-klienten fick 200) men var oanvandbar for
    # agenten: Chrome vagrar lag-portar med net::ERR_UNSAFE_PORT, sa natten
    # brann utan att loggen sa varfor.
    [ValidateRange(1024, 65535)]
    [int]$Port = 8753,
    [string]$Kalla = 'E:\Transkribera',
    [string]$Klon = (Join-Path $env:LOCALAPPDATA 'transkribera-natt'),
    [string]$Rapportrot = (Join-Path $env:USERPROFILE '.claude\projects\E--Transkribera\nattutforskaren'),
    # Tak for nattens API-kostnad. En utforskare som rakar loopa ska kosta en
    # kaffe, inte en manadslon.
    [double]$BudgetUSD = 5.0,
    [switch]$InstalleraTask
)

$ErrorActionPreference = 'Stop'
$TASKNAMN = 'TranskriberaNattutforskaren'

# -- Schemalaggning ---------------------------------------------------------
# Gors fore allt annat och avslutar: -InstalleraTask kor ingen utforskning.
if ($InstalleraTask) {
    # Sokvagen som tasken pekar pa ar LARARENS repo, inte den har filens plats:
    # skriptet kan ligga i en tillfallig worktree nar det installeras, och den
    # katalogen finns inte kl. 03:00.
    $skript = Join-Path $Kalla 'tools\nattutforskaren.ps1'
    $tr = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $skript + '"'
    schtasks /create /tn $TASKNAMN /tr $tr /sc DAILY /st 03:00 /f
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    schtasks /query /tn $TASKNAMN /fo LIST
    exit 0
}

# -- Katalogerna ------------------------------------------------------------
$dag = Get-Date -Format 'yyyy-MM-dd'
$rapport = Join-Path $Rapportrot $dag
New-Item -ItemType Directory -Force -Path $rapport | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $rapport 'specutkast') | Out-Null
$logg = Join-Path $rapport 'korning.log'

function Logga($text) {
    $rad = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $text
    Write-Host $rad
    Add-Content -Path $logg -Value $rad -Encoding utf8
}

function Nativ {
    # Kor ett vanligt program och logga allt det sager. Ma finnas: med
    # $ErrorActionPreference = 'Stop' gor Windows PowerShell 5.1 varje rad ett
    # program skriver till stderr till ett TERMINERANDE fel, aven nar
    # programmet lyckades. "Cloning into ..." skriver git till stderr, sa
    # `git clone` avslutade hela skriptet trots slutkod 0. Har sanks
    # preferensen runt anropet i stallet, och slutkoden far avgora.
    param([string]$Fil, [string[]]$Argument)
    $tidigare = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Fil @Argument 2>&1 | ForEach-Object { Logga ("    " + $_) }
    } finally {
        $ErrorActionPreference = $tidigare
    }
    return $LASTEXITCODE
}

Logga "Nattutforskaren startar. Rapport: $rapport"

# -- Klonen -----------------------------------------------------------------
# Farsk kod utan att rora arbetstradet. reset --hard i stallet for pull:
# klonen ar ett engangstrad och en halvfardig merge kl. 03:00 stoppar natten.
$farsk = -not (Test-Path (Join-Path $Klon '.git'))
if (-not $farsk) {
    # Pekar klonen nagon annanstans an $Kalla ar den fran en tidigare uppsattning
    # (en worktree som stadats bort, ett repo som flyttats). Da ar den vardelos,
    # och utan den har kontrollen faller varje natt pa "fetch: repository not
    # found" tills nagon raderar katalogen for hand.
    $origin = (& git -C $Klon remote get-url origin 2>$null | Out-String).Trim()
    if ($origin -ne $Kalla) {
        Logga "Klonens origin ar '$origin', inte '$Kalla'. Gor om den."
        Remove-Item -Recurse -Force $Klon -ErrorAction SilentlyContinue
        $farsk = $true
    }
}
if ($farsk) {
    Logga "Klonar $Kalla till $Klon"
    $kod = Nativ 'git' @('clone', '--no-hardlinks', $Kalla, $Klon)
} else {
    Logga "Uppdaterar klonen"
    $kod = Nativ 'git' @('-C', $Klon, 'fetch', 'origin')
    if ($kod -eq 0) { $kod = Nativ 'git' @('-C', $Klon, 'reset', '--hard', 'origin/HEAD') }
}
if ($kod -ne 0) {
    Logga "AVBRYTER: git gav slutkod $kod"
    exit 1
}
if (-not (Test-Path (Join-Path $Klon 'e2e\testserver.py'))) {
    Logga "AVBRYTER: klonen saknar e2e\testserver.py"
    exit 1
}
Nativ 'git' @('-C', $Klon, 'log', '--oneline', '-1') | Out-Null

# -- Playwright-MCP:n -------------------------------------------------------
# Claude CLI:t har ingen Playwright-MCP konfigurerad fran borjan, och lararens
# egna moln-MCP:er (Gmail, Drive, Kalender) ska nattens agent absolut inte
# arva. Darfor en egen .mcp.json i klonen som kors med --strict-mcp-config:
# exakt en server, exakt en webblasare.
$mcpfil = Join-Path $Klon '.mcp.json'
$mcp = @{
    mcpServers = @{
        playwright = @{
            command = 'npx'
            # --isolated: ingen profil sparas mellan natter. --browser chrome:
            # samma val som e2e/playwright.config.ts (Playwrights egen chromium
            # laddas aldrig ner pa den har maskinen). --headless: kl. 03:00 ska
            # inget fonster hoppa upp over lararens skrivbord.
            args    = @('-y', '@playwright/mcp@latest', '--isolated', '--headless',
                        '--browser', 'chrome')
        }
    }
}
$mcp | ConvertTo-Json -Depth 5 | Out-File -FilePath $mcpfil -Encoding utf8
Logga "Skrev MCP-konfig: $mcpfil"

# Paketet hamtas av npx vid forsta korningen. Gors det inne i agentens uppstart
# ser felet ut som "MCP-servern svarade inte"; har ser det ut som vad det ar.
Logga "Kontrollerar @playwright/mcp"
if ((Nativ 'npx' @('-y', '@playwright/mcp@latest', '--version')) -ne 0) {
    Logga "VARNING: @playwright/mcp gick inte att hamta. Agenten blir blind."
}

# -- Sandladeservern --------------------------------------------------------
$env:FEJK_CLAUDE = 'auto'
# Nyckeln far inte ens finnas i miljon servern arver: en utforskare som klickar
# "Transkribera" ska fa "lagg in nyckeln", inte skicka ljud for riktiga pengar.
if (Test-Path Env:ELEVENLABS_API_KEY) { Remove-Item Env:ELEVENLABS_API_KEY }
$serverut = Join-Path $rapport 'server.log'
$servererr = Join-Path $rapport 'server-fel.log'
Logga "Startar sandladeservern pa port $Port"
$server = Start-Process -FilePath 'python' `
    -ArgumentList @((Join-Path $Klon 'e2e\testserver.py'), "$Port") `
    -WorkingDirectory $Klon -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $serverut -RedirectStandardError $servererr
# Pid:t sparas pa disk: dor skriptet mellan raderna ska nasta natt (eller en
# manniska) kunna stanga just DEN processen, inte varje python pa maskinen.
$pidfil = Join-Path $rapport 'server.pid'
Set-Content -Path $pidfil -Value $server.Id -Encoding ascii
Logga "Serverns pid: $($server.Id)"

$url = "http://localhost:$Port"
$uppe = $false
foreach ($i in 1..60) {
    try {
        $svar = Invoke-WebRequest -Uri "$url/api/var-kors" -UseBasicParsing -TimeoutSec 3
        if ($svar.StatusCode -eq 200) { $uppe = $true; break }
    } catch {
        Start-Sleep -Seconds 1
    }
}

$slutkod = 0
try {
    if (-not $uppe) {
        Logga "AVBRYTER: servern svarade inte inom 60 s. Se server-fel.log."
        $slutkod = 1
    } else {
        Logga "Servern svarar. Slapper los utforskaren ($TidsbudgetMinuter min)."

        # -- Prompten -------------------------------------------------------
        $promptmall = Join-Path $Klon 'tools\nattutforskaren-prompt.txt'
        if (-not (Test-Path $promptmall)) {
            # Klonen kan sta pa en main som annu inte har prompten (grenen ar
            # inte mergad). Fall tillbaka pa filen bredvid det har skriptet.
            $promptmall = Join-Path $PSScriptRoot 'nattutforskaren-prompt.txt'
        }
        # En Replace per rad, inte en kedja: PowerShell 5.1 tillater inte
        # medlemsanrop som fortsatter pa nasta rad efter en avslutande punkt.
        $prompt = Get-Content -Path $promptmall -Raw -Encoding UTF8
        $prompt = $prompt.Replace('{{URL}}', $url)
        $prompt = $prompt.Replace('{{TIDSBUDGET}}', "$TidsbudgetMinuter")
        $prompt = $prompt.Replace('{{KLON}}', $Klon)
        $promptfil = Join-Path $rapport 'prompt.txt'
        # -Encoding utf8 explicit: Set-Content skriver annars ANSI, och da nar
        # prompten agenten med fragetecken dar a-ring och a-umlaut ska sta.
        Set-Content -Path $promptfil -Value $prompt -Encoding utf8

        # -- Agenten --------------------------------------------------------
        # Arbetskatalogen AR rapportkatalogen: allt agenten skriver hamnar dar
        # av sig sjalvt, och en felskrivning kan inte landa i repot.
        # --strict-mcp-config: bara Playwright, inga av lararens moln-MCP:er.
        # --tools utan Bash: en obevakad natt ska inte kunna kora skalkommandon.
        # bypassPermissions: ingen manniska kan svara pa en behorighetsfraga
        # kl. 03:00, sa gransen dras av verktygslistan i stallet.
        $claude = Join-Path $env:APPDATA 'npm\claude.cmd'
        if (-not (Test-Path $claude)) { $claude = 'claude' }
        $agentut = Join-Path $rapport 'agent.log'
        $agenterr = Join-Path $rapport 'agent-fel.log'
        $arg = @(
            '-p',
            '--output-format', 'text',
            '--mcp-config', ('"' + $mcpfil + '"'),
            '--strict-mcp-config',
            '--permission-mode', 'bypassPermissions',
            '--tools', 'Read,Write,Edit,Glob,Grep,TodoWrite',
            '--add-dir', ('"' + $Klon + '"'),
            '--max-budget-usd', "$BudgetUSD"
        )
        $agent = Start-Process -FilePath $claude -ArgumentList $arg `
            -WorkingDirectory $rapport -PassThru -WindowStyle Hidden `
            -RedirectStandardInput $promptfil `
            -RedirectStandardOutput $agentut -RedirectStandardError $agenterr
        # Handtaget MASTE lasas direkt, annars ar $agent.ExitCode $null efter att
        # processen dott och loggraden nedan blir tom. Att rora .Handle far
        # .NET att cacha handtaget sa slutkoden gar att lasa i efterhand.
        $null = $agent.Handle
        Set-Content -Path (Join-Path $rapport 'agent.pid') -Value $agent.Id -Encoding ascii

        # Hard grans = budgeten plus fem minuters marginal for uppstart och for
        # den sista skrivningen. Prompten sager samma tid, men en agent som
        # fastnar i en laddning laser inte klockan.
        $tak = ($TidsbudgetMinuter * 60) + 300
        Wait-Process -Id $agent.Id -Timeout $tak -ErrorAction SilentlyContinue
        if (-not $agent.HasExited) {
            Logga "Utforskaren nadde tidstaket ($tak s). Stoppar den."
            Stop-Process -Id $agent.Id -Force -ErrorAction SilentlyContinue
            $slutkod = 2
        } else {
            # WaitForExit() innan ExitCode lases: utan den ar koden $null pa ett
            # objekt fran Start-Process -PassThru, och loggraden blev tom.
            $agent.WaitForExit()
            $kod = $agent.ExitCode
            Logga "Utforskaren klar, slutkod $kod"
            if ($kod -ne 0) { $slutkod = $kod }
        }
    }
} finally {
    # Stang via det sparade pid:t. Aldrig Stop-Process -Name python: lararen
    # kan ha appen igang, och den ska inte do for att natten ar slut.
    if ($server -and -not $server.HasExited) {
        Logga "Stoppar sandladeservern (pid $($server.Id))"
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
        Wait-Process -Id $server.Id -Timeout 20 -ErrorAction SilentlyContinue
    }
    if (Test-Path $pidfil) { Remove-Item $pidfil -Force -ErrorAction SilentlyContinue }
}

$fynd = @(Get-ChildItem -Path (Join-Path $rapport 'specutkast') -Filter '*.spec.mjs' -ErrorAction SilentlyContinue)
$filer = (Get-ChildItem $rapport | Select-Object -ExpandProperty Name) -join ', '
Logga ("Klart. Filer i rapporten: " + $filer)
Logga ("Specutkast: " + $fynd.Count)
exit $slutkod
