@echo off
chcp 65001 >nul
echo ===========================================
echo  Ping Tool C++ (WinUI 3) - 编译脚本
echo ===========================================
echo.

set "VS_INSTALL=C:\Program Files\Microsoft Visual Studio\18\Community"

echo [1/3] 设置 VS 编译环境...
call "%VS_INSTALL%\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo 警告: vcvars 报错，尝试继续...
)

cd /d "%~dp0"

set "MSBUILD=%VS_INSTALL%\MSBuild\Current\Bin\MSBuild.exe"

echo.
echo [2/3] 还原 NuGet 包...
"%MSBUILD%" PingTool.sln /p:Configuration=Release /p:Platform=x64 /m /t:Restore /v:quiet 2>&1

echo.
echo [3/3] 编译 Release x64...
"%MSBUILD%" PingTool.sln /p:Configuration=Release /p:Platform=x64 /m /v:minimal

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ===========================================
    echo  编译成功！
    echo  输出: x64\Release\PingTool.exe
    echo ===========================================
    if exist "x64\Release\PingTool.exe" (
        echo 文件大小:
        dir "x64\Release\PingTool.exe" | find ".exe"
    )
) else (
    echo.
    echo ===========================================
    echo  编译失败，请检查上方错误信息
    echo ===========================================
)

pause
