// PingWorker.h — Ping 引擎（C++ 版，与 Python 版 PingWorker 功能等效）
#pragma once
#include "pch.h"

struct PingResult {
    std::wstring target;
    int seq = 0;
    double latency = -1.0;  // ms, -1 = 超时
    bool timeout = true;
};

class PingWorker {
public:
    using Callback = std::function<void(PingResult)>;

    PingWorker() = default;
    ~PingWorker() { Stop(); }

    void Start(const std::wstring& target, Callback cb);
    void Stop();
    bool IsRunning() const { return m_running.load(); }

private:
    void Run();
    PingResult PingOnce(int seq);

    std::atomic<bool> m_running{false};
    std::thread m_thread;
    std::wstring m_target;
    Callback m_callback;
};
