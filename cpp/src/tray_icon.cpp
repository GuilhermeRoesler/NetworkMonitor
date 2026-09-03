#include "tray_icon.hpp"

#include "config.hpp"
#include "paths.hpp"
#include "win32_helpers.hpp"

#include <shellapi.h>

namespace nm {
namespace {

constexpr UINT kTrayIconId = 1;

}  // namespace

TrayIcon::~TrayIcon() { destroy(); }

bool TrayIcon::create(HWND owner) {
    owner_ = owner;

    NOTIFYICONDATAW data{};
    data.cbSize = sizeof(data);
    data.hWnd = owner_;
    data.uID = kTrayIconId;
    data.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    data.uCallbackMessage = callback_message_;
    icon_ = load_file_icon(icon_ico_path().wstring(), kTrayIconSize);
    if (icon_ == nullptr) {
        icon_ = LoadIconW(nullptr, IDI_APPLICATION);
        owns_icon_ = false;
    } else {
        owns_icon_ = true;
    }
    data.hIcon = icon_;
    wcscpy_s(data.szTip, L"Network Monitor");

    created_ = Shell_NotifyIconW(NIM_ADD, &data) == TRUE;
    return created_;
}

void TrayIcon::destroy() {
    if (!created_ || owner_ == nullptr) {
        return;
    }
    NOTIFYICONDATAW data{};
    data.cbSize = sizeof(data);
    data.hWnd = owner_;
    data.uID = kTrayIconId;
    Shell_NotifyIconW(NIM_DELETE, &data);
    created_ = false;
    if (owns_icon_ && icon_ != nullptr) {
        DestroyIcon(icon_);
    }
    icon_ = nullptr;
    owns_icon_ = false;
}

void TrayIcon::show_context_menu() {
    if (!created_ || owner_ == nullptr) {
        return;
    }

    HMENU menu = CreatePopupMenu();
    AppendMenuW(menu, MF_STRING, 1001, L"Abrir painel");
    AppendMenuW(menu, MF_STRING, 1002, L"Notificações");
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(menu, MF_STRING, 1003, L"Encerrar");

    const auto config = load_config();
    CheckMenuItem(menu, 1002, MF_BYCOMMAND | (config.notifications_enabled ? MF_CHECKED : MF_UNCHECKED));

    POINT pt{};
    GetCursorPos(&pt);
    SetForegroundWindow(owner_);
    const UINT cmd = TrackPopupMenu(menu, TPM_RETURNCMD | TPM_BOTTOMALIGN | TPM_LEFTALIGN, pt.x, pt.y, 0, owner_, nullptr);
    DestroyMenu(menu);

    if (cmd != 0U) {
        PostMessageW(owner_, WM_COMMAND, MAKEWPARAM(cmd, 0), 0);
    }
}

}  // namespace nm
