#include "app_controller.hpp"
#include "logging.hpp"
#include "monitor.hpp"
#include "paths.hpp"
#include "win32_helpers.hpp"

#include <windows.h>

#include <atomic>
#include <csignal>
#include <iostream>
#include <string>

namespace {

std::atomic_bool g_stop{false};

void on_signal(int) { g_stop.store(true); }

void ensure_console() { nm::set_console_logging_enabled(true); }

void hide_console_window() {
    if (HWND console = GetConsoleWindow()) {
        ShowWindow(console, SW_HIDE);
    }
}

void print_help() {
    std::cout
        << "Network Monitor (C++)\n"
        << "  (sem flags)   Bandeja + monitor\n"
        << "  --run         Executa apenas o monitor no console\n"
        << "  --gui         Monitor + painel Win32\n"
        << "  --status      Mostra status atual\n"
        << "  --scan        Escaneia sub-rede Radmin\n"
        << "  --scan-lan    Escaneia sub-rede LAN\n"
        << "  --scan-all    Escaneia Radmin e LAN\n"
        << "  --help        Esta ajuda\n\n"
        << "Config compartilhada: " << nm::config_path().string() << "\n";
}

}  // namespace

int main(int argc, char** argv) {
    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);

    std::string mode = "tray";
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--help" || arg == "-h") {
            ensure_console();
            print_help();
            return 0;
        }
        if (arg == "--run") {
            mode = "run";
        } else if (arg == "--gui") {
            mode = "gui";
        } else if (arg == "--status") {
            mode = "status";
        } else if (arg == "--scan") {
            mode = "scan";
        } else if (arg == "--scan-lan") {
            mode = "scan-lan";
        } else if (arg == "--scan-all") {
            mode = "scan-all";
        } else {
            ensure_console();
            std::cerr << "Flag desconhecida: " << arg << "\n";
            print_help();
            return 1;
        }
    }

    try {
        if (mode == "status") {
            ensure_console();
            nm::show_status();
            return 0;
        }
        if (mode == "scan") {
            ensure_console();
            return nm::scan_network("radmin") ? 0 : 1;
        }
        if (mode == "scan-lan") {
            ensure_console();
            return nm::scan_network("lan") ? 0 : 1;
        }
        if (mode == "scan-all") {
            ensure_console();
            nm::scan_network("radmin");
            std::cout << "\n";
            nm::scan_network("lan");
            return 0;
        }
        if (mode == "run") {
            ensure_console();
            nm::run_monitor_loop(g_stop);
            return 0;
        }

        hide_console_window();
        nm::AppController controller(mode == "tray", mode == "gui");
        return controller.run(GetModuleHandleW(nullptr), SW_SHOW);
    } catch (const std::exception& ex) {
        ensure_console();
        std::cerr << "Erro: " << ex.what() << "\n";
        return 1;
    }
}
