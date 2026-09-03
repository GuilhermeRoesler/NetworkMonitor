#pragma once

#include <windows.h>

#include <string>

namespace nm {

std::wstring widen(const std::string& value);
std::string narrow(const std::wstring& value);
std::wstring load_utf8_file_string(const std::wstring& value);
std::wstring trim_copy(std::wstring value);
std::wstring escape_xml(const std::wstring& value);
std::wstring current_time_hhmmss();
void post_message_if_window(HWND hwnd, UINT message, WPARAM wparam = 0, LPARAM lparam = 0);

}  // namespace nm
