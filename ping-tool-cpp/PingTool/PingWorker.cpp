// PingWorker.cpp — Ping 引擎实现
#include "pch.h"
#include "PingWorker.h"

void PingWorker::Start(const std::wstring& target, Callback cb) {
    if (m_running.load()) return;
    m_target = target;
    m_callback = std::move(cb);
    m_running.store(true);
    m_thread = std::thread(&PingWorker::Run, this);
}

void PingWorker::Stop() {
    m_running.store(false);
    if (m_thread.joinable()) {
        // Run 内部每 100ms 轮询停止标志并会 TerminateProcess 子进程，
        // 因此 join 最多阻塞约 100ms + 收尾时间，不会卡死 UI 线程。
        m_thread.join();
    }
}

void PingWorker::Run() {
    int seq = 0;
    while (m_running.load()) {
        ++seq;
        ULONGLONG cycleStart = GetTickCount64();
        PingResult result = PingOnce(seq);
        result.target = m_target;
        if (m_callback && m_running.load()) {
            m_callback(result);
        }
        // 周期 = 1s 自本次发起算起（ping 耗时计入周期）
        ULONGLONG elapsed = GetTickCount64() - cycleStart;
        LONG waitMs = 1000 - static_cast<LONG>(elapsed);
        while (m_running.load() && waitMs > 0) {
            Sleep(min(100, waitMs));
            waitMs -= 100;
        }
    }
}

PingResult PingWorker::PingOnce(int seq) {
    PingResult r;
    r.seq = seq;

    // 构建命令行: ping -n 1 -w 3000 <target>
    std::wstring cmdLine = L"ping -n 1 -w 3000 " + m_target;

    SECURITY_ATTRIBUTES sa = {sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
    HANDLE hStdOutRead = nullptr, hStdOutWrite = nullptr;

    if (!CreatePipe(&hStdOutRead, &hStdOutWrite, &sa, 0)) {
        r.timeout = true;
        r.latency = -1.0;
        return r;
    }
    SetHandleInformation(hStdOutRead, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOW si = {sizeof(STARTUPINFOW)};
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    si.hStdOutput = hStdOutWrite;
    si.hStdError = hStdOutWrite;

    PROCESS_INFORMATION pi = {};

    // 拷贝到可写缓冲区：CreateProcessW 允许修改 lpCommandLine，
    // 不能用 const_cast<LPWSTR>(c_str())（违反只读契约，属未定义行为）。
    std::vector<wchar_t> cmdBuf(cmdLine.begin(), cmdLine.end());
    cmdBuf.push_back(L'\0');

    BOOL ok = CreateProcessW(
        nullptr, cmdBuf.data(),
        nullptr, nullptr, TRUE,
        CREATE_NO_WINDOW, nullptr, nullptr,
        &si, &pi
    );

    CloseHandle(hStdOutWrite);

    if (!ok) {
        CloseHandle(hStdOutRead);
        r.timeout = true;
        r.latency = -1.0;
        return r;
    }

    // 等待进程结束：每 100ms 轮询（可响应停止），累计超时或停止请求
    // 则 TerminateProcess，避免 ReadFile 无限阻塞并防止子进程泄漏。
    const DWORD kTotalTimeoutMs = 5000;
    DWORD waited = 0;
    while (WaitForSingleObject(pi.hProcess, 100) == WAIT_TIMEOUT) {
        waited += 100;
        if (waited >= kTotalTimeoutMs || !m_running.load()) {
            TerminateProcess(pi.hProcess, 0);
            WaitForSingleObject(pi.hProcess, 500);  // 等待退出以关闭管道
            break;
        }
    }

    // 读取输出
    std::string output;
    char buffer[256];
    DWORD bytesRead;
    while (ReadFile(hStdOutRead, buffer, sizeof(buffer) - 1, &bytesRead, nullptr) && bytesRead > 0) {
        buffer[bytesRead] = '\0';
        output += buffer;
    }
    CloseHandle(hStdOutRead);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

    // 解析输出：匹配 "时间<1ms", "时间=Xms", "time<1ms", "time=Xms"
    // 中文 Windows GBK 编码输出
    auto find = [&](const std::string& pattern, size_t& pos) -> bool {
        pos = output.find(pattern);
        return pos != std::string::npos;
    };

    size_t pos;

    // <1ms
    if (find("\xCA\xB1\xBC\xE4<1ms", pos) || find("time<1ms", pos)) {
        r.timeout = false;
        r.latency = 0.5;
        return r;
    }

    // 时间=Xms 或 time=Xms
    auto tryExtract = [&](const std::string& prefix) -> bool {
        size_t p = output.find(prefix);
        if (p == std::string::npos) return false;
        p += prefix.length();
        // p now points to digit(s) before "ms"
        double val = 0;
        while (p < output.length() && isdigit(static_cast<unsigned char>(output[p]))) {
            val = val * 10 + (output[p] - '0');
            ++p;
        }
        if (val > 0) {
            r.timeout = false;
            r.latency = val;
            return true;
        }
        return false;
    };

    if (tryExtract("\xCA\xB1\xBC\xE4=") || tryExtract("time=") || tryExtract("\xCA\xB1\xBC\xE4<") || tryExtract("time<")) {
        return r;
    }

    // 超时
    r.timeout = true;
    r.latency = -1.0;
    return r;
}
