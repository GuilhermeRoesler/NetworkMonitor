#pragma once

#include "config.hpp"

#include <optional>
#include <atomic>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

namespace nm {

constexpr int kDefaultPrefixlen = 24;
constexpr int kMinScanPrefixlen = 22;

struct LocalInterface {
    std::string name;
    std::string ip;
    std::string network_type;  // lan | radmin | tailscale | wireguard
    int prefixlen{kDefaultPrefixlen};

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

int mask_to_prefixlen(const std::string& mask);
int effective_scan_prefixlen(int prefixlen);
bool send_arp(const std::string& dest_ip, const std::string& src_ip = "0.0.0.0");

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

int prefixlen_for_local_ip(const std::string& ip);
std::string subnet_prefix(const std::string& ip, int prefixlen = kDefaultPrefixlen);
std::string scan_subnet_prefix(const std::string& ip, int prefixlen = -1);
/** Compat: sempre /24 em torno do host. */
std::string subnet_prefix_24(const std::string& ip);
std::vector<std::string> unique_scan_ips(const std::vector<std::string>& local_ips);
std::set<std::string> skip_ips_for_network(const std::string& network_type, const std::string& local_ip);

std::vector<std::string> subnet_host_candidates(
    const std::string& local_ip,
    const std::set<std::string>& excluded = {},
    int prefixlen = -1);
std::vector<std::string> arp_probe_hosts(
    const std::vector<std::string>& candidates,
    const std::string& src_ip = "0.0.0.0",
    const std::atomic_bool* stop = nullptr);

/** Vizinhos por IP de interface a partir do stdout de ``arp -a``. */
std::unordered_map<std::string, std::vector<std::string>> parse_arp_neighbors(const std::string& text);
std::vector<std::string> radmin_neighbor_ips_from_arp(
    const std::string& arp_text,
    const std::vector<std::string>& local_ips,
    const std::set<std::string>& skip_ips = {});
std::vector<std::string> list_radmin_arp_neighbors(
    const std::vector<std::string>& local_ips,
    const std::set<std::string>& skip_ips = {});

std::vector<std::pair<std::string, std::string>> parse_tailscale_status_peers(const std::string& json_text);
std::vector<std::pair<std::string, std::string>> list_tailscale_status_peers();
std::vector<std::string> parse_wg_show_dump_peers(
    const std::string& text,
    const std::set<std::string>& local_ips = {});
std::vector<std::string> list_wireguard_peer_ips(const std::vector<std::string>& local_ips = {});

std::vector<Peer> discover_peers(
    const std::string& local_ip,
    const std::set<std::string>& known_ips,
    const std::set<std::string>& skip_ips,
    const std::atomic_bool* stop = nullptr);

std::vector<Peer> discover_lan_peers(
    const std::string& local_ip,
    const std::set<std::string>& known_ips,
    const std::set<std::string>& skip_ips,
    const std::atomic_bool* stop = nullptr);

std::vector<Peer> discover_radmin_peers(
    const std::vector<std::string>& local_ips,
    const std::set<std::string>& known_ips,
    const std::set<std::string>& skip_ips,
    const std::atomic_bool* stop = nullptr);

std::vector<Peer> discover_tailscale_peers(
    const std::set<std::string>& known_ips,
    const std::set<std::string>& skip_ips,
    const std::atomic_bool* stop = nullptr);

std::vector<Peer> discover_wireguard_peers(
    const std::vector<std::string>& local_ips,
    const std::set<std::string>& known_ips,
    const std::set<std::string>& skip_ips,
    const std::atomic_bool* stop = nullptr);

std::vector<Peer> discover_network_peers(
    const std::string& network_type,
    const std::vector<std::string>& local_ips,
    const std::set<std::string>& known_ips,
    const std::atomic_bool* stop = nullptr);

}  // namespace nm
