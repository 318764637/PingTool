// MainWindow.xaml.cpp — 主窗口实现（多目标 Ping + Tailscale 管理）
#include "pch.h"
#include "MainWindow.xaml.h"

using namespace winrt;
using namespace Microsoft::UI::Xaml;
using namespace Microsoft::UI::Xaml::Controls;
using namespace Microsoft::UI::Xaml::Media;

namespace winrt::PingTool::implementation
{
    MainWindow::MainWindow()
    {
        InitializeComponent();

        // 加载已保存的目标
        m_targets = DataManager::Load();

        // 设置窗口默认大小
        this->AppWindow().Resize({500, 550});

        RebuildTargetRows();
    }

    // ════════════════════════════════════════════════════════
    // UI 构建
    // ════════════════════════════════════════════════════════

    void MainWindow::RebuildTargetRows()
    {
        RowsPanel().Children().Clear();
        m_rows.clear();

        if (m_targets.empty()) {
            UpdateEmptyState();
            return;
        }

        EmptyLabel().Visibility(Visibility::Collapsed);

        for (const auto& t : m_targets) {
            m_rows[t] = BuildTargetRow(t);
            // 初始化环形缓冲区
            if (m_buffers.find(t) == m_buffers.end()) {
                m_buffers[t] = std::deque<PingResult>();
            }
        }

        StartAllBtn().IsEnabled(!m_isPinging);
    }

    TargetRowWidgets MainWindow::BuildTargetRow(const std::wstring& target)
    {
        TargetRowWidgets w;

        // 行容器
        auto rowBorder = Controls::Border();
        rowBorder.Background(SolidColorBrush(Windows::UI::ColorHelper::FromArgb(0xFF, 0xE8, 0xF4, 0xFD)));
        rowBorder.CornerRadius(CornerRadius{8, 8, 8, 8});
        rowBorder.Padding(ThicknessHelper::FromUniform(6));
        rowBorder.Margin(ThicknessHelper::FromLengths(0, 0, 0, 3));

        auto rowGrid = Grid();
        rowGrid.ColumnDefinitions().Append(ColumnDefinition{});
        rowGrid.ColumnDefinitions().Append(ColumnDefinition{});
        rowGrid.ColumnDefinitions().Append(ColumnDefinition{});
        rowGrid.ColumnDefinitions().Append(ColumnDefinition{});
        rowGrid.ColumnDefinitions().Append(ColumnDefinition{});

        // Col 0: 目标名
        auto nameLabel = TextBlock();
        nameLabel.Text(target);
        nameLabel.FontFamily(FontFamily(L"Consolas"));
        nameLabel.FontSize(14);
        nameLabel.FontWeight(Text::FontWeights::SemiBold());
        nameLabel.Foreground(SolidColorBrush(Windows::UI::ColorHelper::FromArgb(0xFF, 0x1E, 0x29, 0x3B)));
        nameLabel.VerticalAlignment(VerticalAlignment::Center);
        rowGrid.ColumnDefinitions().GetAt(0).Width({130, GridUnitType::Pixel});
        nameLabel.SetValue(Grid::ColumnProperty(), winrt::box_value(0));
        rowGrid.Children().Append(nameLabel);
        w.NameLabel = nameLabel;

        // Col 1: 4 个延迟色块
        auto blocksPanel = StackPanel();
        blocksPanel.Orientation(Orientation::Horizontal);
        blocksPanel.Spacing(4);
        blocksPanel.VerticalAlignment(VerticalAlignment::Center);
        blocksPanel.SetValue(Grid::ColumnProperty(), winrt::box_value(1));
        rowGrid.ColumnDefinitions().GetAt(1).Width({1.0, GridUnitType::Star});

        for (int i = 0; i < 4; ++i) {
            auto blk = Controls::Border();
            blk.Width(14);
            blk.Height(14);
            blk.CornerRadius(CornerRadius{3, 3, 3, 3});
            blk.Background(SolidColorBrush(Windows::UI::ColorHelper::FromArgb(0xFF, 0xCB, 0xD5, 0xE1)));
            blocksPanel.Children().Append(blk);
            w.LatencyBlocks[i] = blk;
        }
        rowGrid.Children().Append(blocksPanel);

        // Col 2: 平均延迟
        auto avgLabel = TextBlock();
        avgLabel.Text(L"-- ms");
        avgLabel.FontSize(13);
        avgLabel.Foreground(SolidColorBrush(Windows::UI::ColorHelper::FromArgb(0xFF, 0x64, 0x74, 0x8B)));
        avgLabel.VerticalAlignment(VerticalAlignment::Center);
        avgLabel.TextAlignment(TextAlignment::Center);
        rowGrid.ColumnDefinitions().GetAt(2).Width({55, GridUnitType::Pixel});
        avgLabel.SetValue(Grid::ColumnProperty(), winrt::box_value(2));
        rowGrid.Children().Append(avgLabel);
        w.AvgLabel = avgLabel;

        // Col 3: 状态指示灯
        auto dotLabel = TextBlock();
        dotLabel.Text(L"⚫");
        dotLabel.FontSize(10);
        dotLabel.VerticalAlignment(VerticalAlignment::Center);
        dotLabel.Margin(ThicknessHelper::FromLengths(6, 0, 6, 0));
        rowGrid.ColumnDefinitions().GetAt(3).Width({24, GridUnitType::Pixel});
        dotLabel.SetValue(Grid::ColumnProperty(), winrt::box_value(3));
        rowGrid.Children().Append(dotLabel);
        w.DotLabel = dotLabel;

        // Col 4: 删除按钮
        auto delBtn = Button();
        delBtn.Content(winrt::box_value(L"❌"));
        delBtn.Width(28);
        delBtn.Height(28);
        delBtn.Background(SolidColorBrush(Colors::Transparent()));
        delBtn.Foreground(SolidColorBrush(Windows::UI::ColorHelper::FromArgb(0xFF, 0xEF, 0x44, 0x44)));
        delBtn.FontSize(12);
        delBtn.CornerRadius(CornerRadius{6, 6, 6, 6});
        // 将目标名存入 Tag 以便回调时识别
        delBtn.Tag(winrt::box_value(target));
        delBtn.Click([this](auto const& sender, auto const&) {
            auto btn = sender.as<Button>();
            auto t = winrt::unbox_value_or<std::wstring>(btn.Tag(), L"");
            // 停止该目标的 Ping
            StopTarget(t);
            // 持久化删除
            DataManager::Delete(t);
            // 刷新
            m_targets = DataManager::Load();
            m_buffers.erase(t);
            RebuildTargetRows();
            SetStatus(L"已删除: " + t);
        });
        rowGrid.ColumnDefinitions().GetAt(4).Width({32, GridUnitType::Pixel});
        delBtn.SetValue(Grid::ColumnProperty(), winrt::box_value(4));
        rowGrid.Children().Append(delBtn);

        rowBorder.Child(rowGrid);
        RowsPanel().Children().Append(rowBorder);
        w.RowBorder = rowBorder;

        return w;
    }

    void MainWindow::UpdateEmptyState()
    {
        EmptyLabel().Visibility(m_targets.empty() ? Visibility::Visible : Visibility::Collapsed);
        if (m_targets.empty() && !m_isPinging) {
            StartAllBtn().IsEnabled(false);
        }
    }

    // ════════════════════════════════════════════════════════
    // 事件处理
    // ════════════════════════════════════════════════════════

    void MainWindow::OnAddTarget(IInspectable const&, RoutedEventArgs const&)
    {
        std::wstring target = TargetInput().Text().c_str();
        // 去除首尾空格
        size_t start = target.find_first_not_of(L" \t\r\n");
        size_t end = target.find_last_not_of(L" \t\r\n");
        if (start == std::wstring::npos || end == std::wstring::npos) {
            SetStatus(L"请输入有效的 IP 地址或域名");
            return;
        }
        target = target.substr(start, end - start + 1);

        if (DataManager::Add(target)) {
            m_targets = DataManager::Load();
            TargetInput().Text(L"");
            RebuildTargetRows();
            SetStatus(L"已添加: " + target);
        } else {
            // 可能已存在
            auto existing = DataManager::Load();
            bool found = false;
            for (const auto& t : existing) {
                if (t == target) { found = true; break; }
            }
            if (found) {
                SetStatus(L"'" + target + L"' 已在列表中");
            } else {
                SetStatus(L"保存失败，请检查文件权限");
            }
        }
    }

    void MainWindow::OnRemoveTarget(IInspectable const&, RoutedEventArgs const&)
    {
        // 由 BuildTargetRow 中的 lambda 处理
    }

    void MainWindow::OnStartAll(IInspectable const&, RoutedEventArgs const&)
    {
        if (m_targets.empty()) {
            SetStatus(L"请先添加目标");
            return;
        }

        m_isPinging = true;
        SetUiRunning(true);

        int count = 0;
        for (const auto& t : m_targets) {
            if (m_workers.find(t) == m_workers.end() || !m_workers[t]->IsRunning()) {
                auto worker = std::make_shared<PingWorker>();
                m_workers[t] = worker;
                // 确保缓冲区存在
                if (m_buffers.find(t) == m_buffers.end()) {
                    m_buffers[t] = std::deque<PingResult>();
                } else {
                    m_buffers[t].clear();
                }
                auto weakThis = this->get_weak();
                worker->Start(t, [weakThis](PingResult r) {
                    auto strong = weakThis.get();
                    if (strong) {
                        // 投递到 UI 线程
                        strong->DispatcherQueue().TryEnqueue([strong, r]() {
                            strong->OnPingResult(r);
                        });
                    }
                });
                count++;
            }
            // 更新指示灯为等待状态
            if (m_rows.find(t) != m_rows.end()) {
                m_rows[t].DotLabel.Text(L"🟡");
            }
        }
        SetStatus(L"已启动 " + std::to_wstring(count) + L" 个目标 Ping");
    }

    void MainWindow::OnStopAll(IInspectable const&, RoutedEventArgs const&)
    {
        m_isPinging = false;
        for (auto& [t, w] : m_workers) {
            w->Stop();
        }
        m_workers.clear();

        SetUiRunning(false);

        // 重置所有指示灯
        for (auto& [t, row] : m_rows) {
            row.DotLabel.Text(L"⚫");
        }
        SetStatus(L"已停止");
    }

    void MainWindow::OnRestartTailscale(IInspectable const&, RoutedEventArgs const&)
    {
        // 确认对话框
        ContentDialog dialog;
        dialog.Title(winrt::box_value(L"确认重启 Tailscale"));
        dialog.Content(winrt::box_value(L"将要重启 Tailscale 服务，\n\n你的 Tailscale 连接会短暂中断（约 3-5 秒），\n确定要继续吗？"));
        dialog.PrimaryButtonText(L"确定");
        dialog.CloseButtonText(L"取消");
        dialog.DefaultButton(ContentDialogButton::Primary);
        dialog.XamlRoot(this->Content().XamlRoot());

        dialog.PrimaryButtonClick([this](auto const&, auto const&) {
            RestartTsBtn().Content(winrt::box_value(L"重启中..."));
            RestartTsBtn().IsEnabled(false);
            TsStatusLabel().Text(L"正在重启...");
            TsStatusLabel().Foreground(SolidColorBrush(Windows::UI::ColorHelper::FromArgb(0xFF, 0x64, 0x74, 0x8B)));

            // 后台线程执行
            auto weakThis = this->get_weak();
            std::thread([weakThis]() {
                auto result = TailscaleManager::Restart();
                auto strong = weakThis.get();
                if (strong) {
                    strong->DispatcherQueue().TryEnqueue([strong, result]() {
                        strong->OnRestartDone(result);
                    });
                }
            }).detach();
        });

        dialog.ShowAsync();
    }

    // ════════════════════════════════════════════════════════
    // Ping 回调
    // ════════════════════════════════════════════════════════

    void MainWindow::OnPingResult(PingResult result)
    {
        auto& buf = m_buffers[result.target];
        buf.push_back(result);
        // 限制缓冲区大小为 4
        while (buf.size() > 4) buf.pop_front();
        UpdateRowUI(result.target);
    }

    void MainWindow::UpdateRowUI(const std::wstring& target)
    {
        auto it = m_rows.find(target);
        if (it == m_rows.end()) return;

        auto& row = it->second;
        auto bufIt = m_buffers.find(target);
        if (bufIt == m_buffers.end()) return;

        auto& buf = bufIt->second;
        std::vector<PingResult> results(buf.begin(), buf.end());

        // 更新 4 个色块
        for (int i = 0; i < 4; i++) {
            if (i < (int)results.size()) {
                auto& r = results[i];
                Windows::UI::Color c;
                if (r.timeout) {
                    c = Windows::UI::ColorHelper::FromArgb(0xFF, 0x64, 0x74, 0x8B); // 灰色
                } else {
                    c = LatencyColor(r.latency);
                }
                row.LatencyBlocks[i].Background(SolidColorBrush(c));
            } else {
                row.LatencyBlocks[i].Background(
                    SolidColorBrush(Windows::UI::ColorHelper::FromArgb(0xFF, 0xCB, 0xD5, 0xE1)));
            }
        }

        // 平均延迟
        double sum = 0;
        int valid = 0;
        for (auto& r : results) {
            if (!r.timeout) { sum += r.latency; valid++; }
        }
        if (valid > 0) {
            double avg = sum / valid;
            wchar_t buf2[32];
            swprintf_s(buf2, L"%.0f ms", avg);
            row.AvgLabel.Text(buf2);
            row.AvgLabel.Foreground(SolidColorBrush(Windows::UI::ColorHelper::FromArgb(0xFF, 0x1E, 0x29, 0x3B)));
        } else if (!results.empty()) {
            row.AvgLabel.Text(L"超时");
            row.AvgLabel.Foreground(SolidColorBrush(Windows::UI::ColorHelper::FromArgb(0xFF, 0xEF, 0x44, 0x44)));
        }

        // 状态灯
        if (!results.empty()) {
            auto& last = results.back();
            row.DotLabel.Text(LatencyDot(last.timeout ? -1.0 : last.latency));
        }
    }

    // ════════════════════════════════════════════════════════
    // Tailscale 回调
    // ════════════════════════════════════════════════════════

    void MainWindow::OnRestartDone(TailscaleManager::RestartResult result)
    {
        RestartTsBtn().Content(winrt::box_value(L"🔄 重启 Tailscale"));
        RestartTsBtn().IsEnabled(true);

        if (result.success) {
            TsStatusLabel().Text(L"✅ " + result.message);
            TsStatusLabel().Foreground(
                SolidColorBrush(Windows::UI::ColorHelper::FromArgb(0xFF, 0x10, 0xB9, 0x81)));
        } else {
            TsStatusLabel().Text(L"❌ " + result.message);
            TsStatusLabel().Foreground(
                SolidColorBrush(Windows::UI::ColorHelper::FromArgb(0xFF, 0xEF, 0x44, 0x44)));
        }
    }

    // ════════════════════════════════════════════════════════
    // 辅助
    // ════════════════════════════════════════════════════════

    void MainWindow::SetUiRunning(bool running)
    {
        StartAllBtn().IsEnabled(!running && !m_targets.empty());
        StopAllBtn().IsEnabled(running);
        AddButton().IsEnabled(!running);
        TargetInput().IsEnabled(!running);
    }

    void MainWindow::StopTarget(const std::wstring& target)
    {
        auto it = m_workers.find(target);
        if (it != m_workers.end()) {
            it->second->Stop();
            m_workers.erase(it);
        }
        if (m_rows.find(target) != m_rows.end()) {
            m_rows[target].DotLabel.Text(L"⚫");
            // 清空色块
            for (auto& blk : m_rows[target].LatencyBlocks) {
                blk.Background(SolidColorBrush(
                    Windows::UI::ColorHelper::FromArgb(0xFF, 0xCB, 0xD5, 0xE1)));
            }
            m_rows[target].AvgLabel.Text(L"-- ms");
            m_rows[target].AvgLabel.Foreground(
                SolidColorBrush(Windows::UI::ColorHelper::FromArgb(0xFF, 0x64, 0x74, 0x8B)));
        }
    }

    void MainWindow::SetStatus(const std::wstring& text)
    {
        StatusBar().Text(text);
    }

    Windows::UI::Color MainWindow::LatencyColor(double ms)
    {
        if (ms < 30)  return Windows::UI::ColorHelper::FromArgb(0xFF, 0x10, 0xB9, 0x81); // 绿
        if (ms < 80)  return Windows::UI::ColorHelper::FromArgb(0xFF, 0x3B, 0x82, 0xF6); // 蓝
        if (ms < 150) return Windows::UI::ColorHelper::FromArgb(0xFF, 0xF5, 0x9E, 0x0B); // 琥珀
        return Windows::UI::ColorHelper::FromArgb(0xFF, 0xEF, 0x44, 0x44);               // 红
    }

    std::wstring MainWindow::LatencyDot(double ms)
    {
        if (ms < 0)  return L"⚫";
        if (ms < 30)  return L"🟢";
        if (ms < 80)  return L"🔵";
        if (ms < 150) return L"🟡";
        return L"🔴";
    }
}
