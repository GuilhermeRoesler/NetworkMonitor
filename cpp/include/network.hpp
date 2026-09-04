#pragma once

#include "config.hpp"

#include <optional>
#include <atomic>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

namespace nm {

struct LocalInterface {
    std::string name;
    std::string ip;
    std::string network_type;  // lan | radmin | tailscale | wireguard

    std::string id() const;
};

bool is_radmin_ip(const std::string& ip);
bool is_private_ip(const std::string& ip);
bool is_tailscale_ip(const std::string& ip);

std::string adapter_id(const std::string& network_type, const std::string& name);
bool default_adapter_enabled(const std::string& network_type);
bool is_adapter_monitored(
    const LocalInterface& iface,
    const std::unordered_map<std::string, bool>& monitored_adapters);
bool is_adapter_monitored(
    const std::string& adapter_key,
    const std::unordered_map<std::string, bool>& monitored_adapters,
    const std::string& network_type = {});

std::vector<LocalInterface> parse_ipconfig_interfaces(const std::string& text);
std::vector<LocalInterface> list_local_interfaces();

std::optional<std::string> get_radmin_ip();
std::optional<std::string> get_lan_ip();
std::vector<std::string> get_lan_ips();
std::vector<std::string> get_local_ips(const std::string& network_type);
std::optional<std::string> get_local_ip(const std::string& network_type);

std::vector<LocalInterface> get_monitored_interfaces(
    const std::unordered_map<std::string, bool>& monitored_adapters = {});
std::vector<std::string> get_monitored_ips(
    const std::string& network_type,
    const std::unordered_map<std::string, bool>& monitored_adapters = {});

std::string format_local_interfaces(const std::vector<LocalInterface>& interfaces);
std::string format_local_interfaces();

std::string subnet_prefix_24(const std::string& ip);
std::vector<std::string> unique_scan_ips(const std::vector<std::string>& local_ips);
std::set<std::string> skip_ips_for_network(const std::string& network_type, const std::string& local_ip);

std::vector<Peer> discover_peers(
    const std::string& local_ip,
    const std::set<std::string>& known_ips,
    const std::set<std::string>& skip_ips,
    const std::atomic_bool* stop = nullptr);

}  // namespace nm
