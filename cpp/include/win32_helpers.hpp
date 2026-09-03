#pragma once

#include <windows.h>

#include <string>
#include <utility>

namespace nm {

std::wstring widen(const std::string& value);
std::string narrow(const std::wstring& value);
std::wstring load_utf8_file_string(const std::wstring& value);
std::wstring trim_copy(std::wstring value);
std::wstring escape_xml(const std::wstring& value);
std::wstring current_time_hhmmss();
void post_message_if_window(HWND hwnd, UINT message, WPARAM wparam = 0, LPARAM lparam = 0);

/// Tamanhos do ICO em assets/_generate_icon.py.
inline constexpr int kIcoSizes[] = {16, 24, 32, 48, 64, 128, 256};
inline constexpr int kTrayIconSize = 64;

int snap_icon_size(int pixels);
int win_effective_dpi();
/// (pequeno, grande). Mínimo 32/64 — o frame 16px some quando o Windows amplia.
std::pair<int, int> window_icon_sizes(int dpi = 0);
HICON load_file_icon(const std::wstring& path, int size);

}  // namespace nm
