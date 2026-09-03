#pragma once

#include "config.hpp"

#include <optional>
#include <atomic>
#include <set>
#include <string>
#include <vector>

namespace nm {

bool is_radmin_ip(const std::string& ip);
bool is_private_ip(const std::string& ip);

std::optional<std::string> get_radmin_ip();
std::optional<std::string> get_lan_ip();
std::optional<std::string> get_local_ip(const std::string& network_type);

std::string subnet_prefix_24(const std::string& ip);
std::set<std::string> skip_ips_for_network(const std::string& network_type, const std::string& local_ip);

std::vector<Peer> discover_peers(
    const std::string& local_ip,
    const std::set<std::string>& known_ips,
    const std::set<std::string>& skip_ips,
    const std::atomic_bool* stop = nullptr);

}  // namespace nm
