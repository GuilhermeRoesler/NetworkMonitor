#include "monitor.hpp"

#include "logging.hpp"
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

void emit_log(MonitorEventSink* sink, const std::string& message) {
    log_message(message);
    if (sink != nullptr) {
        sink->on_log_message(message);
    }
}

std::string network_label(const std::string& network_type) {
    if (network_type == "radmin") {
        return "Radmin VPN";
    }
    if (network_type == "tailscale") {
        return "Tailscale";
    }
    if (network_type == "wireguard") {
        return "WireGuard";
    }
    if (network_type == "lan") {
        return "Rede local";
    }
    return network_type;
}

}  // namespace

StateMap check_peers(
    std::vector<Peer>& peers,
    const StateMap& previous,
    bool notifications_enabled,
    MonitorEventSink* sink,
    const std::atomic_bool* stop) {
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
                if (stop != nullptr && stop->load()) {
                    break;
                }
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
                const std::string message = std::string("[") + peer->network_name + "] " + peer->name + " " +
                                            status + " — IP: " + peer->ip;
                emit_log(sink, message);
                if (notifications_enabled && sink != nullptr) {
                    sink->on_peer_transition(PeerTransitionEvent{*peer, online});
                }
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

void run_monitor_loop(std::atomic_bool& stop, MonitorEventSink* sink) {
    emit_log(sink, "Iniciando Network Monitor (C++)");
    MonitorConfig config = load_config();
    StateMap state = load_state();
    HistoryMap history = load_history();
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
        for (const auto& lan_ip : get_lan_ips()) {
            known_global.insert(lan_ip);
        }

        bool config_changed = false;
        for (auto& network : config.networks) {
            if (!network.enabled) {
                continue;
            }
            const auto local_ips = get_monitored_ips(network.network_type, config.monitored_adapters);
            if (local_ips.empty()) {
                emit_log(sink, "Rede '" + network.name + "' (" + network.network_type +
                                   ") sem adaptador monitorado detectado.");
                for (const auto& peer : network.peers) {
                    known_global.insert(peer.ip);
                    all_peers.push_back(peer);
                }
                continue;
            }

            double last_scan = last_scans.count(network.name) ? last_scans[network.name] : 0.0;
            const bool due = network.auto_discover && (now - last_scan) >= config.scan_interval_seconds;
            const bool empty = network.peers.empty() && network.auto_discover;

            if (due || empty) {
                const auto scan_ips = unique_scan_ips(local_ips);
                for (const auto& local_ip : local_ips) {
                    known_global.insert(local_ip);
                }
                std::vector<Peer> discovered_all;
                for (const auto& local_ip : scan_ips) {
                    if (stop.load()) {
                        break;
                    }
                    auto discovered = discover_peers(
                        local_ip,
                        known_global,
                        skip_ips_for_network(network.network_type, local_ip),
                        &stop);
                    for (auto& peer : discovered) {
                        peer.network_name = network.name;
                        peer.network_type = network.network_type;
                        emit_log(sink, "Peer descoberto: " + peer.name + " (" + peer.ip + ")");
                        if (sink != nullptr) {
                            sink->on_peer_discovered(PeerDiscoveredEvent{peer});
                        }
                        known_global.insert(peer.ip);
                    }
                    discovered_all.insert(discovered_all.end(), discovered.begin(), discovered.end());
                }
                if (!discovered_all.empty()) {
                    persist_discovered_peers(network.name, discovered_all);
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

        const auto radmin = get_radmin_ip();
        const auto lan = get_lan_ip();
        const auto lan_ips = get_lan_ips();
        const auto monitored_ifaces = get_monitored_interfaces(config.monitored_adapters);
        const std::string local_label = format_local_interfaces(monitored_ifaces);
        if (visible.empty()) {
            emit_log(sink, "Nenhum peer configurado ou encontrado. Aguardando...");
        } else {
            const StateMap previous_state = state;
            state = check_peers(visible, state, config.notifications_enabled, sink, &stop);
            save_state(state, config);
            const std::string now_iso = history_now_iso();
            update_history_from_states(history, previous_state, state, now_iso);
            history = prune_history(history, config.history_retention_days, now_iso);
            save_history(history);
            int online_count = 0;
            for (const auto& peer : visible) {
                if (state.count(peer.ip) && state.at(peer.ip)) {
                    ++online_count;
                }
            }
            emit_log(sink, "Verificação concluída: " + std::to_string(online_count) + "/" +
                               std::to_string(visible.size()) + " online (" +
                               std::to_string(config.hidden_peers().size()) + " ocultos) · " + local_label);
        }

        if (sink != nullptr) {
            MonitorSnapshot snapshot;
            snapshot.peers = config.all_peers();
            snapshot.state = state;
            snapshot.radmin_ip = radmin.value_or("");
            snapshot.lan_ip = lan.value_or("");
            snapshot.lan_ips = lan_ips;
            snapshot.local_ips = local_label;
            snapshot.visible_count = static_cast<int>(config.visible_peers().size());
            snapshot.hidden_count = static_cast<int>(config.hidden_peers().size());
            snapshot.online_count = 0;
            snapshot.notifications_enabled = config.notifications_enabled;
            for (const auto& peer : config.visible_peers()) {
                auto it = state.find(peer.ip);
                if (it != state.end() && it->second) {
                    ++snapshot.online_count;
                }
            }
            sink->on_snapshot(snapshot);
        }

        for (int i = 0; i < config.interval_seconds * 10 && !stop.load(); ++i) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        config = load_config();
    }
    emit_log(sink, "Monitor encerrado.");
}

bool scan_network(const std::string& network_type, bool monitored_only) {
    MonitorConfig config = load_config();
    std::vector<std::string> local_ips;
    if (monitored_only) {
        local_ips = get_monitored_ips(network_type, config.monitored_adapters);
    } else {
        local_ips = get_local_ips(network_type);
    }
    const std::string label = network_label(network_type);
    if (local_ips.empty()) {
        std::cout << label << " não encontrada. Verifique a conexão ou os adaptadores monitorados.\n";
        return false;
    }

    const auto scan_ips = unique_scan_ips(local_ips);
    std::cout << "IP(s) local(is) (" << label << "): ";
    for (size_t i = 0; i < local_ips.size(); ++i) {
        if (i > 0) {
            std::cout << ", ";
        }
        std::cout << local_ips[i];
    }
    std::cout << "\nEscaneando sub-rede(s) ";
    for (size_t i = 0; i < scan_ips.size(); ++i) {
        if (i > 0) {
            std::cout << ", ";
        }
        std::cout << subnet_prefix_24(scan_ips[i]);
    }
    std::cout << "...\n";

    const NetworkConfig* network = nullptr;
    for (const auto& candidate : config.networks) {
        if (candidate.network_type == network_type && candidate.enabled) {
            network = &candidate;
            break;
        }
    }
    if (!network) {
        ensure_network_type_enabled(network_type);
        config = load_config();
        for (const auto& candidate : config.networks) {
            if (candidate.network_type == network_type && candidate.enabled) {
                network = &candidate;
                break;
            }
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
    for (const auto& local_ip : local_ips) {
        known.insert(local_ip);
    }

    std::vector<Peer> discovered_all;
    for (const auto& local_ip : scan_ips) {
        auto discovered = discover_peers(local_ip, known, skip_ips_for_network(network_type, local_ip));
        for (auto& peer : discovered) {
            peer.network_name = network->name;
            peer.network_type = network_type;
            known.insert(peer.ip);
        }
        discovered_all.insert(discovered_all.end(), discovered.begin(), discovered.end());
    }

    if (!discovered_all.empty()) {
        persist_discovered_peers(network->name, discovered_all);
        std::cout << "\n" << discovered_all.size() << " peer(s) encontrado(s) em '" << network->name << "':\n";
        for (const auto& peer : discovered_all) {
            std::cout << "  - " << peer.name << " (" << peer.ip << ")\n";
        }
    } else {
        std::cout << "\nNenhum peer online encontrado na(s) sub-rede(s) " << label << ".\n";
    }
    return true;
}

bool scan_monitored() {
    const MonitorConfig config = load_config();
    std::set<std::string> types;
    for (const auto& iface : list_local_interfaces()) {
        if (is_adapter_monitored(iface, config.monitored_adapters)) {
            types.insert(iface.network_type);
        }
    }
    if (types.empty()) {
        std::cout << "Nenhum adaptador monitorado detectado.\n";
        return false;
    }
    bool ok = false;
    bool first = true;
    for (const auto& network_type : types) {
        if (!first) {
            std::cout << "\n";
        }
        first = false;
        if (scan_network(network_type, true)) {
            ok = true;
        }
    }
    return ok;
}

bool scan_all_detected() {
    std::set<std::string> types;
    for (const auto& iface : list_local_interfaces()) {
        types.insert(iface.network_type);
    }
    if (types.empty()) {
        std::cout << "Nenhuma interface detectada.\n";
        return false;
    }
    bool first = true;
    for (const auto& network_type : types) {
        if (!first) {
            std::cout << "\n";
        }
        first = false;
        scan_network(network_type, false);
    }
    return true;
}

void show_status() {
    const auto interfaces = list_local_interfaces();
    const auto lan_ips = get_lan_ips();
    const MonitorConfig config = load_config();
    const StateMap state = load_state();

    if (!interfaces.empty()) {
        std::cout << "Adaptadores:\n";
        for (const auto& iface : interfaces) {
            const char* flag = is_adapter_monitored(iface, config.monitored_adapters) ? "on" : "off";
            std::cout << "  [" << flag << "] [" << iface.network_type << "] " << iface.name << ": " << iface.ip
                      << "\n";
        }
    } else {
        std::cout << "Adaptadores: nenhum detectado\n";
    }
    std::cout << "IP(s) LAN: ";
    if (lan_ips.empty()) {
        std::cout << "não detectado";
    } else {
        for (size_t i = 0; i < lan_ips.size(); ++i) {
            if (i > 0) {
                std::cout << ", ";
            }
            std::cout << lan_ips[i];
        }
    }
    std::cout << "\n";
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
    std::cout << "Notificações: " << (config.notifications_enabled ? "ativadas" : "pausadas") << "\n";
    std::cout << "Retenção de histórico: " << config.history_retention_days << " dia(s)\n\n";

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
