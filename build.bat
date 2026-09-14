@echo off
chcp 65001 >nul
echo ===========================================
echo  Ping Tool - 打包脚本
echo ===========================================
echo.

echo [1/2] 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/2] 开始打包...
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "PingTool" ^
    --icon "assets\app.ico" ^
    --add-data "targets.json;." ^
    --add-data "assets\app.ico;assets" ^
    --collect-data customtkinter ^
    --hidden-import "ping_tool" ^
    --hidden-import "ping_tool.core" ^
    --hidden-import "ping_tool.core.ping_worker" ^
    --hidden-import "ping_tool.core.tailscale" ^
    --hidden-import "ping_tool.data" ^
    --hidden-import "ping_tool.data.manager" ^
    --hidden-import "ping_tool.ui" ^
    --hidden-import "ping_tool.ui.app" ^
    --hidden-import "ping_tool.ui.styles" ^
    --hidden-import "ping_tool.ui.components" ^
    --hidden-import "ping_tool.ui.components.status_bar" ^
    --hidden-import "ping_tool.ui.components.tailscale_card" ^
    --hidden-import "ping_tool.ui.components.target_card" ^
    --hidden-import "ping_tool.utils" ^
    --hidden-import "ping_tool.utils.validators" ^
    --hidden-import "ping_tool.config" ^
    --hidden-import "ping_tool.logger" ^
    --clean ^
    main.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ===========================================
    echo  打包成功！文件位于 dist\PingTool.exe
    echo ===========================================
) else (
    echo.
    echo ===========================================
    echo  打包失败，请检查上方错误信息
    echo ===========================================
)

pause
