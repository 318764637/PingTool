// TailscaleManager.h — Tailscale 服务重启管理
#pragma once
#include "pch.h"

class TailscaleManager {
public:
    struct RestartResult {
        bool success = false;
        std::wstring message;
    };

    static RestartResult Restart();

private:
    static bool IsAdmin();
    static RestartResult RestartWithUAC();
    static RestartResult RestartDirect();

    static constexpr const wchar_t* SERVICE_NAME = L"Tailscale";
};
