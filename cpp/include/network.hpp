#pragma once

#include "config.hpp"

#include <optional>
#include <atomic>
#include <set>
#include <string>
#include <vector>

namespace nm {

struct LocalInterface {
    std::string name;
    std::string ip;
    std::string network_type;  // "radmin" | "lan"
};

bool is_radmin_ip(const std::string& ip);
bool is_private_ip(const std::string& ip);

std::vector<LocalInterface> parse_ipconfig_interfaces(const std::string& text);
std::vector<LocalInterface> list_local_interfaces();

std::optional<std::string> get_radmin_ip();
std::optional<std::string> get_lan_ip();
std::vector<std::string> get_lan_ips();
std::vector<std::string> get_local_ips(const std::string& network_type);
std::optional<std::string> get_local_ip(const std::string& network_type);

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
