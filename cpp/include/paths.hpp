#pragma once

#include <filesystem>
#include <optional>
#include <string>

namespace nm {

namespace fs = std::filesystem;

/// Quando definido, config/state/log usam este diretório (útil em testes).
void set_app_dir_override(std::optional<fs::path> dir);

fs::path resolve_app_dir();
fs::path config_path();
fs::path state_path();
fs::path log_path();
fs::path assets_dir();
fs::path icon_ico_path();
fs::path icon_png_path();

}  // namespace nm
