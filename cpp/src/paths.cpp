#include "paths.hpp"

#include <windows.h>

#include <vector>

namespace nm {
namespace {

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
        if (fs::exists(dir / "peers.json")) {
            return dir;
        }
    }

    // Fallback: pasta do executável (release empacotado)
    return start;
}

fs::path config_path() { return resolve_app_dir() / "peers.json"; }
fs::path state_path() { return resolve_app_dir() / "state.json"; }
fs::path log_path() { return resolve_app_dir() / "monitor.log"; }

}  // namespace nm
