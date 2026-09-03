#include "app_controller.hpp"

#include "config.hpp"
#include "logging.hpp"
#include "win32_helpers.hpp"

#include <shellapi.h>

namespace nm {
namespace {

constexpr wchar_t kControllerClassName[] = L"NetworkMonitorAppController";

}  // namespace

AppController::AppController(bool with_tray, bool show_window_at_start)
    : with_tray_(with_tray), show_window_at_start_(show_window_at_start) {}

AppController::~AppController() { stop_monitor(); }

int AppController::run(HINSTANCE instance, int ncmdshow) {
    instance_ = instance;
    (void)ncmdshow;
    set_console_logging_enabled(false);

    if (!create_message_window()) {
        return 1;
    }

    status_window_ = std::make_unique<StatusWindow>(message_window_, with_tray_);
    if (!status_window_->create(instance_)) {
        return 1;
    }

    if (with_tray_) {
        tray_.create(message_window_);
    }
    if (show_window_at_start_) {
        status_window_->show();
    }

    start_monitor();

    MSG msg{};
    while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }

    stop_.store(true);
    tray_.destroy();
    stop_monitor();
    if (status_window_ != nullptr) {
        status_window_->close();
    }
    return static_cast<int>(msg.wParam);
}

void AppController::on_peer_transition(const PeerTransitionEvent& event) {
    auto* payload = new PeerTransitionEvent(event);
    post_message_if_window(message_window_, kMsgPeerTransition, 0, reinterpret_cast<LPARAM>(payload));
}

void AppController::on_peer_discovered(const PeerDiscoveredEvent& event) {
    (void)event;
    // O próximo on_snapshot do loop já atualiza o painel com a lista completa.
}

void AppController::on_snapshot(const MonitorSnapshot& snapshot) {
    auto* payload = new MonitorSnapshot(snapshot);
    post_message_if_window(message_window_, kMsgSnapshot, 0, reinterpret_cast<LPARAM>(payload));
}

void AppController::on_log_message(const std::string& message) {
    auto* payload = new std::string(message);
    post_message_if_window(message_window_, kMsgLogLine, 0, reinterpret_cast<LPARAM>(payload));
}

LRESULT CALLBACK AppController::WndProc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
    if (message == WM_NCCREATE) {
        auto* create = reinterpret_cast<CREATESTRUCTW*>(lparam);
        auto* self = static_cast<AppController*>(create->lpCreateParams);
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
        return DefWindowProcW(hwnd, message, wparam, lparam);
    }

    auto* self = reinterpret_cast<AppController*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
    if (self != nullptr) {
        return self->handle_message(message, wparam, lparam);
    }
    return DefWindowProcW(hwnd, message, wparam, lparam);
}

LRESULT AppController::handle_message(UINT message, WPARAM wparam, LPARAM lparam) {
    switch (message) {
        case WM_APP + 1:
            if (LOWORD(lparam) == WM_LBUTTONDBLCLK) {
                open_window();
            } else if (LOWORD(lparam) == WM_RBUTTONUP || LOWORD(lparam) == WM_CONTEXTMENU) {
                tray_.show_context_menu();
            }
            return 0;
        case WM_COMMAND:
            switch (LOWORD(wparam)) {
                case 1001:
                    open_window();
                    return 0;
                case 1002:
                    set_notifications_enabled(!load_config().notifications_enabled);
                    if (status_window_ != nullptr) {
                        status_window_->handle_toggle_notifications();
                    }
                    return 0;
                case 1003:
                    stop_.store(true);
                    PostQuitMessage(0);
                    return 0;
                default:
                    break;
            }
            break;
        case kMsgPeerTransition: {
            std::unique_ptr<PeerTransitionEvent> payload(reinterpret_cast<PeerTransitionEvent*>(lparam));
            toast_.show_transition(*payload);
            return 0;
        }
        case kMsgSnapshot: {
            std::unique_ptr<MonitorSnapshot> payload(reinterpret_cast<MonitorSnapshot*>(lparam));
            if (status_window_ != nullptr) {
                status_window_->handle_snapshot(*payload);
            }
            return 0;
        }
        case kMsgOpenWindow:
            open_window();
            return 0;
        case kMsgToggleNotifications:
            set_notifications_enabled(!load_config().notifications_enabled);
            if (status_window_ != nullptr) {
                status_window_->handle_toggle_notifications();
            }
            return 0;
        case kMsgQuitApp:
        case WM_CLOSE:
            stop_.store(true);
            PostQuitMessage(0);
            return 0;
        case kMsgLogLine: {
            std::unique_ptr<std::string> payload(reinterpret_cast<std::string*>(lparam));
            (void)payload;
            return 0;
        }
        case WM_DESTROY:
            stop_.store(true);
            PostQuitMessage(0);
            return 0;
        default:
            break;
    }
    return DefWindowProcW(message_window_, message, wparam, lparam);
}

bool AppController::create_message_window() {
    WNDCLASSW wc{};
    wc.lpfnWndProc = &AppController::WndProc;
    wc.hInstance = instance_;
    wc.lpszClassName = kControllerClassName;
    RegisterClassW(&wc);

    message_window_ = CreateWindowExW(
        0,
        kControllerClassName,
        L"Network Monitor Controller",
        0,
        0,
        0,
        0,
        0,
        HWND_MESSAGE,
        nullptr,
        instance_,
        this);
    return message_window_ != nullptr;
}

void AppController::start_monitor() {
    stop_.store(false);
    monitor_thread_ = std::thread([this]() { run_monitor_loop(stop_, this); });
}

void AppController::stop_monitor() {
    stop_.store(true);
    if (monitor_thread_.joinable()) {
        monitor_thread_.join();
    }
}

void AppController::open_window() {
    if (status_window_ != nullptr) {
        status_window_->show();
    }
}

}  // namespace nm
