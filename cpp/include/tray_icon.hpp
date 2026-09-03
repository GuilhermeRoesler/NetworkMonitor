#pragma once

#include <windows.h>

namespace nm {

class TrayIcon {
public:
    TrayIcon() = default;
    ~TrayIcon();

    bool create(HWND owner);
    void destroy();
    void show_context_menu();

private:
    HWND owner_{nullptr};
    UINT callback_message_{WM_APP + 1};
    bool created_{false};
};

}  // namespace nm
