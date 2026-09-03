#include "config.hpp"
#include "monitor.hpp"
#include "paths.hpp"

#include <atomic>
#include <csignal>
#include <cstring>
#include <iostream>
#include <string>

namespace {

std::atomic_bool g_stop{false};

void on_signal(int) { g_stop.store(true); }

void print_help() {
    std::cout
        << "Network Monitor (C++)\n"
        << "  (sem flags)   Loop de monitoramento no console\n"
        << "  --run         Idem\n"
        << "  --status      Mostra status atual\n"
        << "  --scan        Escaneia sub-rede Radmin\n"
        << "  --scan-lan    Escaneia sub-rede LAN\n"
        << "  --scan-all    Escaneia Radmin e LAN\n"
        << "  --help        Esta ajuda\n\n"
        << "Config compartilhada: " << nm::config_path().string() << "\n"
        << "Nota: bandeja/GUI/toast ficam na versão Python (Fase 1 = core).\n";
}

}  // namespace

int main(int argc, char** argv) {
    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);

    std::string mode = "run";
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--help" || arg == "-h") {
            print_help();
            return 0;
        }
        if (arg == "--run") {
            mode = "run";
        } else if (arg == "--status") {
            mode = "status";
        } else if (arg == "--scan") {
            mode = "scan";
        } else if (arg == "--scan-lan") {
            mode = "scan-lan";
        } else if (arg == "--scan-all") {
            mode = "scan-all";
        } else {
            std::cerr << "Flag desconhecida: " << arg << "\n";
            print_help();
            return 1;
        }
    }

    try {
        if (mode == "status") {
            nm::show_status();
            return 0;
        }
        if (mode == "scan") {
            return nm::scan_network("radmin") ? 0 : 1;
        }
        if (mode == "scan-lan") {
            return nm::scan_network("lan") ? 0 : 1;
        }
        if (mode == "scan-all") {
            nm::scan_network("radmin");
            std::cout << "\n";
            nm::scan_network("lan");
            return 0;
        }

        nm::run_monitor_loop(g_stop);
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "Erro: " << ex.what() << "\n";
        return 1;
    }
}
