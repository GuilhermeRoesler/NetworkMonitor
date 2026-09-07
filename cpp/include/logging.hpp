#pragma once

#include <cstdint>
#include <filesystem>
#include <string>

namespace nm {

namespace fs = std::filesystem;

constexpr std::uintmax_t kLogMaxBytes = 5ull * 1024ull * 1024ull;
constexpr int kLogBackupCount = 2;

void set_console_logging_enabled(bool enabled);
void log_message(const std::string& message);

/// Rotaciona `path` quando o tamanho atinge `max_bytes` (mesma convenção do RotatingFileHandler).
void rotate_log_file_if_needed(const fs::path& path, std::uintmax_t max_bytes, int backup_count);

}  // namespace nm
