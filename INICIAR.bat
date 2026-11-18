@echo off
chcp 65001 >nul
title Cortes automaticos - NAO FECHE ESTA JANELA
cd /d "%~dp0"

echo ============================================================
echo   SISTEMA DE CORTES AUTOMATICOS
echo   Painel:  http://localhost:8000
echo   Videos:  http://localhost:8000/videos
echo.
echo   - Enquanto esta janela estiver aberta, o notebook NAO suspende.
echo   - Se o sistema fechar por erro, ele reinicia sozinho em 10 s.
echo   - Para PARAR: feche esta janela (no X).
echo ============================================================
echo.

set PRIMEIRA=1
:loop
if "%PRIMEIRA%"=="1" (
    ".venv\Scripts\python.exe" main.py
) else (
    ".venv\Scripts\python.exe" main.py --nao-abrir
)
set PRIMEIRA=0
echo.
echo [%date% %time%] O sistema fechou. Reiniciando em 10 segundos... (feche a janela para parar)
timeout /t 10 /nobreak >nul
goto loop
