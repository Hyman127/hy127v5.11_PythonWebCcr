@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Code880 Web 工作台

echo.
echo   Code880 Web 工作台 启动中...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0启动Web工作台.ps1" -ProjectRoot "%~dp0"

if %errorlevel% neq 0 (
    echo.
    echo   [!] 启动失败，请查看错误信息
    pause
    exit /b 1
)
