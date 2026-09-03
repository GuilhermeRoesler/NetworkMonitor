#pragma once

#include <filesystem>
#include <string>

namespace nm {

namespace fs = std::filesystem;

fs::path resolve_app_dir();
fs::path config_path();
fs::path state_path();
fs::path log_path();

}  // namespace nm
