#pragma once

#include <filesystem>
#include <optional>
#include <string>

namespace nm {

namespace fs = std::filesystem;

/// Quando definido, config/state/log (e assets em testes) usam este diretório.
void set_app_dir_override(std::optional<fs::path> dir);

/// Raiz do repo ou pasta do .exe (binários / assets).
fs::path resolve_app_dir();

/// Onde ficam peers.json, state.json, history.json e monitor.log (repo em dev; AppData se instalado).
fs::path resolve_data_dir();

/// Garante que resolve_data_dir() exista.
void ensure_data_dir();

fs::path config_path();
fs::path state_path();
fs::path history_path();
fs::path log_path();
fs::path assets_dir();
fs::path icon_ico_path();
fs::path icon_png_path();

}  // namespace nm
