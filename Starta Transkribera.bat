@echo off
title Transkribera
cd /d "%~dp0"
echo ============================================================
echo   Startar Transkribera...
echo   En flik oppnas i din webblasare. Lat detta fonster vara
echo   oppet medan du anvander appen - stang det for att avsluta.
echo ============================================================
echo.
python -m app.web
echo.
echo Transkribera har stangts.
pause
