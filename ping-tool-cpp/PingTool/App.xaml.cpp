// App.xaml.cpp — 应用程序类实现
#include "pch.h"
#include "App.xaml.h"
#include "MainWindow.xaml.h"

namespace winrt::PingTool::implementation
{
    App::App()
    {
        InitializeComponent();
    }

    void App::OnLaunched(Microsoft::UI::Xaml::LaunchActivatedEventArgs const& /*args*/)
    {
        m_window = winrt::make<MainWindow>();
        m_window.Activate();
    }
}
