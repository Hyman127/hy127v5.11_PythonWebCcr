@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PS1_PATH=%~dpn0.ps1"
set "TRACE_PATH=%~dp0init_exit_trace.txt"
if "%CODE880_EXIT_TRACE%"=="1" (
    > "%TRACE_PATH%" echo [BAT] trace reset at %DATE% %TIME%
    >> "%TRACE_PATH%" echo [BAT] bat_path=%~f0
    >> "%TRACE_PATH%" echo [BAT] cwd=%CD%
    >> "%TRACE_PATH%" echo [BAT] ps1_path=%PS1_PATH%
    >> "%TRACE_PATH%" echo [BAT] comspec=%COMSPEC%
    >> "%TRACE_PATH%" echo [BAT] wt_session=%WT_SESSION%
) else (
    if exist "%TRACE_PATH%" del /q "%TRACE_PATH%" >nul 2>nul
)
if not exist "%PS1_PATH%" (
    if "%CODE880_EXIT_TRACE%"=="1" >> "%TRACE_PATH%" echo [BAT] ps1_missing=%PS1_PATH%
    echo.
    echo Re-initialization script not found: "%PS1_PATH%"
    echo Exit in 8 sec...
    powershell -NoProfile -Command "Start-Sleep -Seconds 8" >nul
    rem Close the CMD window opened for this launcher.
    if "%CODE880_EXIT_TRACE%"=="1" >> "%TRACE_PATH%" echo [BAT] before_exit_missing_ps1=1 at %DATE% %TIME%
    endlocal & exit 1
)

if "%CODE880_EXIT_TRACE%"=="1" >> "%TRACE_PATH%" echo [BAT] before_powershell at %DATE% %TIME%
powershell -NoProfile -STA -ExecutionPolicy Bypass -File "%PS1_PATH%"
set "FINAL_EXIT=%ERRORLEVEL%"
if "%CODE880_EXIT_TRACE%"=="1" >> "%TRACE_PATH%" echo [BAT] after_powershell errorlevel=%FINAL_EXIT% at %DATE% %TIME%

rem Close CMD after initialization and preserve the PowerShell exit code.
if "%CODE880_EXIT_TRACE%"=="1" >> "%TRACE_PATH%" echo [BAT] before_final_exit errorlevel=%FINAL_EXIT% at %DATE% %TIME%
endlocal & exit %FINAL_EXIT%
