// MainWindow.xaml.h — 主窗口声明
#pragma once
#include "MainWindow.xaml.g.h"
#include "PingWorker.h"
#include "DataManager.h"
#include "TailscaleManager.h"

namespace winrt::PingTool::implementation
{
    // 目标行 UI 组件引用
    struct TargetRowWidgets {
        winrt::Microsoft::UI::Xaml::Controls::Border RowBorder{ nullptr };
        winrt::Microsoft::UI::Xaml::Controls::TextBlock NameLabel{ nullptr };
        std::array<winrt::Microsoft::UI::Xaml::Controls::Border, 4> LatencyBlocks{};
        winrt::Microsoft::UI::Xaml::Controls::TextBlock AvgLabel{ nullptr };
        winrt::Microsoft::UI::Xaml::Controls::TextBlock DotLabel{ nullptr };
    };

    struct MainWindow : MainWindowT<MainWindow>
    {
        MainWindow();

        // 事件处理器
        void OnAddTarget(winrt::Windows::Foundation::IInspectable const& sender,
                         winrt::Microsoft::UI::Xaml::RoutedEventArgs const& e);
        void OnRemoveTarget(winrt::Windows::Foundation::IInspectable const& sender,
                            winrt::Microsoft::UI::Xaml::RoutedEventArgs const& e);
        void OnStartAll(winrt::Windows::Foundation::IInspectable const& sender,
                        winrt::Microsoft::UI::Xaml::RoutedEventArgs const& e);
        void OnStopAll(winrt::Windows::Foundation::IInspectable const& sender,
                       winrt::Microsoft::UI::Xaml::RoutedEventArgs const& e);
        void OnRestartTailscale(winrt::Windows::Foundation::IInspectable const& sender,
                                winrt::Microsoft::UI::Xaml::RoutedEventArgs const& e);

    private:
        // UI 构建
        void RebuildTargetRows();
        TargetRowWidgets BuildTargetRow(const std::wstring& target);
        void UpdateEmptyState();
        void SetUiRunning(bool running);

        // Ping 回调 → UI 更新
        void OnPingResult(PingResult result);
        void UpdateRowUI(const std::wstring& target);

        // Tailscale 完成回调
        void OnRestartDone(TailscaleManager::RestartResult result);

        // 辅助
        void SetStatus(const std::wstring& text);
        static winrt::Windows::UI::Color LatencyColor(double ms);
        static std::wstring LatencyDot(double ms);
        void StopTarget(const std::wstring& target);

        // 数据状态
        std::vector<std::wstring> m_targets;
        std::unordered_map<std::wstring, std::shared_ptr<PingWorker>> m_workers;
        std::unordered_map<std::wstring, std::deque<PingResult>> m_buffers;
        std::unordered_map<std::wstring, TargetRowWidgets> m_rows;
        bool m_isPinging = false;
    };
}

namespace winrt::PingTool::factory_implementation
{
    struct MainWindow : MainWindowT<MainWindow, implementation::MainWindow> {};
}
