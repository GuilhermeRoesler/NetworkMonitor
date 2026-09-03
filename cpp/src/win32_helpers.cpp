#include "win32_helpers.hpp"

#include <windows.h>

#include <algorithm>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <string>

namespace nm {

std::wstring widen(const std::string& value) {
    if (value.empty()) {
        return {};
    }
    const int size = MultiByteToWideChar(CP_UTF8, 0, value.c_str(), -1, nullptr, 0);
    if (size <= 1) {
        return {};
    }
    std::wstring result(static_cast<size_t>(size - 1), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, value.c_str(), -1, result.data(), size);
    return result;
}

std::string narrow(const std::wstring& value) {
    if (value.empty()) {
        return {};
    }
    const int size = WideCharToMultiByte(CP_UTF8, 0, value.c_str(), -1, nullptr, 0, nullptr, nullptr);
    if (size <= 1) {
        return {};
    }
    std::string result(static_cast<size_t>(size - 1), '\0');
    WideCharToMultiByte(CP_UTF8, 0, value.c_str(), -1, result.data(), size, nullptr, nullptr);
    return result;
}

std::wstring load_utf8_file_string(const std::wstring& value) { return value; }

std::wstring trim_copy(std::wstring value) {
    auto is_space = [](wchar_t ch) { return ch == L' ' || ch == L'\t' || ch == L'\r' || ch == L'\n'; };
    while (!value.empty() && is_space(value.front())) {
        value.erase(value.begin());
    }
    while (!value.empty() && is_space(value.back())) {
        value.pop_back();
    }
    return value;
}

std::wstring escape_xml(const std::wstring& value) {
    std::wstring result;
    result.reserve(value.size() + 16);
    for (wchar_t ch : value) {
        switch (ch) {
            case L'&':
                result += L"&amp;";
                break;
            case L'<':
                result += L"&lt;";
                break;
            case L'>':
                result += L"&gt;";
                break;
            case L'\"':
                result += L"&quot;";
                break;
            case L'\'':
                result += L"&apos;";
                break;
            default:
                result.push_back(ch);
                break;
        }
    }
    return result;
}

std::wstring current_time_hhmmss() {
    SYSTEMTIME st{};
    GetLocalTime(&st);
    wchar_t buffer[16]{};
    swprintf_s(buffer, L"%02u:%02u:%02u", st.wHour, st.wMinute, st.wSecond);
    return buffer;
}

void post_message_if_window(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
    if (hwnd != nullptr && IsWindow(hwnd)) {
        PostMessageW(hwnd, message, wparam, lparam);
    }
}

int snap_icon_size(int pixels) {
    pixels = (std::max)(kIcoSizes[0], pixels);
    for (int size : kIcoSizes) {
        if (size >= pixels) {
            return size;
        }
    }
    return kIcoSizes[sizeof(kIcoSizes) / sizeof(kIcoSizes[0]) - 1];
}

int win_effective_dpi() {
    UINT dpi_x = 96;
    UINT dpi_y = 96;
    const HMONITOR monitor = MonitorFromWindow(GetDesktopWindow(), MONITOR_DEFAULTTOPRIMARY);
    const HMODULE shcore = LoadLibraryW(L"Shcore.dll");
    if (shcore != nullptr) {
        using GetDpiForMonitorFn = HRESULT(WINAPI*)(HMONITOR, int, UINT*, UINT*);
        const auto get_dpi = reinterpret_cast<GetDpiForMonitorFn>(GetProcAddress(shcore, "GetDpiForMonitor"));
        if (get_dpi != nullptr && SUCCEEDED(get_dpi(monitor, 0, &dpi_x, &dpi_y)) && dpi_x != 0) {
            FreeLibrary(shcore);
            return static_cast<int>(dpi_x);
        }
        FreeLibrary(shcore);
    }
    return 96;
}

std::pair<int, int> window_icon_sizes(int dpi) {
    if (dpi <= 0) {
        dpi = win_effective_dpi();
    }
    const double scale = static_cast<double>(dpi) / 96.0;
    int small = snap_icon_size((std::max)(32, static_cast<int>(16 * scale + 0.5)));
    int big = snap_icon_size((std::max)(64, static_cast<int>(32 * scale + 0.5)));
    if (big <= small) {
        for (int size : kIcoSizes) {
            if (size > small) {
                big = size;
                break;
            }
        }
    }
    return {small, big};
}

HICON load_file_icon(const std::wstring& path, int size) {
    if (path.empty() || size <= 0) {
        return nullptr;
    }
    return static_cast<HICON>(
        LoadImageW(nullptr, path.c_str(), IMAGE_ICON, size, size, LR_LOADFROMFILE));
}

}  // namespace nm
