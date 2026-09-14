// TailscaleManager.cpp — Tailscale 服务重启实现
#include "pch.h"
#include "TailscaleManager.h"

TailscaleManager::RestartResult TailscaleManager::Restart() {
    if (!IsAdmin()) {
        return RestartWithUAC();
    }
    return RestartDirect();
}

bool TailscaleManager::IsAdmin() {
    BOOL isAdmin = FALSE;
    PSID adminGroup = nullptr;
    SID_IDENTIFIER_AUTHORITY ntAuthority = SECURITY_NT_AUTHORITY;
    if (AllocateAndInitializeSid(&ntAuthority, 2,
            SECURITY_BUILTIN_DOMAIN_RID,
            DOMAIN_ALIAS_RID_ADMINS,
            0, 0, 0, 0, 0, 0, &adminGroup)) {
        CheckTokenMembership(nullptr, adminGroup, &isAdmin);
        FreeSid(adminGroup);
    }
    return isAdmin != FALSE;
}

TailscaleManager::RestartResult TailscaleManager::RestartWithUAC() {
    // 创建批处理脚本并用 runas 提权执行
    wchar_t tempPath[MAX_PATH];
    GetTempPathW(MAX_PATH, tempPath);
    std::wstring batchPath = std::wstring(tempPath) + L"tailscale_restart.bat";

    std::wstring batch = L"@echo off\r\nsc stop ";
    batch += SERVICE_NAME;
    batch += L"\r\ntimeout /t 3 /nobreak >nul\r\nsc start ";
    batch += SERVICE_NAME;
    batch += L"\r\npause\r\n";

    FILE* f = _wfopen(batchPath.c_str(), L"w, ccs=UTF-8");
    if (!f) {
        return {false, L"无法创建批处理文件"};
    }
    fputws(batch.c_str(), f);
    fclose(f);

    SHELLEXECUTEINFOW sei = {sizeof(SHELLEXECUTEINFOW)};
    sei.fMask = SEE_MASK_NOCLOSEPROCESS;
    sei.lpVerb = L"runas";
    sei.lpFile = batchPath.c_str();
    sei.nShow = SW_SHOWNORMAL;

    if (ShellExecuteExW(&sei)) {
        if (sei.hProcess) CloseHandle(sei.hProcess);
        return {true, L"已弹出管理员确认窗口，请在弹出窗口中确认并等待完成"};
    }
    return {false, L"无法提权执行，请以管理员身份运行本程序后重试"};
}

TailscaleManager::RestartResult TailscaleManager::RestartDirect() {
    RestartResult result;

    // 停止服务
    STARTUPINFOW si = {sizeof(STARTUPINFOW)};
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    PROCESS_INFORMATION pi = {};

    std::wstring stopCmd = std::wstring(L"sc stop ") + SERVICE_NAME;
    if (CreateProcessW(nullptr, stopCmd.data(), nullptr, nullptr, FALSE,
            CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi)) {
        WaitForSingleObject(pi.hProcess, 10000);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    }

    Sleep(3000); // 等待服务完全停止

    // 启动服务
    std::wstring startCmd = std::wstring(L"sc start ") + SERVICE_NAME;
    if (CreateProcessW(nullptr, startCmd.data(), nullptr, nullptr, FALSE,
            CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi)) {
        WaitForSingleObject(pi.hProcess, 10000);
        DWORD exitCode = 0;
        GetExitCodeProcess(pi.hProcess, &exitCode);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);

        if (exitCode == 0) {
            result.success = true;
            result.message = L"Tailscale 重启成功";
        } else {
            result.success = false;
            result.message = L"启动失败，请检查 Tailscale 服务状态";
        }
    } else {
        result.success = false;
        result.message = L"无法执行 sc 命令";
    }

    return result;
}
