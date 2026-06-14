@echo off
chcp 65001 >nul

REM Lagg till Deno i PATH (kravs for yt-dlp signaturlosning)
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\DenoLand.Deno_*") do set "PATH=%%D;%PATH%"

echo === Testa YouTube Premium-cookies ===
echo.

if not exist "%~dp0cookies.txt" (
    echo FEL: cookies.txt hittades inte!
    echo Forvantad plats: %~dp0cookies.txt
    echo.
    echo === INSTRUKTIONER FOR COOKIE-EXPORT ===
    echo.
    echo 1. Oppna Chrome i inkognitolage (Ctrl+Shift+N)
    echo 2. Logga in pa youtube.com med ditt Premium-konto
    echo 3. I samma flik, ga till: https://www.youtube.com/robots.txt
    echo 4. Installera tillagget "Get cookies.txt LOCALLY" (Chrome Web Store)
    echo 5. Klicka pa tillagget och exportera cookies for youtube.com
    echo 6. Spara filen som: %~dp0cookies.txt
    echo 7. STANG inkognitofonstret direkt efter export!
    echo.
    echo Klar? Kor detta skript igen for att testa.
    echo.
    pause
    exit /b 1
)

echo cookies.txt hittad! Testar mot YouTube...
echo.

echo [1/2] Testar inloggning...
yt-dlp --cookies "%~dp0cookies.txt" --skip-download --print "%%(uploader)s" "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>&1
if errorlevel 1 (
    echo.
    echo FEL: Cookies verkar inte fungera. Fornya dem enligt instruktionerna ovan.
    echo.
    pause
    exit /b 1
)

echo.
echo [2/2] Listar format (sok efter Premium-format med hogre bitrate)...
echo.
yt-dlp --cookies "%~dp0cookies.txt" -F "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

echo.
echo ===================================================
echo Om du ser format 356 (1080p Premium) eller liknande
echo hogbitrate-format sa fungerar dina Premium-cookies!
echo ===================================================
echo.
pause
