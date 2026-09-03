#pragma once

#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace nm {

struct Peer {
    std::string ip;
    std::string name;
    std::string network_name;
    std::string network_type{"radmin"};
    bool hidden{false};
    bool muted{false};
    std::optional<bool> online;
};

struct NetworkConfig {
    std::string name;
    std::string network_type;
    bool enabled{true};
    bool auto_discover{true};
    std::vector<Peer> peers;
};

struct MonitorConfig {
    int interval_seconds{15};
    bool auto_discover{true};
    int scan_interval_seconds{300};
    bool notifications_enabled{true};
    std::vector<std::string> peer_order;
    std::vector<NetworkConfig> networks;

    std::vector<Peer> all_peers() const;
    std::vector<Peer> visible_peers() const;
    std::vector<Peer> hidden_peers() const;
};

using StateMap = std::unordered_map<std::string, bool>;

MonitorConfig load_config();
void save_default_config();
StateMap load_state();
void save_state(const StateMap& state, const MonitorConfig& config);
void persist_discovered_peers(const std::string& network_name, const std::vector<Peer>& discovered);
bool update_peer_name(const std::string& ip, const std::string& new_name);
bool set_peer_hidden(const std::string& ip, bool hidden);
bool set_peer_muted(const std::string& ip, bool muted);
void set_notifications_enabled(bool enabled);
void save_peer_order(const std::vector<std::string>& order);
bool move_peer(const std::string& dragged_ip, const std::string& target_ip);
bool move_peer_to_end(const std::string& dragged_ip);

}  // namespace nm
