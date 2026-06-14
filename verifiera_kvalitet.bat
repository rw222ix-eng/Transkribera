@echo off
chcp 65001 >nul

REM Lagg till Deno i PATH (kravs for yt-dlp signaturlosning)
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\DenoLand.Deno_*") do set "PATH=%%D;%PATH%"

echo === Verifiera Premium-bitrate ===
echo.

set URL=%~1
if "%URL%"=="" (
    echo Anvandning: verifiera_kvalitet.bat "https://youtube.com/watch?v=VIDEO_ID"
    echo.
    echo Laddar ner samma video MED och UTAN cookies
    echo och jamfor bitrate med ffprobe.
    pause
    exit /b 1
)

set TEMP_DIR=%TEMP%\yt_verify_%RANDOM%
mkdir "%TEMP_DIR%" 2>nul

echo [1/4] Laddar ner MED cookies (Premium)...
yt-dlp --cookies "%~dp0cookies.txt" -f "bv*[height<=1080]+ba/b[height<=1080]" -o "%TEMP_DIR%\med_premium.%%(ext)s" --no-playlist "%URL%"

echo.
echo [2/4] Laddar ner UTAN cookies (standard)...
yt-dlp -f "bv*[height<=1080]+ba/b[height<=1080]" -o "%TEMP_DIR%\utan_premium.%%(ext)s" --no-playlist "%URL%"

echo.
echo [3/4] Analyserar bitrate...
echo.
echo ============ MED Premium ============
for %%f in ("%TEMP_DIR%\med_premium.*") do (
    echo Fil: %%f
    ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,bit_rate -of default=noprint_wrappers=1 "%%f"
    echo.
)

echo ============ UTAN Premium ============
for %%f in ("%TEMP_DIR%\utan_premium.*") do (
    echo Fil: %%f
    ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,bit_rate -of default=noprint_wrappers=1 "%%f"
    echo.
)

echo [4/4] Rensar temporara filer...
rmdir /s /q "%TEMP_DIR%" 2>nul

echo.
echo Jamfor bit_rate ovan. Premium bor ge betydligt hogre bitrate
echo (t.ex. 6-10 Mbps vs 2-4 Mbps pa 1080p).
echo.
pause
