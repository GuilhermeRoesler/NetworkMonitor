#include "status_window.hpp"

#include "config.hpp"
#include "network.hpp"
#include "paths.hpp"
#include "win32_helpers.hpp"

#include <commctrl.h>
#include <uxtheme.h>
#include <windowsx.h>

#include <memory>

namespace nm {
namespace {

constexpr wchar_t kStatusWindowClassName[] = L"NetworkMonitorStatusWindow";

constexpr int kIdSummary = 2001;
constexpr int kIdLocalIp = 2002;
constexpr int kIdUpdated = 2003;
constexpr int kIdRefresh = 2004;
constexpr int kIdNotifications = 2005;
constexpr int kIdShowHidden = 2006;
constexpr int kIdList = 2007;
constexpr int kIdTitle = 2008;
constexpr int kIdFooter = 2009;

constexpr int kMenuRename = 3001;
constexpr int kMenuMoveTop = 3002;
constexpr int kMenuHide = 3003;
constexpr int kMenuShow = 3004;
constexpr int kMenuMute = 3005;
constexpr int kMenuUnmute = 3006;

const COLORREF kColorBg = RGB(246, 248, 250);
const COLORREF kColorCard = RGB(255, 255, 255);
const COLORREF kColorText = RGB(36, 41, 47);
const COLORREF kColorMuted = RGB(87, 96, 106);
const COLORREF kColorOnline = RGB(26, 127, 55);
const COLORREF kColorOffline = RGB(207, 34, 46);
const COLORREF kColorUnknown = RGB(110, 119, 129);
const COLORREF kColorHidden = RGB(139, 148, 158);
const COLORREF kColorMutedState = RGB(154, 103, 0);
const COLORREF kColorDrop = RGB(219, 234, 254);
const COLORREF kColorStripe = RGB(251, 252, 253);
const wchar_t kFooterHint[] =
    L"Arraste para reordenar · Duplo clique/F2 renomeia · Delete oculta · Clique direito: ocultar ou silenciar";
const wchar_t kFooterDragging[] = L"Reordenando: solte sobre outro peer ou abaixo da lista para mover ao final";

std::wstring status_text_for_peer(const Peer& peer, const StateMap& state) {
    if (peer.hidden) {
        return L"Oculto";
    }
    const auto it = state.find(peer.ip);
    if (it == state.end()) {
        return L"Desconhecido";
    }
    return it->second ? L"Online" : L"Offline";
}

void autosize_columns(HWND list) {
    if (list == nullptr) {
        return;
    }
    RECT rect{};
    GetClientRect(list, &rect);
    const int total = rect.right - rect.left;
    const int ip_width = 170;
    const int status_width = 120;
    const int name_width = (total > (ip_width + status_width + 40)) ? total - ip_width - status_width - 8 : 240;
    ListView_SetColumnWidth(list, 0, name_width);
    ListView_SetColumnWidth(list, 1, ip_width);
    ListView_SetColumnWidth(list, 2, status_width);
}

}  // namespace

StatusWindow::StatusWindow(HWND owner) : owner_(owner) {}

bool StatusWindow::create(HINSTANCE instance) {
    instance_ = instance;
    INITCOMMONCONTROLSEX icc{};
    icc.dwSize = sizeof(icc);
    icc.dwICC = ICC_LISTVIEW_CLASSES;
    InitCommonControlsEx(&icc);

    WNDCLASSW wc{};
    wc.lpfnWndProc = &StatusWindow::WndProc;
    wc.hInstance = instance_;
    wc.hIcon = static_cast<HICON>(LoadImageW(nullptr, icon_ico_path().c_str(), IMAGE_ICON, 32, 32, LR_LOADFROMFILE));
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.hbrBackground = CreateSolidBrush(kColorBg);
    wc.lpszClassName = kStatusWindowClassName;
    RegisterClassW(&wc);
    if (wc.hIcon != nullptr) {
        DestroyIcon(wc.hIcon);
    }

    hwnd_ = CreateWindowExW(
        0,
        kStatusWindowClassName,
        L"Network Monitor",
        WS_OVERLAPPEDWINDOW,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        640,
        520,
        nullptr,
        nullptr,
        instance_,
        this);
    return hwnd_ != nullptr;
}

void StatusWindow::show() {
    if (hwnd_ == nullptr) {
        return;
    }
    ShowWindow(hwnd_, SW_SHOW);
    SetForegroundWindow(hwnd_);
}

void StatusWindow::close() {
    if (hwnd_ != nullptr && IsWindow(hwnd_)) {
        DestroyWindow(hwnd_);
        hwnd_ = nullptr;
    }
}

bool StatusWindow::is_window(HWND hwnd) const { return hwnd_ == hwnd; }

HWND StatusWindow::hwnd() const { return hwnd_; }

void StatusWindow::handle_snapshot(const MonitorSnapshot& snapshot) {
    snapshot_ = snapshot;
    has_snapshot_ = true;
    if (hwnd_ != nullptr) {
        refresh_view();
    }
}

void StatusWindow::handle_toggle_notifications() {
    if (hwnd_ != nullptr) {
        refresh_view();
    }
}

LRESULT CALLBACK StatusWindow::WndProc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
    if (message == WM_NCCREATE) {
        auto* create = reinterpret_cast<CREATESTRUCTW*>(lparam);
        auto* self = static_cast<StatusWindow*>(create->lpCreateParams);
        if (self != nullptr) {
            self->hwnd_ = hwnd;
        }
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
        return TRUE;
    }

    auto* self = reinterpret_cast<StatusWindow*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
    if (self != nullptr) {
        return self->handle_message(message, wparam, lparam);
    }
    return DefWindowProcW(hwnd, message, wparam, lparam);
}

LRESULT StatusWindow::handle_message(UINT message, WPARAM wparam, LPARAM lparam) {
    switch (message) {
        case WM_CREATE:
            build_controls();
            SetWindowPos(hwnd_, nullptr, 0, 0, 700, 560, SWP_NOMOVE | SWP_NOZORDER);
            SetTimer(hwnd_, kRefreshTimerId, kRefreshMs, nullptr);
            return 0;
        case WM_SIZE: {
            const int width = LOWORD(lparam);
            const int height = HIWORD(lparam);
            MoveWindow(title_, 16, 14, width - 32, 28, TRUE);
            MoveWindow(local_ip_, 16, 44, width - 32, 20, TRUE);
            MoveWindow(summary_, 16, 68, width - 32, 22, TRUE);
            MoveWindow(button_refresh_, 16, 104, 124, 30, TRUE);
            MoveWindow(check_notifications_, 152, 108, 132, 24, TRUE);
            MoveWindow(check_hidden_, 298, 108, 144, 24, TRUE);
            MoveWindow(updated_, width - 190, 106, 174, 24, TRUE);
            MoveWindow(list_, 16, 144, width - 32, height - 196, TRUE);
            MoveWindow(footer_, 16, height - 42, width - 32, 20, TRUE);
            autosize_columns(list_);
            return 0;
        }
        case WM_TIMER:
            if (wparam == kRefreshTimerId) {
                refresh_now();
            }
            return 0;
        case WM_COMMAND:
            switch (LOWORD(wparam)) {
                case kIdRefresh:
                    refresh_now();
                    return 0;
                case kIdNotifications:
                    toggle_notifications();
                    return 0;
                case kIdShowHidden:
                    show_hidden_ = (Button_GetCheck(check_hidden_) == BST_CHECKED);
                    refresh_view();
                    return 0;
                case kMenuRename:
                    rename_selected();
                    return 0;
                case kMenuMoveTop:
                    move_selected_to_top();
                    return 0;
                case kMenuHide:
                    hide_selected();
                    return 0;
                case kMenuShow:
                    show_selected();
                    return 0;
                case kMenuMute:
                    mute_selected();
                    return 0;
                case kMenuUnmute:
                    unmute_selected();
                    return 0;
                default:
                    break;
            }
            break;
        case WM_CONTEXTMENU:
            if (reinterpret_cast<HWND>(wparam) == list_) {
                POINT pt{GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam)};
                if (pt.x == -1 && pt.y == -1) {
                    RECT rect{};
                    GetWindowRect(list_, &rect);
                    pt.x = rect.left + 10;
                    pt.y = rect.top + 10;
                }
                show_context_menu(pt);
                return 0;
            }
            break;
        case WM_NOTIFY:
            if (reinterpret_cast<LPNMHDR>(lparam)->hwndFrom == list_) {
                const auto code = reinterpret_cast<LPNMHDR>(lparam)->code;
                if (code == NM_CUSTOMDRAW) {
                    auto* draw = reinterpret_cast<LPNMLVCUSTOMDRAW>(lparam);
                    if (draw->nmcd.dwDrawStage == CDDS_PREPAINT) {
                        return CDRF_NOTIFYITEMDRAW | CDRF_NOTIFYSUBITEMDRAW;
                    }
                    if (draw->nmcd.dwDrawStage == (CDDS_ITEMPREPAINT | CDDS_SUBITEM)) {
                        wchar_t ip_buffer[256]{};
                        wchar_t status_buffer[64]{};
                        ListView_GetItemText(list_, static_cast<int>(draw->nmcd.dwItemSpec), 1, ip_buffer, 255);
                        ListView_GetItemText(list_, static_cast<int>(draw->nmcd.dwItemSpec), 2, status_buffer, 63);
                        const std::string ip = narrow(ip_buffer);
                        const auto config = load_config();
                        const auto peers = config.all_peers();
                        const auto peer_it =
                            std::find_if(peers.begin(), peers.end(), [&](const Peer& peer) { return peer.ip == ip; });
                        const std::wstring status = status_buffer;
                        const bool selected = (draw->nmcd.uItemState & CDIS_SELECTED) != 0;
                        if (selected) {
                            draw->clrTextBk = GetSysColor(COLOR_HIGHLIGHT);
                            draw->clrText = RGB(255, 255, 255);
                        } else {
                            draw->clrTextBk = (draw->nmcd.dwItemSpec % 2 == 0) ? kColorCard : kColorStripe;
                            if (peer_it != peers.end() && peer_it->hidden) {
                                draw->clrText = kColorHidden;
                            } else if (peer_it != peers.end() && peer_it->muted && draw->iSubItem == 0) {
                                draw->clrText = kColorMutedState;
                            } else if (status == L"Online") {
                                draw->clrText = kColorOnline;
                            } else if (status == L"Offline") {
                                draw->clrText = kColorOffline;
                            } else if (status == L"Oculto") {
                                draw->clrText = kColorHidden;
                            } else if (status == L"Silenciado") {
                                draw->clrText = kColorMutedState;
                            } else {
                                draw->clrText = kColorUnknown;
                            }
                        }
                        return CDRF_NEWFONT;
                    }
                }
                if (code == NM_DBLCLK) {
                    rename_selected();
                    return 0;
                }
                if (code == LVN_BEGINDRAG) {
                    auto* drag = reinterpret_cast<NM_LISTVIEW*>(lparam);
                    wchar_t ip_buffer[256]{};
                    ListView_GetItemText(list_, drag->iItem, 1, ip_buffer, 255);
                    drag_ip_ = narrow(ip_buffer);
                    drag_active_ = !drag_ip_.empty();
                    if (drag_active_) {
                        SetCapture(hwnd_);
                        SetCursor(LoadCursorW(nullptr, IDC_HAND));
                        SetWindowTextW(footer_, kFooterDragging);
                    }
                    return 0;
                }
                if (code == NM_RCLICK) {
                    POINT pt{};
                    GetCursorPos(&pt);
                    show_context_menu(pt);
                    return 0;
                }
                if (code == LVN_KEYDOWN) {
                    auto* key = reinterpret_cast<NMLVKEYDOWN*>(lparam);
                    if (key->wVKey == VK_F2) {
                        rename_selected();
                        return 0;
                    }
                    if (key->wVKey == VK_DELETE) {
                        hide_selected();
                        return 0;
                    }
                }
                if (code == LVN_BEGINLABELEDITW) {
                    return 0;
                }
                if (code == LVN_ENDLABELEDITW) {
                    auto* edit = reinterpret_cast<NMLVDISPINFOW*>(lparam);
                    if (edit->item.pszText != nullptr) {
                        const int index = edit->item.iItem;
                        wchar_t ip_buffer[256]{};
                        ListView_GetItemText(list_, index, 1, ip_buffer, 255);
                        if (update_peer_name(narrow(ip_buffer), narrow(trim_copy(edit->item.pszText)))) {
                            refresh_now();
                            return TRUE;
                        }
                    }
                    return FALSE;
                }
            }
            break;
        case WM_CTLCOLORSTATIC: {
            const HWND control = reinterpret_cast<HWND>(lparam);
            HDC dc = reinterpret_cast<HDC>(wparam);
            SetBkMode(dc, TRANSPARENT);
            SetTextColor(dc, control == summary_ || control == title_ ? kColorText : kColorMuted);
            static HBRUSH background = CreateSolidBrush(kColorBg);
            return reinterpret_cast<INT_PTR>(background);
        }
        case WM_CTLCOLOREDIT: {
            HDC dc = reinterpret_cast<HDC>(wparam);
            SetBkColor(dc, kColorCard);
            SetTextColor(dc, kColorText);
            static HBRUSH card = CreateSolidBrush(kColorCard);
            return reinterpret_cast<INT_PTR>(card);
        }
        case WM_MOUSEMOVE:
            if (drag_active_) {
                update_drag_target(lparam);
                return 0;
            }
            break;
        case WM_LBUTTONUP:
            if (drag_active_) {
                finish_drag(lparam);
                return 0;
            }
            break;
        case WM_CLOSE:
            ShowWindow(hwnd_, SW_HIDE);
            return 0;
        case WM_DESTROY:
            KillTimer(hwnd_, kRefreshTimerId);
            if (title_font_ != nullptr) {
                DeleteObject(title_font_);
                title_font_ = nullptr;
            }
            if (text_font_ != nullptr) {
                DeleteObject(text_font_);
                text_font_ = nullptr;
            }
            if (summary_font_ != nullptr) {
                DeleteObject(summary_font_);
                summary_font_ = nullptr;
            }
            hwnd_ = nullptr;
            return 0;
        default:
            break;
    }
    return DefWindowProcW(hwnd_, message, wparam, lparam);
}

void StatusWindow::build_controls() {
    title_font_ = CreateFontW(22, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS,
                              CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    text_font_ = CreateFontW(18, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS,
                             CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    summary_font_ = CreateFontW(18, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS,
                                CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");

    title_ = CreateWindowW(L"STATIC", L"Network Monitor", WS_CHILD | WS_VISIBLE, 0, 0, 0, 0, hwnd_,
                           reinterpret_cast<HMENU>(static_cast<INT_PTR>(kIdTitle)), instance_, nullptr);
    local_ip_ = CreateWindowW(L"STATIC", L"IP local: ...", WS_CHILD | WS_VISIBLE, 0, 0, 0, 0, hwnd_,
                              reinterpret_cast<HMENU>(static_cast<INT_PTR>(kIdLocalIp)), instance_, nullptr);
    summary_ = CreateWindowW(L"STATIC", L"Carregando...", WS_CHILD | WS_VISIBLE, 0, 0, 0, 0, hwnd_,
                             reinterpret_cast<HMENU>(static_cast<INT_PTR>(kIdSummary)), instance_, nullptr);
    button_refresh_ = CreateWindowW(L"BUTTON", L"Atualizar agora", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 0, 0, 0, 0,
                                    hwnd_, reinterpret_cast<HMENU>(static_cast<INT_PTR>(kIdRefresh)), instance_, nullptr);
    check_notifications_ =
        CreateWindowW(L"BUTTON", L"Notificações", WS_CHILD | WS_VISIBLE | BS_AUTOCHECKBOX, 0, 0, 0, 0, hwnd_,
                      reinterpret_cast<HMENU>(static_cast<INT_PTR>(kIdNotifications)), instance_, nullptr);
    check_hidden_ =
        CreateWindowW(L"BUTTON", L"Mostrar ocultos", WS_CHILD | WS_VISIBLE | BS_AUTOCHECKBOX, 0, 0, 0, 0, hwnd_,
                      reinterpret_cast<HMENU>(static_cast<INT_PTR>(kIdShowHidden)), instance_, nullptr);
    updated_ = CreateWindowW(L"STATIC", L"", WS_CHILD | WS_VISIBLE | SS_RIGHT, 0, 0, 0, 0, hwnd_,
                             reinterpret_cast<HMENU>(static_cast<INT_PTR>(kIdUpdated)), instance_, nullptr);
    footer_ = CreateWindowW(
        L"STATIC",
        kFooterHint,
        WS_CHILD | WS_VISIBLE,
        0,
        0,
        0,
        0,
        hwnd_,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kIdFooter)),
        instance_,
        nullptr);

    list_ = CreateWindowW(WC_LISTVIEWW, L"", WS_CHILD | WS_VISIBLE | LVS_REPORT | LVS_SINGLESEL | LVS_EDITLABELS, 0, 0,
                          0, 0, hwnd_, reinterpret_cast<HMENU>(static_cast<INT_PTR>(kIdList)), instance_, nullptr);
    ListView_SetExtendedListViewStyle(
        list_,
        LVS_EX_FULLROWSELECT | LVS_EX_DOUBLEBUFFER | LVS_EX_INFOTIP | LVS_EX_LABELTIP | LVS_EX_BORDERSELECT |
            LVS_EX_GRIDLINES);
    SetWindowTheme(list_, L"Explorer", nullptr);

    LVCOLUMNW column{};
    column.mask = LVCF_TEXT | LVCF_WIDTH | LVCF_SUBITEM;
    column.cx = 260;
    column.pszText = const_cast<LPWSTR>(L"Nome");
    ListView_InsertColumn(list_, 0, &column);
    column.cx = 160;
    column.pszText = const_cast<LPWSTR>(L"IP");
    ListView_InsertColumn(list_, 1, &column);
    column.cx = 120;
    column.pszText = const_cast<LPWSTR>(L"Status");
    ListView_InsertColumn(list_, 2, &column);
    autosize_columns(list_);

    for (HWND control : {title_, local_ip_, summary_, updated_, footer_, button_refresh_, check_notifications_, check_hidden_}) {
        SendMessageW(control, WM_SETFONT, reinterpret_cast<WPARAM>(text_font_), TRUE);
    }
    SendMessageW(title_, WM_SETFONT, reinterpret_cast<WPARAM>(title_font_), TRUE);
    SendMessageW(summary_, WM_SETFONT, reinterpret_cast<WPARAM>(summary_font_), TRUE);
    SendMessageW(list_, WM_SETFONT, reinterpret_cast<WPARAM>(text_font_), TRUE);
}

void StatusWindow::refresh_view() {
    if (hwnd_ == nullptr || list_ == nullptr) {
        return;
    }

    const auto selected = selected_ip();
    ListView_DeleteAllItems(list_);

    const auto peers = peers_to_display();
    int row = 0;
    for (const auto& entry : peers) {
        LVITEMW item{};
        item.mask = LVIF_TEXT | LVIF_PARAM;
        item.iItem = row;
        item.iSubItem = 0;
        item.pszText = const_cast<LPWSTR>(entry.display_name.c_str());
        item.lParam = static_cast<LPARAM>(row);
        ListView_InsertItem(list_, &item);
        ListView_SetItemText(list_, row, 1, const_cast<LPWSTR>(widen(entry.peer.ip).c_str()));
        ListView_SetItemText(list_, row, 2, const_cast<LPWSTR>(entry.status_text.c_str()));
        ++row;
    }

    if (selected.has_value()) {
        set_selected_ip(*selected);
    }
    autosize_columns(list_);
    refresh_labels();
}

void StatusWindow::refresh_labels() {
    std::wstring local_ip_text;
    if (!snapshot_.radmin_ip.empty()) {
        local_ip_text += L"Radmin: " + widen(snapshot_.radmin_ip);
    }
    if (!snapshot_.lan_ip.empty()) {
        if (!local_ip_text.empty()) {
            local_ip_text += L" · ";
        }
        local_ip_text += L"LAN: " + widen(snapshot_.lan_ip);
    }
    if (local_ip_text.empty()) {
        local_ip_text = L"Nenhuma rede detectada";
    }
    SetWindowTextW(local_ip_, local_ip_text.c_str());

    std::wstring summary;
    if (snapshot_.visible_count == 0 && snapshot_.hidden_count == 0) {
        summary = L"Nenhum peer configurado em peers.json";
    } else {
        int offline = snapshot_.visible_count - snapshot_.online_count;
        summary = std::to_wstring(snapshot_.online_count) + L" online · " + std::to_wstring(offline) + L" offline · " +
                  std::to_wstring(snapshot_.visible_count) + L" visíveis";
        if (snapshot_.hidden_count > 0) {
            summary += L" · " + std::to_wstring(snapshot_.hidden_count) + L" ocultos";
        }
    }
    if (!snapshot_.notifications_enabled) {
        summary += L" · notificações pausadas";
    }
    SetWindowTextW(summary_, summary.c_str());
    Button_SetCheck(check_notifications_, snapshot_.notifications_enabled ? BST_CHECKED : BST_UNCHECKED);
    Button_SetCheck(check_hidden_, show_hidden_ ? BST_CHECKED : BST_UNCHECKED);
    const std::wstring updated = L"Atualizado às " + current_time_hhmmss();
    SetWindowTextW(updated_, updated.c_str());
}

std::vector<StatusWindow::DisplayPeer> StatusWindow::peers_to_display() const {
    std::vector<DisplayPeer> result;
    const auto config = load_config();
    const auto peers = show_hidden_ ? config.all_peers() : config.visible_peers();
    for (const auto& peer : peers) {
        DisplayPeer entry;
        entry.peer = peer;
        entry.status_text = status_text_for_peer(peer, snapshot_.state);
        entry.display_name = widen(peer.name);
        if (peer.muted && !peer.hidden) {
            entry.display_name = L"\xD83D\xDD07 " + entry.display_name;
        }
        result.push_back(std::move(entry));
    }
    return result;
}

std::optional<std::string> StatusWindow::selected_ip() const {
    const int index = ListView_GetNextItem(list_, -1, LVNI_SELECTED);
    if (index < 0) {
        return std::nullopt;
    }
    wchar_t buffer[256]{};
    ListView_GetItemText(list_, index, 1, buffer, 255);
    return narrow(buffer);
}

void StatusWindow::set_selected_ip(const std::string& ip) {
    const int count = ListView_GetItemCount(list_);
    for (int i = 0; i < count; ++i) {
        wchar_t buffer[256]{};
        ListView_GetItemText(list_, i, 1, buffer, 255);
        if (narrow(buffer) == ip) {
            ListView_SetItemState(list_, i, LVIS_SELECTED | LVIS_FOCUSED, LVIS_SELECTED | LVIS_FOCUSED);
            ListView_EnsureVisible(list_, i, FALSE);
            return;
        }
    }
}

void StatusWindow::toggle_notifications() {
    set_notifications_enabled(Button_GetCheck(check_notifications_) == BST_CHECKED);
    refresh_now();
}

void StatusWindow::refresh_now() {
    if (hwnd_ == nullptr) {
        return;
    }
    const auto config = load_config();
    snapshot_.peers = config.all_peers();
    snapshot_.state = load_state();
    snapshot_.radmin_ip = get_radmin_ip().value_or("");
    snapshot_.lan_ip = get_lan_ip().value_or("");
    snapshot_.visible_count = static_cast<int>(config.visible_peers().size());
    snapshot_.hidden_count = static_cast<int>(config.hidden_peers().size());
    snapshot_.notifications_enabled = config.notifications_enabled;
    snapshot_.online_count = 0;
    for (const auto& peer : config.visible_peers()) {
        const auto it = snapshot_.state.find(peer.ip);
        if (it != snapshot_.state.end() && it->second) {
            ++snapshot_.online_count;
        }
    }
    refresh_view();
}

void StatusWindow::show_context_menu(POINT screen_point) {
    const auto ip = selected_ip();
    if (!ip.has_value()) {
        return;
    }
    context_ip_ = *ip;

    const auto config = load_config();
    const auto peers = config.all_peers();
    const auto it = std::find_if(peers.begin(), peers.end(), [&](const Peer& peer) { return peer.ip == *ip; });
    if (it == peers.end()) {
        return;
    }

    HMENU menu = CreatePopupMenu();
    AppendMenuW(menu, MF_STRING, kMenuRename, L"Renomear");
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(menu, MF_STRING, kMenuMoveTop, L"Mover para o topo");
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    if (it->hidden) {
        AppendMenuW(menu, MF_STRING, kMenuShow, L"Mostrar dispositivo");
    } else {
        AppendMenuW(menu, MF_STRING, kMenuHide, L"Ocultar dispositivo");
        if (it->muted) {
            AppendMenuW(menu, MF_STRING, kMenuUnmute, L"Ativar notificações");
        } else {
            AppendMenuW(menu, MF_STRING, kMenuMute, L"Silenciar notificações");
        }
    }
    TrackPopupMenu(menu, TPM_LEFTALIGN | TPM_RIGHTBUTTON, screen_point.x, screen_point.y, 0, hwnd_, nullptr);
    DestroyMenu(menu);
}

void StatusWindow::rename_selected() {
    const int index = ListView_GetNextItem(list_, -1, LVNI_SELECTED);
    if (index >= 0) {
        ListView_EditLabel(list_, index);
    }
}

void StatusWindow::move_selected_to_top() {
    const auto ip = selected_ip();
    if (!ip.has_value()) {
        return;
    }
    const auto config = load_config();
    const auto peers = show_hidden_ ? config.all_peers() : config.visible_peers();
    for (const auto& peer : peers) {
        if (peer.ip != *ip) {
            if (move_peer(*ip, peer.ip)) {
                refresh_now();
            }
            return;
        }
    }
}

void StatusWindow::hide_selected() {
    const auto ip = selected_ip();
    if (ip.has_value() && set_peer_hidden(*ip, true)) {
        refresh_now();
    }
}

void StatusWindow::show_selected() {
    if (!context_ip_.empty() && set_peer_hidden(context_ip_, false)) {
        refresh_now();
    }
}

void StatusWindow::mute_selected() {
    const auto ip = selected_ip();
    if (ip.has_value() && set_peer_muted(*ip, true)) {
        refresh_now();
    }
}

void StatusWindow::unmute_selected() {
    if (!context_ip_.empty() && set_peer_muted(context_ip_, false)) {
        refresh_now();
    }
}

void StatusWindow::update_drag_target(LPARAM lparam) {
    if (list_ == nullptr) {
        return;
    }
    POINT point{GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam)};
    ScreenToClient(list_, &point);
    LVHITTESTINFO hit{};
    hit.pt = point;
    const int index = ListView_HitTest(list_, &hit);
    ListView_SetItemState(list_, -1, 0, LVIS_DROPHILITED);
    if (index >= 0) {
        ListView_SetItemState(list_, index, LVIS_DROPHILITED, LVIS_DROPHILITED);
    }
}

void StatusWindow::begin_drag_if_needed(LPARAM lparam) { (void)lparam; }

void StatusWindow::finish_drag(LPARAM lparam) {
    if (list_ == nullptr) {
        drag_active_ = false;
        drag_ip_.clear();
        return;
    }

    POINT point{GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam)};
    ScreenToClient(list_, &point);
    LVHITTESTINFO hit{};
    hit.pt = point;
    const int index = ListView_HitTest(list_, &hit);

    bool changed = false;
    if (index >= 0) {
        wchar_t ip_buffer[256]{};
        ListView_GetItemText(list_, index, 1, ip_buffer, 255);
        const std::string target_ip = narrow(ip_buffer);
        if (!drag_ip_.empty() && target_ip != drag_ip_) {
            changed = move_peer(drag_ip_, target_ip);
        }
    } else if (!drag_ip_.empty()) {
        changed = move_peer_to_end(drag_ip_);
    }

    ReleaseCapture();
    SetCursor(LoadCursorW(nullptr, IDC_ARROW));
    clear_drop_highlight();
    SetWindowTextW(footer_, kFooterHint);
    drag_active_ = false;
    drag_ip_.clear();
    if (changed) {
        refresh_now();
    }
}

void StatusWindow::clear_drop_highlight() {
    if (list_ != nullptr) {
        ListView_SetItemState(list_, -1, 0, LVIS_DROPHILITED);
    }
}

}  // namespace nm
