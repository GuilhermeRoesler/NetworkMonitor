#pragma once

#include "monitor.hpp"
#include "status_window.hpp"
#include "toast.hpp"
#include "tray_icon.hpp"

#include <windows.h>

#include <atomic>
#include <memory>
#include <thread>

namespace nm {

class AppController : public MonitorEventSink {
public:
    AppController(bool with_tray, bool show_window_at_start);
    ~AppController() override;

    int run(HINSTANCE instance, int ncmdshow);

    void on_peer_transition(const PeerTransitionEvent& event) override;
    void on_peer_discovered(const PeerDiscoveredEvent& event) override;
    void on_snapshot(const MonitorSnapshot& snapshot) override;
    void on_log_message(const std::string& message) override;

private:
    HINSTANCE instance_{nullptr};
    HWND message_window_{nullptr};
    TrayIcon tray_;
    std::unique_ptr<StatusWindow> status_window_;
    ToastManager toast_;
    std::atomic_bool stop_{false};
    std::thread monitor_thread_;
    bool with_tray_{true};
    bool show_window_at_start_{false};

    static constexpr UINT kMsgSnapshot = WM_APP + 10;
    static constexpr UINT kMsgPeerTransition = WM_APP + 11;
    static constexpr UINT kMsgOpenWindow = WM_APP + 12;
    static constexpr UINT kMsgToggleNotifications = WM_APP + 13;
    static constexpr UINT kMsgQuitApp = WM_APP + 14;
    static constexpr UINT kMsgLogLine = WM_APP + 15;

    static LRESULT CALLBACK WndProc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam);
    LRESULT handle_message(UINT message, WPARAM wparam, LPARAM lparam);
    bool create_message_window();
    void start_monitor();
    void stop_monitor();
    void open_window();
};

}  // namespace nm
