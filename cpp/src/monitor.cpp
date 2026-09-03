#include "monitor.hpp"

#include "network.hpp"
#include "ping.hpp"

#include <atomic>
#include <chrono>
#include <iostream>
#include <mutex>
#include <set>
#include <thread>
#include <unordered_map>

namespace nm {
namespace {

void log_line(const std::string& message) {
    std::cout << message << std::endl;
}

}  // namespace

StateMap check_peers(std::vector<Peer>& peers, const StateMap& previous, bool /*notifications_enabled*/) {
    // Fase 1: sem toast WinRT — apenas atualiza estado (transições vão para o log).
    StateMap current = previous;
    std::vector<Peer*> monitored;
    for (auto& peer : peers) {
        if (!peer.hidden) {
            monitored.push_back(&peer);
        }
    }

    std::mutex mutex;
    std::atomic<size_t> next{0};
    const unsigned workers = 16;
    std::vector<std::thread> threads;
    threads.reserve(workers);

    for (unsigned i = 0; i < workers; ++i) {
        threads.emplace_back([&]() {
            while (true) {
                const size_t index = next.fetch_add(1);
                if (index >= monitored.size()) {
                    break;
                }
                Peer* peer = monitored[index];
                const bool online = ping_host(peer->ip);
                std::lock_guard lock(mutex);
                current[peer->ip] = online;
                peer->online = online;

                const auto it = previous.find(peer->ip);
                if (it == previous.end() || it->second == online || peer->muted) {
                    continue;
                }
                const char* status = online ? "ficou online" : "ficou offline";
                log_line(std::string("[") + peer->network_name + "] " + peer->name + " " + status +
                         " — IP: " + peer->ip);
            }
        });
    }
    for (auto& thread : threads) {
        thread.join();
    }

    for (const auto& peer : peers) {
        if (peer.hidden) {
            current.erase(peer.ip);
        }
    }
    return current;
}

void run_monitor_loop(std::atomic_bool& stop) {
    log_line("Iniciando Network Monitor (C++)");
    MonitorConfig config = load_config();
    StateMap state = load_state();
    std::unordered_map<std::string, double> last_scans;

    while (!stop.load()) {
        const auto now = std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
        std::vector<Peer> all_peers;
        std::set<std::string> known_global;
        for (const auto& peer : config.all_peers()) {
            known_global.insert(peer.ip);
        }
        if (auto radmin = get_radmin_ip()) {
            known_global.insert(*radmin);
        }
        if (auto lan = get_lan_ip()) {
            known_global.insert(*lan);
        }

        bool config_changed = false;
        for (auto& network : config.networks) {
            if (!network.enabled) {
                continue;
            }
            auto local_ip = get_local_ip(network.network_type);
            if (!local_ip) {
                log_line("Rede '" + network.name + "' (" + network.network_type + ") não detectada.");
                continue;
            }

            double last_scan = last_scans.count(network.name) ? last_scans[network.name] : 0.0;
            const bool due = network.auto_discover && (now - last_scan) >= config.scan_interval_seconds;
            const bool empty = network.peers.empty() && network.auto_discover;

            if (due || empty) {
                auto discovered = discover_peers(
                    *local_ip,
                    known_global,
                    skip_ips_for_network(network.network_type, *local_ip));
                for (auto& peer : discovered) {
                    peer.network_name = network.name;
                    peer.network_type = network.network_type;
                    log_line("Peer descoberto: " + peer.name + " (" + peer.ip + ")");
                }
                if (!discovered.empty()) {
                    persist_discovered_peers(network.name, discovered);
                    config_changed = true;
                }
                last_scans[network.name] = now;
            }

            for (const auto& peer : network.peers) {
                known_global.insert(peer.ip);
                all_peers.push_back(peer);
            }
        }

        if (config_changed) {
            config = load_config();
            all_peers = config.all_peers();
        }

        std::vector<Peer> visible;
        for (const auto& peer : all_peers) {
            if (!peer.hidden) {
                visible.push_back(peer);
            }
        }

        if (visible.empty()) {
            log_line("Nenhum peer configurado ou encontrado. Aguardando...");
        } else {
            state = check_peers(visible, state, config.notifications_enabled);
            save_state(state, config);
            int online_count = 0;
            for (const auto& peer : visible) {
                if (state.count(peer.ip) && state.at(peer.ip)) {
                    ++online_count;
                }
            }
            const auto radmin = get_radmin_ip();
            const auto lan = get_lan_ip();
            log_line(
                "Verificação concluída: " + std::to_string(online_count) + "/" + std::to_string(visible.size()) +
                " online (" + std::to_string(config.hidden_peers().size()) + " ocultos) · Radmin: " +
                (radmin ? *radmin : "—") + " · LAN: " + (lan ? *lan : "—"));
        }

        for (int i = 0; i < config.interval_seconds * 10 && !stop.load(); ++i) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }
    log_line("Monitor encerrado.");
}

bool scan_network(const std::string& network_type) {
    auto local_ip = get_local_ip(network_type);
    const std::string label = network_type == "radmin" ? "Radmin VPN" : "LAN";
    if (!local_ip) {
        std::cout << label << " não encontrada. Verifique a conexão.\n";
        return false;
    }

    std::cout << "IP local (" << label << "): " << *local_ip << "\n";
    std::cout << "Escaneando sub-rede " << subnet_prefix_24(*local_ip) << "...\n";

    MonitorConfig config = load_config();
    const NetworkConfig* network = nullptr;
    for (const auto& candidate : config.networks) {
        if (candidate.network_type == network_type && candidate.enabled) {
            network = &candidate;
            break;
        }
    }
    if (!network) {
        std::cout << "Nenhuma rede do tipo '" << network_type << "' habilitada em peers.json.\n";
        return false;
    }

    std::set<std::string> known;
    for (const auto& peer : config.all_peers()) {
        known.insert(peer.ip);
    }
    known.insert(*local_ip);

    auto discovered = discover_peers(*local_ip, known, skip_ips_for_network(network_type, *local_ip));
    for (auto& peer : discovered) {
        peer.network_name = network->name;
        peer.network_type = network_type;
    }

    if (!discovered.empty()) {
        persist_discovered_peers(network->name, discovered);
        std::cout << "\n" << discovered.size() << " peer(s) encontrado(s) em '" << network->name << "':\n";
        for (const auto& peer : discovered) {
            std::cout << "  - " << peer.name << " (" << peer.ip << ")\n";
        }
    } else {
        std::cout << "\nNenhum peer online encontrado na sub-rede " << label << ".\n";
    }
    return true;
}

void show_status() {
    const auto radmin = get_radmin_ip();
    const auto lan = get_lan_ip();
    const MonitorConfig config = load_config();
    const StateMap state = load_state();

    std::cout << "IP Radmin: " << (radmin ? *radmin : "não detectado") << "\n";
    std::cout << "IP LAN:    " << (lan ? *lan : "não detectado") << "\n";
    std::cout << "Peers visíveis: " << config.visible_peers().size() << "\n";
    std::cout << "Peers ocultos:  " << config.hidden_peers().size() << "\n";
    std::cout << "Intervalo de verificação: " << config.interval_seconds << "s\n";
    int muted = 0;
    for (const auto& peer : config.visible_peers()) {
        if (peer.muted) {
            ++muted;
        }
    }
    std::cout << "Peers silenciados: " << muted << "\n";
    std::cout << "Notificações: " << (config.notifications_enabled ? "ativadas" : "pausadas") << "\n\n";

    const auto peers = config.visible_peers();
    if (peers.empty()) {
        std::cout << "Nenhum peer em peers.json. Use --scan, --scan-lan ou --scan-all.\n";
        return;
    }

    std::string current_network;
    for (const auto& peer : peers) {
        if (peer.network_name != current_network) {
            current_network = peer.network_name;
            std::cout << "[" << current_network << "]\n";
        }
        std::string status = "desconhecido";
        if (state.count(peer.ip)) {
            status = state.at(peer.ip) ? "online" : "offline";
        }
        std::cout << "  [" << status << "] " << peer.name << " (" << peer.ip << ")";
        if (peer.muted) {
            std::cout << " [silenciado]";
        }
        std::cout << "\n";
    }
}

}  // namespace nm
