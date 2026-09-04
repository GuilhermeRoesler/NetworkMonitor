#pragma once

#include "config.hpp"
#include "monitor.hpp"

#include <windows.h>

#include <optional>
#include <string>
#include <vector>

namespace nm {

class StatusWindow {
public:
    explicit StatusWindow(HWND owner, bool close_hides);

    bool create(HINSTANCE instance);
    void show();
    void close();
    bool is_window(HWND hwnd) const;
    HWND hwnd() const;
    void handle_snapshot(const MonitorSnapshot& snapshot);
    void handle_toggle_notifications();

private:
    struct DisplayPeer {
        Peer peer;
        std::wstring display_name;
        std::wstring status_text;
    };

    HWND owner_{nullptr};
    HWND hwnd_{nullptr};
    HWND list_{nullptr};
    HWND title_{nullptr};
    HWND summary_{nullptr};
    HWND local_ip_{nullptr};
    HWND updated_{nullptr};
    HWND footer_{nullptr};
    HWND button_refresh_{nullptr};
    HWND check_notifications_{nullptr};
    HWND check_hidden_{nullptr};
    HINSTANCE instance_{nullptr};
    HICON window_icon_small_{nullptr};
    HICON window_icon_big_{nullptr};
    HFONT title_font_{nullptr};
    HFONT text_font_{nullptr};
    HFONT summary_font_{nullptr};
    MonitorSnapshot snapshot_{};
    bool has_snapshot_{false};
    bool show_hidden_{false};
    bool close_hides_{true};
    bool drag_active_{false};
    bool pending_refresh_{false};
    bool labeling_{false};
    std::string drag_ip_;
    std::string context_ip_;

    static constexpr UINT_PTR kRefreshTimerId = 1001;

    static LRESULT CALLBACK WndProc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam);
    LRESULT handle_message(UINT message, WPARAM wparam, LPARAM lparam);
    void build_controls();
    void refresh_view();
    void refresh_labels();
    bool should_defer_refresh() const;
    void request_refresh();
    std::vector<DisplayPeer> peers_to_display() const;
    std::optional<std::string> selected_ip() const;
    std::optional<std::string> action_ip() const;
    void set_selected_ip(const std::string& ip);
    void toggle_notifications();
    void refresh_now(bool force_network = false);
    void show_context_menu(POINT screen_point);
    void rename_selected();
    void move_selected_to_top();
    void hide_selected();
    void show_selected();
    void mute_selected();
    void unmute_selected();
    POINT map_to_list(LPARAM lparam) const;
    void update_drag_target(LPARAM lparam);
    void finish_drag(LPARAM lparam);
    void clear_drop_highlight();
    void cleanup_fonts_and_icon();
};

}  // namespace nm
