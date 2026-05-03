
@echo off
setlocal

REM Get the directory of the currently running script
set "SCRIPT_DIR=%~dp0"

REM Remove the trailing backslash from the script directory path
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Get the package name from the script's parent directory name, removing the "__" prefix
for %%I in ("%SCRIPT_DIR%") do set "PKG=%%~nxI"
set "PKG=%PKG:~2%"

REM Define absolute paths for the source and destination directories
set "SOURCE_DIR=%SCRIPT_DIR%"
for %%I in ("%SCRIPT_DIR%\..\.venv\Lib\site-packages") do set "DEST_DIR=%%~fI"
set "PKG_DEST_DIR=%DEST_DIR%\%PKG%"


REM Delete the old package directory if it exists, using the absolute path
if exist "%PKG_DEST_DIR%" (
    echo Deleting old package directory: %PKG_DEST_DIR%
    rmdir /s /q "%PKG_DEST_DIR%"
)

REM Copy the package to the site-packages directory, using absolute paths
echo Copying from: %SOURCE_DIR%
echo Copying to:   %PKG_DEST_DIR%
robocopy "%SOURCE_DIR%" "%PKG_DEST_DIR%" /E /XD __pycache__ /XF *.bat *.pyc /NFL /NDL /NJH /NJS /nc /ns /np
if %errorlevel% lss 8 ( set "ROBOCOPY_OK=1" ) else ( set "ROBOCOPY_OK=0" )

echo.
echo Done copying %PKG% to %DEST_DIR%

if "%ROBOCOPY_OK%"=="0" (
    echo [ERROR] robocopy failed
    if not "%1"=="1" ( pause )
    endlocal
    exit /b 1
)

if not "%1"=="1" ( pause )
endlocal
exit /b 0
