@echo off
rem Dra inspelningen hit och släpp — det är hela gränssnittet. Ligger manuset som
rem en .txt med SAMMA namn bredvid ljudfilen plockas det upp automatiskt, så en
rem släppt fil räcker även när stavningen ska styras av pappret.
rem
rem %~dp0 = mappen den här filen ligger i. cd dit först: manus.py importerar app/
rem och hittar nyckelfilen relativt sig själv, men Utforskaren startar en släppt
rem fil i en helt annan katalog.
cd /d "%~dp0"
if "%~1"=="" (
  echo Dra en ljud- eller videofil hit och slapp den pa manus.bat.
  pause
  exit /b 1
)
if exist "%~dpn1.txt" (
  python manus.py "%~f1" --manus "%~dpn1.txt"
) else (
  python manus.py "%~f1"
)
rem Pausen finns för att fönstret annars stänger sig i samma sekund som det blir
rem klart — och då syns varken filnamnen eller ett eventuellt fel.
pause
