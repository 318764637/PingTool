// App.xaml.h — 应用程序类声明
#pragma once
#include "App.xaml.g.h"

namespace winrt::PingTool::implementation
{
    struct App : AppT<App>
    {
        App();

        void OnLaunched(Microsoft::UI::Xaml::LaunchActivatedEventArgs const& args);

    private:
        winrt::Microsoft::UI::Xaml::Window m_window{ nullptr };
    };
}

namespace winrt::PingTool::factory_implementation
{
    struct App : AppT<App, implementation::App> {};
}
