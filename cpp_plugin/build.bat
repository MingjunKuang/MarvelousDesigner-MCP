@echo off
setlocal ENABLEDELAYEDEXPANSION

rem Build the MD MCP C++ plugin. Run from the cpp_plugin directory or from anywhere.
rem Override QTDIR / CLO_SDK on the command line if your install paths differ.

rem Run from a Visual Studio developer command prompt with cmake on PATH.
if "%QTDIR%"=="" exit /b 1
if "%CLO_SDK%"=="" exit /b 1
where cmake >nul 2>nul || exit /b 1
pushd "%~dp0"

echo [build] QTDIR=%QTDIR%
echo [build] CLO_SDK=%CLO_SDK%

cmake -S . -B build -G "Visual Studio 17 2022" -A x64 ^
    -DQTDIR="%QTDIR%" -DCLO_SDK="%CLO_SDK%" || (popd & exit /b 1)

cmake --build build --config Release -j || (popd & exit /b 1)

echo.
echo [build] OK. Output: %CD%\build\Release\MdMcpPlugin.dll
popd
endlocal
