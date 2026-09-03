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
    explicit StatusWindow(HWND owner);

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
    HFONT title_font_{nullptr};
    HFONT text_font_{nullptr};
    HFONT summary_font_{nullptr};
    MonitorSnapshot snapshot_{};
    bool has_snapshot_{false};
    bool show_hidden_{false};
    bool drag_tracking_{false};
    bool drag_active_{false};
    POINT drag_start_{};
    std::string drag_ip_;
    std::string context_ip_;

    static constexpr UINT_PTR kRefreshTimerId = 1001;
    static constexpr int kRefreshMs = 3000;

    static LRESULT CALLBACK WndProc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam);
    LRESULT handle_message(UINT message, WPARAM wparam, LPARAM lparam);
    void build_controls();
    void refresh_view();
    void refresh_labels();
    std::vector<DisplayPeer> peers_to_display() const;
    std::optional<std::string> selected_ip() const;
    void set_selected_ip(const std::string& ip);
    void toggle_notifications();
    void refresh_now();
    void show_context_menu(POINT screen_point);
    void rename_selected();
    void move_selected_to_top();
    void hide_selected();
    void show_selected();
    void mute_selected();
    void unmute_selected();
    void update_drag_target(LPARAM lparam);
    void begin_drag_if_needed(LPARAM lparam);
    void finish_drag(LPARAM lparam);
    void clear_drop_highlight();
};

}  // namespace nm
