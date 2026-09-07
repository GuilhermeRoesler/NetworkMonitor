#include "logging.hpp"

#include "paths.hpp"

#include <fstream>
#include <iostream>
#include <mutex>
#include <system_error>

namespace nm {
namespace {

std::mutex g_log_mutex;
bool g_console_logging_enabled = false;

fs::path backup_path(const fs::path& path, int index) {
    return fs::path(path.string() + "." + std::to_string(index));
}

}  // namespace

void set_console_logging_enabled(bool enabled) {
    std::lock_guard lock(g_log_mutex);
    g_console_logging_enabled = enabled;
}

void rotate_log_file_if_needed(const fs::path& path, std::uintmax_t max_bytes, int backup_count) {
    if (max_bytes == 0 || backup_count < 0) {
        return;
    }

    std::error_code ec;
    if (!fs::exists(path, ec) || ec) {
        return;
    }
    const auto size = fs::file_size(path, ec);
    if (ec || size < max_bytes) {
        return;
    }

    if (backup_count == 0) {
        fs::remove(path, ec);
        return;
    }

    fs::remove(backup_path(path, backup_count), ec);
    for (int index = backup_count - 1; index >= 1; --index) {
        const fs::path src = backup_path(path, index);
        if (fs::exists(src, ec) && !ec) {
            fs::rename(src, backup_path(path, index + 1), ec);
        }
    }
    fs::rename(path, backup_path(path, 1), ec);
}

void log_message(const std::string& message) {
    std::lock_guard lock(g_log_mutex);

    ensure_data_dir();
    const fs::path path = log_path();
    rotate_log_file_if_needed(path, kLogMaxBytes, kLogBackupCount);

    std::ofstream out(path, std::ios::app | std::ios::binary);
    if (out) {
        out << message << "\n";
    }

    if (g_console_logging_enabled) {
        std::cout << message << std::endl;
    }
}

}  // namespace nm
