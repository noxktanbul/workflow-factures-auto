@echo off
setlocal EnableDelayedExpansion
title Robot Factures - Launcher

:: ---------------------------------------------------------------------------
:: FIX UX-01 : Creation automatique du raccourci Bureau vers le dossier Entrant
:: ---------------------------------------------------------------------------
set "ENTRANT=%~dp0Entrant"
set "SHORTCUT=%USERPROFILE%\Desktop\Deposer Factures ICI.lnk"

if not exist "%SHORTCUT%" (
    powershell -NoProfile -Command ^
        "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%ENTRANT%'; $s.IconLocation = 'shell32.dll,4'; $s.Description = 'Deposer vos factures PDF ici pour traitement automatique'; $s.Save()"
    echo [INFO] Raccourci Bureau cree : Deposer Factures ICI
)

:: ---------------------------------------------------------------------------
:: Recompilation automatique si le .exe est absent ou si les sources sont plus recents
:: ---------------------------------------------------------------------------
set "EXE=%~dp0dist\Robot_Factures.exe"
set "SPEC=%~dp0Robot_Factures.spec"

if not exist "%EXE%" (
    echo [INFO] Aucun exe trouve. Recompilation en cours...
    where pyinstaller >nul 2>&1 && (
        cd /d "%~dp0"
        pyinstaller "%SPEC%" --noconfirm
        echo [INFO] Compilation terminee.
    ) || (
        echo [WARN] PyInstaller introuvable. Lancement en mode script Python.
    )
)

:: ---------------------------------------------------------------------------
:: FIX ROBUST-03 : Boucle de redemarrage automatique en cas de crash
:: ---------------------------------------------------------------------------
:start
echo.
echo [%DATE% %TIME%] Demarrage de Robot_Factures...
echo [%DATE% %TIME%] Demarrage >> "%~dp0launcher.log"

:: Lancement du .exe depuis dist/
if exist "%~dp0dist\Robot_Factures.exe" (
    "%~dp0dist\Robot_Factures.exe"
) else if exist "%~dp0dist\main_watcher.exe" (
    "%~dp0dist\main_watcher.exe"
) else (
    :: Fallback : lancement direct Python si aucun exe trouve
    python "%~dp0main_watcher.py"
)

set EXIT_CODE=%ERRORLEVEL%
echo [%DATE% %TIME%] Robot_Factures arrete (code: %EXIT_CODE%) >> "%~dp0launcher.log"

if %EXIT_CODE% EQU 0 (
    echo [INFO] Arret normal. Fermeture du launcher.
    goto end
)

echo [WARN] Arret inattendu (code %EXIT_CODE%). Redemarrage dans 10 secondes...
echo [%DATE% %TIME%] Redemarrage dans 10s... >> "%~dp0launcher.log"
timeout /t 10 /nobreak >nul
goto start

:end
echo Launcher ferme.
pause
