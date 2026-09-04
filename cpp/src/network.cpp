#include "network.hpp"

#include "ping.hpp"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <atomic>
#include <algorithm>
#include <cctype>
#include <cstdio>
#include <mutex>
#include <regex>
#include <sstream>
#include <thread>
#include <vector>

namespace nm {

bool is_radmin_ip(const std::string& ip) { return ip.rfind("26.", 0) == 0; }

bool is_private_ip(const std::string& ip) {
    unsigned a = 0, b = 0, c = 0, d = 0;
    if (std::sscanf(ip.c_str(), "%u.%u.%u.%u", &a, &b, &c, &d) != 4) {
        return false;
    }
    if (a == 10) {
        return true;
    }
    if (a == 172 && b >= 16 && b <= 31) {
        return true;
    }
    if (a == 192 && b == 168) {
        return true;
    }
    return false;
}

bool is_tailscale_ip(const std::string& ip) {
    unsigned a = 0, b = 0, c = 0, d = 0;
    if (std::sscanf(ip.c_str(), "%u.%u.%u.%u", &a, &b, &c, &d) != 4) {
        return false;
    }
    return a == 100 && b >= 64 && b <= 127;
}

std::string LocalInterface::id() const { return adapter_id(network_type, name); }

std::string adapter_id(const std::string& network_type, const std::string& name) {
    std::string slug;
    slug.reserve(name.size());
    bool pending_dash = false;
    for (unsigned char ch : name) {
        const char lower = static_cast<char>(::tolower(ch));
        if ((lower >= 'a' && lower <= 'z') || (lower >= '0' && lower <= '9')) {
            if (pending_dash && !slug.empty()) {
                slug.push_back('-');
            }
            slug.push_back(lower);
            pending_dash = false;
        } else {
            pending_dash = true;
        }
    }
    if (slug.empty()) {
        slug = "adapter";
    }
    return network_type + ":" + slug;
}

bool default_adapter_enabled(const std::string& network_type) { return network_type == "lan"; }

bool is_adapter_monitored(
    const std::string& adapter_key,
    const std::unordered_map<std::string, bool>& monitored_adapters,
    const std::string& network_type) {
    const auto it = monitored_adapters.find(adapter_key);
    if (it != monitored_adapters.end()) {
        return it->second;
    }
    std::string type = network_type;
    if (type.empty()) {
        const auto pos = adapter_key.find(':');
        type = pos == std::string::npos ? "lan" : adapter_key.substr(0, pos);
    }
    return default_adapter_enabled(type.empty() ? "lan" : type);
}

bool is_adapter_monitored(
    const LocalInterface& iface,
    const std::unordered_map<std::string, bool>& monitored_adapters) {
    return is_adapter_monitored(iface.id(), monitored_adapters, iface.network_type);
}

namespace {

std::string dword_to_ip(DWORD value) {
    const unsigned a = (value >> 24) & 0xFF;
    const unsigned b = (value >> 16) & 0xFF;
    const unsigned c = (value >> 8) & 0xFF;
    const unsigned d = value & 0xFF;
    std::ostringstream oss;
    oss << a << '.' << b << '.' << c << '.' << d;
    return oss.str();
}

std::optional<DWORD> read_radmin_reg_ipv4() {
    const wchar_t* paths[] = {
        L"SOFTWARE\\WOW6432Node\\Famatech\\RadminVPN\\1.0",
        L"SOFTWARE\\Famatech\\RadminVPN\\1.0",
    };
    for (const wchar_t* path : paths) {
        HKEY key = nullptr;
        if (RegOpenKeyExW(HKEY_LOCAL_MACHINE, path, 0, KEY_READ | KEY_WOW64_64KEY, &key) != ERROR_SUCCESS) {
            if (RegOpenKeyExW(HKEY_LOCAL_MACHINE, path, 0, KEY_READ, &key) != ERROR_SUCCESS) {
                continue;
            }
        }
        DWORD type = 0;
        DWORD value = 0;
        DWORD size = sizeof(value);
        const LONG status = RegQueryValueExW(key, L"IPv4", nullptr, &type, reinterpret_cast<LPBYTE>(&value), &size);
        RegCloseKey(key);
        if (status == ERROR_SUCCESS && (type == REG_DWORD || type == REG_BINARY)) {
            return value;
        }
    }
    return std::nullopt;
}

std::string run_ipconfig() {
    SECURITY_ATTRIBUTES sa{};
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;
    HANDLE read_pipe = nullptr;
    HANDLE write_pipe = nullptr;
    if (!CreatePipe(&read_pipe, &write_pipe, &sa, 0)) {
        return {};
    }
    SetHandleInformation(read_pipe, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOW si{};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.hStdOutput = write_pipe;
    si.hStdError = write_pipe;
    si.wShowWindow = SW_HIDE;

    PROCESS_INFORMATION pi{};
    wchar_t cmd[] = L"ipconfig";
    if (!CreateProcessW(nullptr, cmd, nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi)) {
        CloseHandle(write_pipe);
        CloseHandle(read_pipe);
        return {};
    }
    CloseHandle(write_pipe);

    std::string output;
    char buffer[1024];
    DWORD read = 0;
    while (ReadFile(read_pipe, buffer, sizeof(buffer), &read, nullptr) && read > 0) {
        output.append(buffer, buffer + read);
    }
    WaitForSingleObject(pi.hProcess, 10000);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    CloseHandle(read_pipe);
    return output;
}

std::string to_lower(std::string value) {
    for (char& c : value) {
        c = static_cast<char>(::tolower(static_cast<unsigned char>(c)));
    }
    return value;
}

bool has_word_wg(const std::string& lower) {
    for (size_t i = 0; i + 1 < lower.size(); ++i) {
        if (lower[i] != 'w' || lower[i + 1] != 'g') {
            continue;
        }
        const bool left_ok = i == 0 || !std::isalnum(static_cast<unsigned char>(lower[i - 1]));
        const bool right_ok = i + 2 >= lower.size() || !std::isalnum(static_cast<unsigned char>(lower[i + 2]));
        if (left_ok && right_ok) {
            return true;
        }
    }
    return false;
}

bool should_skip_adapter(const std::string& name) {
    const std::string lower = to_lower(name);
    const char* keep[] = {"radmin", "tailscale", "wireguard"};
    for (const char* token : keep) {
        if (lower.find(token) != std::string::npos) {
            return false;
        }
    }
    const char* skips[] = {"loopback", "vethernet", "vmware", "hyper-v", "virtualbox", "virtual"};
    for (const char* token : skips) {
        if (lower.find(token) != std::string::npos) {
            return true;
        }
    }
    return false;
}

std::optional<std::string> classify_adapter(const std::string& name, const std::string& ip) {
    const std::string lower = to_lower(name);
    if (is_radmin_ip(ip) || lower.find("radmin") != std::string::npos) {
        return std::string("radmin");
    }
    if (is_tailscale_ip(ip) || lower.find("tailscale") != std::string::npos) {
        return std::string("tailscale");
    }
    if (lower.find("wireguard") != std::string::npos || has_word_wg(lower) || lower.rfind("wg-", 0) == 0) {
        return std::string("wireguard");
    }
    if (is_private_ip(ip)) {
        return std::string("lan");
    }
    return std::nullopt;
}

std::string network_type_label(const std::string& network_type) {
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

std::optional<std::string> lan_from_udp() {
    WSADATA wsa{};
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        return std::nullopt;
    }
    SOCKET sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock == INVALID_SOCKET) {
        WSACleanup();
        return std::nullopt;
    }
    sockaddr_in dest{};
    dest.sin_family = AF_INET;
    dest.sin_port = htons(80);
    InetPtonA(AF_INET, "8.8.8.8", &dest.sin_addr);
    std::optional<std::string> result;
    if (connect(sock, reinterpret_cast<sockaddr*>(&dest), sizeof(dest)) == 0) {
        sockaddr_in local{};
        int len = sizeof(local);
        if (getsockname(sock, reinterpret_cast<sockaddr*>(&local), &len) == 0) {
            char buf[INET_ADDRSTRLEN]{};
            InetNtopA(AF_INET, &local.sin_addr, buf, sizeof(buf));
            const std::string candidate = buf;
            if (is_private_ip(candidate) && !is_radmin_ip(candidate)) {
                result = candidate;
            }
        }
    }
    closesocket(sock);
    WSACleanup();
    return result;
}

unsigned ip_to_u32(const std::string& ip) {
    unsigned a = 0, b = 0, c = 0, d = 0;
    std::sscanf(ip.c_str(), "%u.%u.%u.%u", &a, &b, &c, &d);
    return (a << 24) | (b << 16) | (c << 8) | d;
}

std::string u32_to_ip(unsigned value) {
    std::ostringstream oss;
    oss << ((value >> 24) & 0xFF) << '.' << ((value >> 16) & 0xFF) << '.' << ((value >> 8) & 0xFF) << '.'
        << (value & 0xFF);
    return oss.str();
}

std::vector<std::string> get_ips_of_type(const std::string& network_type) {
    std::vector<std::string> ips;
    std::set<std::string> seen;
    for (const auto& iface : list_local_interfaces()) {
        if (iface.network_type != network_type || seen.count(iface.ip)) {
            continue;
        }
        seen.insert(iface.ip);
        ips.push_back(iface.ip);
    }
    return ips;
}

}  // namespace

std::vector<LocalInterface> parse_ipconfig_interfaces(const std::string& text) {
    std::istringstream stream(text);
    std::string line;
    std::string current_adapter;
    std::vector<LocalInterface> results;
    std::set<std::string> seen_ips;
    static const std::regex re(R"(IPv4[^:]*:\s*([\d.]+))", std::regex::icase);

    while (std::getline(stream, line)) {
        if (!line.empty() && line[0] != ' ' && line[0] != '\t') {
            current_adapter = line;
            while (!current_adapter.empty() &&
                   (current_adapter.back() == '\r' || current_adapter.back() == ':')) {
                current_adapter.pop_back();
            }
            continue;
        }
        if (current_adapter.empty() || should_skip_adapter(current_adapter)) {
            continue;
        }
        std::smatch match;
        if (!std::regex_search(line, match, re)) {
            continue;
        }
        const std::string candidate = match[1].str();
        if (candidate.rfind("169.254.", 0) == 0 || seen_ips.count(candidate)) {
            continue;
        }

        const auto network_type = classify_adapter(current_adapter, candidate);
        if (!network_type) {
            continue;
        }

        LocalInterface iface;
        iface.name = current_adapter;
        iface.ip = candidate;
        iface.network_type = *network_type;
        seen_ips.insert(candidate);
        results.push_back(std::move(iface));
    }
    return results;
}

std::vector<LocalInterface> list_local_interfaces() {
    std::vector<LocalInterface> interfaces = parse_ipconfig_interfaces(run_ipconfig());
    if (const auto dword = read_radmin_reg_ipv4()) {
        const std::string radmin_ip = dword_to_ip(*dword);
        bool found = false;
        for (const auto& iface : interfaces) {
            if (iface.ip == radmin_ip) {
                found = true;
                break;
            }
        }
        if (!found) {
            interfaces.insert(interfaces.begin(), LocalInterface{"Radmin VPN", radmin_ip, "radmin"});
        }
    }
    return interfaces;
}

std::optional<std::string> get_radmin_ip() {
    if (const auto dword = read_radmin_reg_ipv4()) {
        return dword_to_ip(*dword);
    }
    for (const auto& iface : list_local_interfaces()) {
        if (iface.network_type == "radmin") {
            return iface.ip;
        }
    }
    return std::nullopt;
}

std::vector<std::string> get_lan_ips() {
    std::vector<std::string> ips;
    std::set<std::string> seen;
    for (const auto& iface : list_local_interfaces()) {
        if (iface.network_type != "lan" || seen.count(iface.ip)) {
            continue;
        }
        seen.insert(iface.ip);
        ips.push_back(iface.ip);
    }

    if (auto preferred = lan_from_udp()) {
        auto it = std::find(ips.begin(), ips.end(), *preferred);
        if (it != ips.end()) {
            ips.erase(it);
            ips.insert(ips.begin(), *preferred);
        } else if (!seen.count(*preferred)) {
            ips.insert(ips.begin(), *preferred);
        }
    }
    return ips;
}

std::optional<std::string> get_lan_ip() {
    const auto ips = get_lan_ips();
    if (ips.empty()) {
        return std::nullopt;
    }
    return ips.front();
}

std::vector<std::string> get_local_ips(const std::string& network_type) {
    if (network_type == "lan") {
        return get_lan_ips();
    }
    return get_ips_of_type(network_type);
}

std::optional<std::string> get_local_ip(const std::string& network_type) {
    const auto ips = get_local_ips(network_type);
    if (ips.empty()) {
        return std::nullopt;
    }
    return ips.front();
}

std::vector<LocalInterface> get_monitored_interfaces(
    const std::unordered_map<std::string, bool>& monitored_adapters) {
    std::vector<LocalInterface> result;
    for (const auto& iface : list_local_interfaces()) {
        if (is_adapter_monitored(iface, monitored_adapters)) {
            result.push_back(iface);
        }
    }
    return result;
}

std::vector<std::string> get_monitored_ips(
    const std::string& network_type,
    const std::unordered_map<std::string, bool>& monitored_adapters) {
    std::vector<std::string> ips;
    std::set<std::string> seen;
    for (const auto& iface : list_local_interfaces()) {
        if (iface.network_type != network_type) {
            continue;
        }
        if (!is_adapter_monitored(iface, monitored_adapters)) {
            continue;
        }
        if (seen.count(iface.ip)) {
            continue;
        }
        seen.insert(iface.ip);
        ips.push_back(iface.ip);
    }

    if (network_type == "lan") {
        if (auto preferred = lan_from_udp()) {
            auto it = std::find(ips.begin(), ips.end(), *preferred);
            if (it != ips.end()) {
                ips.erase(it);
                ips.insert(ips.begin(), *preferred);
            }
        }
    }
    return ips;
}

std::string format_local_interfaces(const std::vector<LocalInterface>& interfaces) {
    if (interfaces.empty()) {
        return "Nenhuma rede detectada";
    }
    std::ostringstream oss;
    for (size_t i = 0; i < interfaces.size(); ++i) {
        if (i > 0) {
            oss << " · ";
        }
        const auto& iface = interfaces[i];
        const std::string label =
            iface.network_type == "lan" ? iface.name : network_type_label(iface.network_type);
        oss << label << ": " << iface.ip;
    }
    return oss.str();
}

std::string format_local_interfaces() { return format_local_interfaces(list_local_interfaces()); }

std::string subnet_prefix_24(const std::string& ip) {
    const unsigned base = ip_to_u32(ip) & 0xFFFFFF00u;
    return u32_to_ip(base) + "/24";
}

std::vector<std::string> unique_scan_ips(const std::vector<std::string>& local_ips) {
    std::vector<std::string> result;
    std::set<std::string> seen_subnets;
    for (const auto& ip : local_ips) {
        const std::string key = subnet_prefix_24(ip);
        if (seen_subnets.count(key)) {
            continue;
        }
        seen_subnets.insert(key);
        result.push_back(ip);
    }
    return result;
}

std::set<std::string> skip_ips_for_network(const std::string& network_type, const std::string& local_ip) {
    std::set<std::string> skipped{local_ip};
    if (network_type == "radmin") {
        skipped.insert("26.0.0.1");
    } else {
        const unsigned gateway = (ip_to_u32(local_ip) & 0xFFFFFF00u) + 1;
        skipped.insert(u32_to_ip(gateway));
    }
    return skipped;
}

std::vector<Peer> discover_peers(
    const std::string& local_ip,
    const std::set<std::string>& known_ips,
    const std::set<std::string>& skip_ips,
    const std::atomic_bool* stop) {
    const unsigned base = ip_to_u32(local_ip) & 0xFFFFFF00u;
    std::vector<std::string> candidates;
    candidates.reserve(254);
    for (unsigned host = 1; host <= 254; ++host) {
        const std::string ip = u32_to_ip(base + host);
        if (known_ips.count(ip) || skip_ips.count(ip) || ip == local_ip) {
            continue;
        }
        candidates.push_back(ip);
    }

    std::vector<Peer> discovered;
    std::mutex mutex;
    std::atomic<size_t> next{0};
    const unsigned workers = 32;
    std::vector<std::thread> threads;
    threads.reserve(workers);

    for (unsigned i = 0; i < workers; ++i) {
        threads.emplace_back([&]() {
            while (true) {
                if (stop != nullptr && stop->load()) {
                    break;
                }
                const size_t index = next.fetch_add(1);
                if (index >= candidates.size()) {
                    break;
                }
                const std::string& ip = candidates[index];
                if (!ping_host(ip, 800)) {
                    continue;
                }
                if (stop != nullptr && stop->load()) {
                    break;
                }
                if (known_ips.count(ip)) {
                    continue;
                }
                Peer peer;
                peer.ip = ip;
                const std::string name = resolve_hostname(ip);
                peer.name = name.empty() ? ip : name;
                std::lock_guard lock(mutex);
                discovered.push_back(std::move(peer));
            }
        });
    }
    for (auto& thread : threads) {
        thread.join();
    }
    return discovered;
}

}  // namespace nm
