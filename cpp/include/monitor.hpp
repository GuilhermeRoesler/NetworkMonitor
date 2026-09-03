#pragma once

#include "config.hpp"

#include <atomic>
#include <functional>
#include <string>
#include <vector>

namespace nm {

struct MonitorSnapshot {
    std::vector<Peer> peers;
    StateMap state;
    std::string radmin_ip;
    std::string lan_ip;
    int visible_count{0};
    int hidden_count{0};
    int online_count{0};
    bool notifications_enabled{true};
};

struct PeerTransitionEvent {
    Peer peer;
    bool online{false};
};

struct PeerDiscoveredEvent {
    Peer peer;
};

struct MonitorEventSink {
    virtual ~MonitorEventSink() = default;
    virtual void on_peer_transition(const PeerTransitionEvent& event) = 0;
    virtual void on_peer_discovered(const PeerDiscoveredEvent& event) = 0;
    virtual void on_snapshot(const MonitorSnapshot& snapshot) = 0;
    virtual void on_log_message(const std::string& message) = 0;
};

StateMap check_peers(
    std::vector<Peer>& peers,
    const StateMap& previous,
    bool notifications_enabled,
    MonitorEventSink* sink = nullptr,
    const std::atomic_bool* stop = nullptr);
void run_monitor_loop(std::atomic_bool& stop, MonitorEventSink* sink = nullptr);
bool scan_network(const std::string& network_type);
void show_status();

}  // namespace nm
