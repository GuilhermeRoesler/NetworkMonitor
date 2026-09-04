#include "paths.hpp"

#include <windows.h>

#include <string>
#include <vector>

namespace nm {
namespace {

constexpr const wchar_t* kDataFolderName = L"NetworkMonitor";

std::optional<fs::path> g_app_dir_override;

fs::path exe_dir() {
    wchar_t buffer[MAX_PATH]{};
    const DWORD len = GetModuleFileNameW(nullptr, buffer, MAX_PATH);
    if (len == 0 || len >= MAX_PATH) {
        return fs::current_path();
    }
    return fs::path(buffer).parent_path();
}

bool looks_like_repo_root(const fs::path& dir) {
    return fs::exists(dir / "python" / "main.py") && fs::exists(dir / "cpp" / "CMakeLists.txt");
}

fs::path env_dir(const wchar_t* name) {
    const DWORD needed = GetEnvironmentVariableW(name, nullptr, 0);
    if (needed == 0) {
        return {};
    }
    std::wstring buffer(needed, L'\0');
    const DWORD written = GetEnvironmentVariableW(name, buffer.data(), needed);
    if (written == 0 || written >= needed) {
        return {};
    }
    buffer.resize(written);
    return fs::path(buffer);
}

fs::path local_app_data_dir() {
    fs::path local = env_dir(L"LOCALAPPDATA");
    if (!local.empty()) {
        return local;
    }
    fs::path profile = env_dir(L"USERPROFILE");
    if (!profile.empty()) {
        return profile / "AppData" / "Local";
    }
    return {};
}

}  // namespace

void set_app_dir_override(std::optional<fs::path> dir) { g_app_dir_override = std::move(dir); }

fs::path resolve_app_dir() {
    if (g_app_dir_override) {
        return *g_app_dir_override;
    }

    fs::path start = exe_dir();
    std::vector<fs::path> candidates = {
        start,
        start / ".." / ".." / "..",  // cpp/build/bin -> repo
        start / ".." / ".." / ".." / "..",
        fs::current_path(),
    };

    for (const auto& candidate : candidates) {
        std::error_code ec;
        const fs::path normalized = fs::weakly_canonical(candidate, ec);
        const fs::path& dir = ec ? candidate : normalized;
        if (looks_like_repo_root(dir)) {
            return dir;
        }
    }

    return start;
}

fs::path resolve_data_dir() {
    if (g_app_dir_override) {
        return *g_app_dir_override;
    }

    const fs::path app = resolve_app_dir();
    if (looks_like_repo_root(app)) {
        return app;
    }

    const fs::path start = exe_dir();
    if (fs::exists(start / "peers.json")) {
        return start;
    }

    const fs::path local = local_app_data_dir();
    if (!local.empty()) {
        return local / kDataFolderName;
    }
    return start;
}

void ensure_data_dir() {
    std::error_code ec;
    fs::create_directories(resolve_data_dir(), ec);
}

fs::path config_path() { return resolve_data_dir() / "peers.json"; }
fs::path state_path() { return resolve_data_dir() / "state.json"; }
fs::path history_path() { return resolve_data_dir() / "history.json"; }
fs::path log_path() { return resolve_data_dir() / "monitor.log"; }
fs::path assets_dir() { return resolve_app_dir() / "assets"; }
fs::path icon_ico_path() { return assets_dir() / "icon.ico"; }
fs::path icon_png_path() { return assets_dir() / "icon.png"; }

}  // namespace nm
