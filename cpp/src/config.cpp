#include "config.hpp"

#include "paths.hpp"

#include <nlohmann_json.hpp>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <ctime>
#include <fstream>
#include <set>
#include <stdexcept>
#include <unordered_map>

namespace nm {
namespace {

using json = nlohmann::json;

std::vector<std::string> collect_peer_ips(const json& raw) {
    std::vector<std::string> ips;
    for (const auto& network : raw.value("networks", json::array())) {
        for (const auto& peer : network.value("peers", json::array())) {
            const std::string ip = peer.value("ip", "");
            if (!ip.empty()) {
                ips.push_back(ip);
            }
        }
    }
    return ips;
}

std::set<std::string> get_hidden_ips(const json& raw) {
    std::set<std::string> hidden;
    for (const auto& network : raw.value("networks", json::array())) {
        for (const auto& peer : network.value("peers", json::array())) {
            const std::string ip = peer.value("ip", "");
            if (!ip.empty() && peer.value("hidden", false)) {
                hidden.insert(ip);
            }
        }
    }
    return hidden;
}

std::vector<std::string> normalize_peer_order(json& raw) {
    const auto known = collect_peer_ips(raw);
    const auto hidden = get_hidden_ips(raw);
    std::set<std::string> known_set(known.begin(), known.end());

    std::vector<std::string> order;
    for (const auto& ip : raw.value("peer_order", json::array())) {
        if (ip.is_string() && known_set.count(ip.get<std::string>())) {
            order.push_back(ip.get<std::string>());
        }
    }
    for (const auto& ip : known) {
        if (std::find(order.begin(), order.end(), ip) == order.end()) {
            order.push_back(ip);
        }
    }

    std::vector<std::string> visible;
    std::vector<std::string> hidden_order;
    for (const auto& ip : order) {
        if (hidden.count(ip)) {
            hidden_order.push_back(ip);
        } else {
            visible.push_back(ip);
        }
    }
    visible.insert(visible.end(), hidden_order.begin(), hidden_order.end());
    raw["peer_order"] = visible;
    return visible;
}

void write_json(const fs::path& path, const json& raw) {
    ensure_data_dir();
    std::ofstream out(path, std::ios::binary);
    if (!out) {
        throw std::runtime_error("Não foi possível gravar " + path.string());
    }
    out << raw.dump(2);
}

json read_json(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        throw std::runtime_error("Não foi possível ler " + path.string());
    }
    json raw;
    in >> raw;
    return raw;
}

json load_raw_config() {
    const auto path = config_path();
    if (!fs::exists(path)) {
        save_default_config();
    }
    return read_json(path);
}

void save_raw_config(const json& raw) { write_json(config_path(), raw); }

json* find_peer(json& raw, const std::string& ip, std::string* peer_name = nullptr) {
    for (auto& network : raw["networks"]) {
        for (auto& peer : network["peers"]) {
            if (peer.value("ip", "") == ip) {
                if (peer_name != nullptr) {
                    *peer_name = peer.value("name", ip);
                }
                return &peer;
            }
        }
    }
    return nullptr;
}

const json* find_peer(const json& raw, const std::string& ip) {
    for (const auto& network : raw["networks"]) {
        for (const auto& peer : network["peers"]) {
            if (peer.value("ip", "") == ip) {
                return &peer;
            }
        }
    }
    return nullptr;
}

}  // namespace

std::vector<Peer> MonitorConfig::all_peers() const {
    std::vector<Peer> result;
    for (const auto& network : networks) {
        if (!network.enabled) {
            continue;
        }
        for (const auto& peer : network.peers) {
            result.push_back(peer);
        }
    }

    if (peer_order.empty()) {
        std::stable_partition(result.begin(), result.end(), [](const Peer& p) { return !p.hidden; });
        return result;
    }

    std::unordered_map<std::string, size_t> rank;
    for (size_t i = 0; i < peer_order.size(); ++i) {
        rank[peer_order[i]] = i;
    }
    const size_t fallback = peer_order.size();
    std::sort(result.begin(), result.end(), [&](const Peer& a, const Peer& b) {
        const int ha = a.hidden ? 1 : 0;
        const int hb = b.hidden ? 1 : 0;
        if (ha != hb) {
            return ha < hb;
        }
        const size_t ra = rank.count(a.ip) ? rank[a.ip] : fallback;
        const size_t rb = rank.count(b.ip) ? rank[b.ip] : fallback;
        if (ra != rb) {
            return ra < rb;
        }
        return a.ip < b.ip;
    });
    return result;
}

std::vector<Peer> MonitorConfig::visible_peers() const {
    std::vector<Peer> result;
    for (const auto& peer : all_peers()) {
        if (!peer.hidden) {
            result.push_back(peer);
        }
    }
    return result;
}

std::vector<Peer> MonitorConfig::hidden_peers() const {
    std::vector<Peer> result;
    for (const auto& peer : all_peers()) {
        if (peer.hidden) {
            result.push_back(peer);
        }
    }
    return result;
}

void save_default_config() {
    json raw = {
        {"interval_seconds", 15},
        {"auto_discover", true},
        {"scan_interval_seconds", 300},
        {"notifications_enabled", true},
        {"history_retention_days", kHistoryRetentionDefault},
        {"networks",
         json::array(
             {json{{"name", "Radmin VPN"},
                   {"type", "radmin"},
                   {"enabled", true},
                   {"auto_discover", true},
                   {"peers", json::array()}},
              json{{"name", "Rede Local (LAN)"},
                   {"type", "lan"},
                   {"enabled", true},
                   {"auto_discover", true},
                   {"peers", json::array()}}})},
    };
    write_json(config_path(), raw);
}

MonitorConfig load_config() {
    const auto path = config_path();
    if (!fs::exists(path)) {
        save_default_config();
    }

    json raw = read_json(path);
    const auto original_order = raw.value("peer_order", json::array());
    const bool global_auto = raw.value("auto_discover", true);

    MonitorConfig config;
    config.interval_seconds = raw.value("interval_seconds", 15);
    config.auto_discover = global_auto;
    config.scan_interval_seconds = raw.value("scan_interval_seconds", 300);
    config.notifications_enabled = raw.value("notifications_enabled", true);
    config.history_retention_days =
        clamp_history_retention_days(raw.value("history_retention_days", kHistoryRetentionDefault));

    for (const auto& network : raw.value("networks", json::array())) {
        NetworkConfig net;
        net.name = network.value("name", "Rede");
        net.network_type = network.value("type", "radmin");
        net.enabled = network.value("enabled", true);
        if (network.contains("auto_discover") && !network["auto_discover"].is_null()) {
            net.auto_discover = network.value("auto_discover", global_auto);
        } else {
            net.auto_discover = global_auto;
        }

        for (const auto& peer : network.value("peers", json::array())) {
            const std::string ip = peer.value("ip", "");
            if (ip.empty()) {
                continue;
            }
            Peer p;
            p.ip = ip;
            p.name = peer.value("name", ip);
            p.network_name = net.name;
            p.network_type = net.network_type;
            p.hidden = peer.value("hidden", false);
            p.muted = peer.value("muted", false);
            net.peers.push_back(std::move(p));
        }
        config.networks.push_back(std::move(net));
    }

    config.peer_order = normalize_peer_order(raw);
    if (raw.value("peer_order", json::array()) != original_order) {
        write_json(path, raw);
    }
    return config;
}

StateMap load_state() {
    const auto path = state_path();
    if (!fs::exists(path)) {
        return {};
    }
    try {
        const json raw = read_json(path);
        StateMap state;
        for (auto it = raw.begin(); it != raw.end(); ++it) {
            if (it.value().is_boolean()) {
                state[it.key()] = it.value().get<bool>();
            }
        }
        return state;
    } catch (...) {
        return {};
    }
}

void save_state(const StateMap& state, const MonitorConfig& config) {
    std::set<std::string> hidden;
    for (const auto& peer : config.hidden_peers()) {
        hidden.insert(peer.ip);
    }
    json raw = json::object();
    for (const auto& [ip, online] : state) {
        if (!hidden.count(ip)) {
            raw[ip] = online;
        }
    }
    write_json(state_path(), raw);
}

int clamp_history_retention_days(int days) {
    if (days < kHistoryRetentionMin) {
        return kHistoryRetentionMin;
    }
    if (days > kHistoryRetentionMax) {
        return kHistoryRetentionMax;
    }
    return days;
}

std::string history_now_iso() {
    const auto now = std::chrono::system_clock::now();
    const std::time_t t = std::chrono::system_clock::to_time_t(now);
    std::tm local{};
#if defined(_WIN32)
    localtime_s(&local, &t);
#else
    localtime_r(&t, &local);
#endif
    char buf[32]{};
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", &local);
    return std::string(buf);
}

HistoryMap load_history() {
    const auto path = history_path();
    if (!fs::exists(path)) {
        return {};
    }
    try {
        const json raw = read_json(path);
        HistoryMap history;
        if (!raw.is_object()) {
            return {};
        }
        for (auto it = raw.begin(); it != raw.end(); ++it) {
            if (!it.value().is_array()) {
                continue;
            }
            std::vector<HistorySegment> segments;
            for (const auto& seg : it.value()) {
                if (!seg.is_object()) {
                    continue;
                }
                const std::string start = seg.value("start", "");
                if (start.empty()) {
                    continue;
                }
                HistorySegment item;
                item.start = start;
                if (seg.contains("end") && !seg["end"].is_null()) {
                    item.end = seg.value("end", "");
                    if (item.end->empty()) {
                        item.end.reset();
                    }
                }
                segments.push_back(std::move(item));
            }
            if (!segments.empty()) {
                history[it.key()] = std::move(segments);
            }
        }
        return history;
    } catch (...) {
        return {};
    }
}

void save_history(const HistoryMap& history) {
    json raw = json::object();
    for (const auto& [ip, segments] : history) {
        json arr = json::array();
        for (const auto& seg : segments) {
            json item = {{"start", seg.start}};
            if (seg.end) {
                item["end"] = *seg.end;
            } else {
                item["end"] = nullptr;
            }
            arr.push_back(std::move(item));
        }
        raw[ip] = std::move(arr);
    }
    write_json(history_path(), raw);
}

namespace {

bool has_open_segment(const std::vector<HistorySegment>& segments) {
    return !segments.empty() && !segments.back().end.has_value();
}

void ensure_open_segment(HistoryMap& history, const std::string& ip, const std::string& now_iso) {
    auto& segments = history[ip];
    if (!has_open_segment(segments)) {
        segments.push_back(HistorySegment{now_iso, std::nullopt});
    }
}

void close_open_segment(HistoryMap& history, const std::string& ip, const std::string& now_iso) {
    auto it = history.find(ip);
    if (it == history.end() || it->second.empty()) {
        return;
    }
    if (!it->second.back().end.has_value()) {
        it->second.back().end = now_iso;
    }
}

}  // namespace

void record_history_transition(HistoryMap& history, const std::string& ip, bool online,
                               const std::string& now_iso) {
    if (online) {
        ensure_open_segment(history, ip, now_iso);
    } else {
        close_open_segment(history, ip, now_iso);
    }
}

void update_history_from_states(HistoryMap& history, const StateMap& previous, const StateMap& current,
                                const std::string& now_iso) {
    for (const auto& [ip, online] : current) {
        const auto it = previous.find(ip);
        if (it == previous.end()) {
            if (online) {
                ensure_open_segment(history, ip, now_iso);
            }
            continue;
        }
        if (it->second != online) {
            record_history_transition(history, ip, online, now_iso);
        } else if (online) {
            ensure_open_segment(history, ip, now_iso);
        }
    }
}

HistoryMap prune_history(const HistoryMap& history, int retention_days, const std::string& now_iso) {
    // Cutoff by string compare on ISO local timestamps (YYYY-MM-DDTHH:MM:SS).
    // Approximate: subtract retention_days from the date portion of now_iso.
    std::string cutoff = now_iso;
    if (now_iso.size() >= 10) {
        int year = 0;
        int month = 0;
        int day = 0;
        if (std::sscanf(now_iso.c_str(), "%d-%d-%d", &year, &month, &day) == 3) {
            std::tm tm{};
            tm.tm_year = year - 1900;
            tm.tm_mon = month - 1;
            tm.tm_mday = day - clamp_history_retention_days(retention_days);
            tm.tm_hour = 0;
            tm.tm_min = 0;
            tm.tm_sec = 0;
            tm.tm_isdst = -1;
            const std::time_t t = std::mktime(&tm);
            if (t != static_cast<std::time_t>(-1)) {
                std::tm local{};
#if defined(_WIN32)
                localtime_s(&local, &t);
#else
                localtime_r(&t, &local);
#endif
                char buf[32]{};
                std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", &local);
                // Keep time-of-day from now_iso when possible.
                if (now_iso.size() >= 19) {
                    cutoff = std::string(buf).substr(0, 10) + now_iso.substr(10);
                } else {
                    cutoff = buf;
                }
            }
        }
    }

    HistoryMap pruned;
    for (const auto& [ip, segments] : history) {
        std::vector<HistorySegment> kept;
        for (const auto& seg : segments) {
            if (seg.end && *seg.end < cutoff) {
                continue;
            }
            HistorySegment copy = seg;
            if (copy.start < cutoff) {
                copy.start = cutoff;
            }
            kept.push_back(std::move(copy));
        }
        if (!kept.empty()) {
            pruned[ip] = std::move(kept);
        }
    }
    return pruned;
}

void persist_discovered_peers(const std::string& network_name, const std::vector<Peer>& discovered) {
    if (discovered.empty()) {
        return;
    }
    json raw = load_raw_config();
    auto& networks = raw["networks"];
    json* target = nullptr;
    for (auto& network : networks) {
        if (network.value("name", "") == network_name) {
            target = &network;
            break;
        }
    }
    if (!target) {
        return;
    }

    auto& peers = (*target)["peers"];
    std::set<std::string> existing;
    for (const auto& peer : peers) {
        existing.insert(peer.value("ip", ""));
    }
    for (const auto& peer : discovered) {
        if (existing.count(peer.ip)) {
            continue;
        }
        peers.push_back(json{{"name", peer.name}, {"ip", peer.ip}});
        existing.insert(peer.ip);
    }

    auto order = normalize_peer_order(raw);
    for (const auto& peer : discovered) {
        if (std::find(order.begin(), order.end(), peer.ip) == order.end()) {
            order.push_back(peer.ip);
        }
    }
    raw["peer_order"] = order;
    save_raw_config(raw);
}

bool update_peer_name(const std::string& ip, const std::string& new_name) {
    if (new_name.empty()) {
        return false;
    }

    json raw = load_raw_config();
    json* peer = find_peer(raw, ip);
    if (peer == nullptr) {
        return false;
    }

    (*peer)["name"] = new_name;
    save_raw_config(raw);
    return true;
}

bool set_peer_hidden(const std::string& ip, bool hidden) {
    json raw = load_raw_config();
    json* peer = find_peer(raw, ip);
    if (peer == nullptr) {
        return false;
    }

    if (hidden) {
        (*peer)["hidden"] = true;
    } else {
        peer->erase("hidden");
    }
    normalize_peer_order(raw);
    save_raw_config(raw);
    return true;
}

bool set_peer_muted(const std::string& ip, bool muted) {
    json raw = load_raw_config();
    json* peer = find_peer(raw, ip);
    if (peer == nullptr) {
        return false;
    }

    if (muted) {
        (*peer)["muted"] = true;
    } else {
        peer->erase("muted");
    }
    save_raw_config(raw);
    return true;
}

void set_notifications_enabled(bool enabled) {
    json raw = load_raw_config();
    raw["notifications_enabled"] = enabled;
    save_raw_config(raw);
}

void save_peer_order(const std::vector<std::string>& order) {
    json raw = load_raw_config();
    const auto peer_ips = collect_peer_ips(raw);
    std::set<std::string> known(peer_ips.begin(), peer_ips.end());
    const std::set<std::string> hidden = get_hidden_ips(raw);

    std::vector<std::string> normalized;
    for (const auto& ip : order) {
        if (known.count(ip) && std::find(normalized.begin(), normalized.end(), ip) == normalized.end()) {
            normalized.push_back(ip);
        }
    }
    for (const auto& ip : peer_ips) {
        if (std::find(normalized.begin(), normalized.end(), ip) == normalized.end()) {
            normalized.push_back(ip);
        }
    }

    std::vector<std::string> visible;
    std::vector<std::string> hidden_order;
    for (const auto& ip : normalized) {
        if (hidden.count(ip)) {
            hidden_order.push_back(ip);
        } else {
            visible.push_back(ip);
        }
    }
    visible.insert(visible.end(), hidden_order.begin(), hidden_order.end());
    raw["peer_order"] = visible;
    save_raw_config(raw);
}

bool move_peer(const std::string& dragged_ip, const std::string& target_ip) {
    if (dragged_ip == target_ip) {
        return false;
    }

    json raw = load_raw_config();
    const std::set<std::string> hidden = get_hidden_ips(raw);
    if (hidden.count(dragged_ip)) {
        return false;
    }

    std::vector<std::string> order = normalize_peer_order(raw);
    if (std::find(order.begin(), order.end(), dragged_ip) == order.end()) {
        return false;
    }

    std::vector<std::string> visible;
    std::vector<std::string> hidden_order;
    for (const auto& ip : order) {
        if (hidden.count(ip)) {
            hidden_order.push_back(ip);
        } else {
            visible.push_back(ip);
        }
    }

    visible.erase(std::remove(visible.begin(), visible.end(), dragged_ip), visible.end());
    const auto target_it = std::find(visible.begin(), visible.end(), target_ip);
    if (target_it == visible.end()) {
        visible.push_back(dragged_ip);
    } else {
        visible.insert(target_it, dragged_ip);
    }

    visible.insert(visible.end(), hidden_order.begin(), hidden_order.end());
    raw["peer_order"] = visible;
    save_raw_config(raw);
    return true;
}

bool move_peer_to_end(const std::string& dragged_ip) {
    json raw = load_raw_config();
    const std::set<std::string> hidden = get_hidden_ips(raw);
    if (hidden.count(dragged_ip)) {
        return false;
    }

    std::vector<std::string> order = normalize_peer_order(raw);
    std::vector<std::string> visible;
    std::vector<std::string> hidden_order;
    for (const auto& ip : order) {
        if (hidden.count(ip)) {
            hidden_order.push_back(ip);
        } else {
            visible.push_back(ip);
        }
    }

    const auto it = std::find(visible.begin(), visible.end(), dragged_ip);
    if (it == visible.end()) {
        return false;
    }
    visible.erase(it);
    visible.push_back(dragged_ip);

    visible.insert(visible.end(), hidden_order.begin(), hidden_order.end());
    raw["peer_order"] = visible;
    save_raw_config(raw);
    return true;
}

}  // namespace nm
