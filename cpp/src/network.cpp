#include "network.hpp"

#include "ping.hpp"
#include "nlohmann_json.hpp"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <iphlpapi.h>

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

int mask_to_prefixlen(const std::string& mask) {
    unsigned a = 0, b = 0, c = 0, d = 0;
    if (std::sscanf(mask.c_str(), "%u.%u.%u.%u", &a, &b, &c, &d) != 4) {
        return kDefaultPrefixlen;
    }
    const unsigned value = (a << 24) | (b << 16) | (c << 8) | d;
    if (value == 0) {
        return 0;
    }
    // Conta bits 1 contíguos a partir do MSB.
    int prefix = 0;
    unsigned bit = 0x80000000u;
    while (bit && (value & bit)) {
        ++prefix;
        bit >>= 1;
    }
    // Máscara inválida (buracos) → default.
    unsigned expected = prefix == 0 ? 0u : (0xFFFFFFFFu << (32 - prefix));
    if (value != expected) {
        return kDefaultPrefixlen;
    }
    return prefix;
}

int effective_scan_prefixlen(int prefixlen) {
    int plen = prefixlen;
    if (plen < 0) {
        plen = 0;
    }
    if (plen > 32) {
        plen = 32;
    }
    if (plen < kMinScanPrefixlen) {
        return kDefaultPrefixlen;
    }
    return plen;
}

bool send_arp(const std::string& dest_ip, const std::string& src_ip) {
    // SendARP espera IPAddr no formato de inet_addr (bytes de rede em DWORD LE).
    auto to_ipaddr = [](const std::string& ip) -> ULONG {
        unsigned a = 0, b = 0, c = 0, d = 0;
        if (std::sscanf(ip.c_str(), "%u.%u.%u.%u", &a, &b, &c, &d) != 4) {
            return 0;
        }
        return (static_cast<ULONG>(d) << 24) | (static_cast<ULONG>(c) << 16) |
               (static_cast<ULONG>(b) << 8) | static_cast<ULONG>(a);
    };
    ULONG mac[2]{};
    ULONG mac_len = 6;
    return SendARP(to_ipaddr(dest_ip), to_ipaddr(src_ip), mac, &mac_len) == NO_ERROR;
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
    std::string pending_ip;
    int pending_prefix = kDefaultPrefixlen;
    static const std::regex re_ip(R"(IPv4[^:]*:\s*([\d.]+))", std::regex::icase);
    static const std::regex re_mask(
        R"((?:Subnet Mask|M[aá]scara(?: de Sub-rede)?)\s*(?:\.|\s)*:\s*([\d.]+))",
        std::regex::icase);

    auto flush_pending = [&]() {
        if (pending_ip.empty() || current_adapter.empty()) {
            pending_ip.clear();
            pending_prefix = kDefaultPrefixlen;
            return;
        }
        if (seen_ips.count(pending_ip) || pending_ip.rfind("169.254.", 0) == 0) {
            pending_ip.clear();
            pending_prefix = kDefaultPrefixlen;
            return;
        }
        const auto network_type = classify_adapter(current_adapter, pending_ip);
        if (!network_type) {
            pending_ip.clear();
            pending_prefix = kDefaultPrefixlen;
            return;
        }
        LocalInterface iface;
        iface.name = current_adapter;
        iface.ip = pending_ip;
        iface.network_type = *network_type;
        iface.prefixlen = pending_prefix;
        seen_ips.insert(pending_ip);
        results.push_back(std::move(iface));
        pending_ip.clear();
        pending_prefix = kDefaultPrefixlen;
    };

    while (std::getline(stream, line)) {
        if (!line.empty() && line[0] != ' ' && line[0] != '\t') {
            flush_pending();
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
        if (!pending_ip.empty() && std::regex_search(line, match, re_mask)) {
            pending_prefix = mask_to_prefixlen(match[1].str());
            continue;
        }
        if (!std::regex_search(line, match, re_ip)) {
            continue;
        }
        flush_pending();
        pending_ip = match[1].str();
        pending_prefix = kDefaultPrefixlen;
    }
    flush_pending();
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
            interfaces.insert(
                interfaces.begin(), LocalInterface{"Radmin VPN", radmin_ip, "radmin", 8});
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

int prefixlen_for_local_ip(const std::string& ip) {
    for (const auto& iface : list_local_interfaces()) {
        if (iface.ip == ip) {
            return iface.prefixlen;
        }
    }
    return kDefaultPrefixlen;
}

std::string subnet_prefix(const std::string& ip, int prefixlen) {
    int use = prefixlen;
    if (use < 0) {
        use = kDefaultPrefixlen;
    }
    if (use > 32) {
        use = 32;
    }
    const unsigned host = ip_to_u32(ip);
    const unsigned mask = use == 0 ? 0u : (0xFFFFFFFFu << (32 - use));
    return u32_to_ip(host & mask) + "/" + std::to_string(use);
}

std::string scan_subnet_prefix(const std::string& ip, int prefixlen) {
    const int raw = prefixlen < 0 ? prefixlen_for_local_ip(ip) : prefixlen;
    return subnet_prefix(ip, effective_scan_prefixlen(raw));
}

std::string subnet_prefix_24(const std::string& ip) { return subnet_prefix(ip, 24); }

std::vector<std::string> unique_scan_ips(const std::vector<std::string>& local_ips) {
    std::vector<std::string> result;
    std::set<std::string> seen_subnets;
    for (const auto& ip : local_ips) {
        const std::string key = scan_subnet_prefix(ip);
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
        skipped.insert("26.255.255.255");
    } else {
        const std::string subnet = scan_subnet_prefix(local_ip);
        const auto slash = subnet.find('/');
        const unsigned base = ip_to_u32(slash == std::string::npos ? local_ip : subnet.substr(0, slash));
        skipped.insert(u32_to_ip(base + 1));
    }
    return skipped;
}

std::vector<std::string> subnet_host_candidates(
    const std::string& local_ip,
    const std::set<std::string>& excluded,
    int prefixlen) {
    const int raw = prefixlen < 0 ? prefixlen_for_local_ip(local_ip) : prefixlen;
    const int plen = effective_scan_prefixlen(raw);
    const unsigned host = ip_to_u32(local_ip);
    const unsigned mask = plen == 0 ? 0u : (0xFFFFFFFFu << (32 - plen));
    const unsigned base = host & mask;
    const unsigned host_bits = 32u - static_cast<unsigned>(plen);
    const unsigned max_host = host_bits >= 32 ? 0xFFFFFFFFu : ((1u << host_bits) - 1u);

    std::vector<std::string> candidates;
    if (max_host < 2) {
        return candidates;
    }
    candidates.reserve(static_cast<size_t>(max_host - 1));
    for (unsigned offset = 1; offset < max_host; ++offset) {
        const std::string ip = u32_to_ip(base + offset);
        if (ip == local_ip || excluded.count(ip)) {
            continue;
        }
        candidates.push_back(ip);
    }
    return candidates;
}

std::vector<std::string> arp_probe_hosts(
    const std::vector<std::string>& candidates,
    const std::string& src_ip,
    const std::atomic_bool* stop) {
    if (candidates.empty()) {
        return {};
    }
    std::vector<std::string> alive;
    std::mutex mutex;
    std::atomic<size_t> next{0};
    const unsigned workers = 64;
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
                if (send_arp(ip, src_ip)) {
                    std::lock_guard lock(mutex);
                    alive.push_back(ip);
                }
            }
        });
    }
    for (auto& thread : threads) {
        thread.join();
    }
    return alive;
}

std::string run_arp() {
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
    wchar_t cmd[] = L"arp -a";
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

std::string normalize_mac(std::string mac) {
    for (char& c : mac) {
        if (c == ':') {
            c = '-';
        }
        c = static_cast<char>(::tolower(static_cast<unsigned char>(c)));
    }
    return mac;
}

bool is_skipped_arp_mac(const std::string& mac) {
    return mac == "00-00-00-00-00-00" || mac == "ff-ff-ff-ff-ff-ff";
}

std::unordered_map<std::string, std::vector<std::string>> parse_arp_neighbors(const std::string& text) {
    std::unordered_map<std::string, std::vector<std::string>> by_iface;
    std::unordered_map<std::string, std::set<std::string>> seen_by_iface;
    std::string current_iface;
    const std::regex iface_re(R"(^\s*Interface:\s*([\d.]+))", std::regex::icase);
    const std::regex entry_re(
        R"(^\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})\s+(\S+))",
        std::regex::icase);

    std::istringstream stream(text);
    std::string line;
    while (std::getline(stream, line)) {
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        std::smatch match;
        if (std::regex_search(line, match, iface_re)) {
            current_iface = match[1].str();
            by_iface.emplace(current_iface, std::vector<std::string>{});
            seen_by_iface.emplace(current_iface, std::set<std::string>{});
            continue;
        }
        if (current_iface.empty() || !std::regex_search(line, match, entry_re)) {
            continue;
        }
        const std::string ip = match[1].str();
        const std::string mac = normalize_mac(match[2].str());
        const std::string type_lower = to_lower(match[3].str());
        if (is_skipped_arp_mac(mac)) {
            continue;
        }
        if (type_lower.find("invalid") != std::string::npos ||
            type_lower.find("incomplet") != std::string::npos ||
            type_lower.find("inval") != std::string::npos) {
            continue;
        }
        auto& seen = seen_by_iface[current_iface];
        if (seen.count(ip)) {
            continue;
        }
        seen.insert(ip);
        by_iface[current_iface].push_back(ip);
    }
    return by_iface;
}

std::vector<std::string> radmin_neighbor_ips_from_arp(
    const std::string& arp_text,
    const std::vector<std::string>& local_ips,
    const std::set<std::string>& skip_ips) {
    std::set<std::string> local_set(local_ips.begin(), local_ips.end());
    std::set<std::string> skipped = skip_ips;
    skipped.insert(local_set.begin(), local_set.end());
    skipped.insert("26.0.0.1");
    skipped.insert("26.255.255.255");

    const auto by_iface = parse_arp_neighbors(arp_text);
    std::vector<std::string> results;
    std::set<std::string> seen;

    auto consider = [&](const std::string& ip) {
        if (!is_radmin_ip(ip) || skipped.count(ip) || seen.count(ip)) {
            return;
        }
        seen.insert(ip);
        results.push_back(ip);
    };

    for (const auto& iface_ip : local_set) {
        const auto it = by_iface.find(iface_ip);
        if (it == by_iface.end()) {
            continue;
        }
        for (const auto& neighbor : it->second) {
            consider(neighbor);
        }
    }

    if (results.empty()) {
        for (const auto& [iface_ip, neighbors] : by_iface) {
            (void)iface_ip;
            for (const auto& neighbor : neighbors) {
                consider(neighbor);
            }
        }
    }
    return results;
}

std::vector<std::string> list_radmin_arp_neighbors(
    const std::vector<std::string>& local_ips,
    const std::set<std::string>& skip_ips) {
    return radmin_neighbor_ips_from_arp(run_arp(), local_ips, skip_ips);
}

std::vector<Peer> discover_peers(
    const std::string& local_ip,
    const std::set<std::string>& known_ips,
    const std::set<std::string>& skip_ips,
    const std::atomic_bool* stop) {
    std::set<std::string> excluded = known_ips;
    excluded.insert(skip_ips.begin(), skip_ips.end());
    excluded.insert(local_ip);
    const auto candidates = subnet_host_candidates(local_ip, excluded);

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

std::vector<Peer> discover_lan_peers(
    const std::string& local_ip,
    const std::set<std::string>& known_ips,
    const std::set<std::string>& skip_ips,
    const std::atomic_bool* stop) {
    std::set<std::string> excluded = known_ips;
    excluded.insert(skip_ips.begin(), skip_ips.end());
    excluded.insert(local_ip);
    const auto candidates = subnet_host_candidates(local_ip, excluded);
    const auto alive = arp_probe_hosts(candidates, local_ip, stop);

    std::vector<Peer> discovered;
    for (const auto& ip : alive) {
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
        discovered.push_back(std::move(peer));
    }
    return discovered;
}

std::vector<Peer> discover_radmin_peers(
    const std::vector<std::string>& local_ips,
    const std::set<std::string>& known_ips,
    const std::set<std::string>& skip_ips,
    const std::atomic_bool* stop) {
    if (local_ips.empty()) {
        return {};
    }

    std::set<std::string> skipped = skip_ips;
    for (const auto& local_ip : local_ips) {
        const auto extra = skip_ips_for_network("radmin", local_ip);
        skipped.insert(extra.begin(), extra.end());
    }

    std::vector<std::string> candidates;
    for (const auto& ip : list_radmin_arp_neighbors(local_ips, skipped)) {
        if (known_ips.count(ip) || skipped.count(ip)) {
            continue;
        }
        candidates.push_back(ip);
    }

    std::vector<Peer> discovered;
    for (const auto& ip : candidates) {
        if (stop != nullptr && stop->load()) {
            break;
        }
        if (!ping_host(ip, 800)) {
            continue;
        }
        if (known_ips.count(ip)) {
            continue;
        }
        Peer peer;
        peer.ip = ip;
        const std::string name = resolve_hostname(ip);
        peer.name = name.empty() ? ip : name;
        discovered.push_back(std::move(peer));
    }
    return discovered;
}

std::string run_command_capture(const std::wstring& command) {
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
    std::wstring mutable_cmd = command;
    if (!CreateProcessW(
            nullptr, mutable_cmd.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi)) {
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
    WaitForSingleObject(pi.hProcess, 15000);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    CloseHandle(read_pipe);
    return output;
}

std::vector<std::pair<std::string, std::string>> parse_tailscale_status_peers(const std::string& json_text) {
    std::vector<std::pair<std::string, std::string>> results;
    try {
        const auto payload = nlohmann::json::parse(json_text);
        if (!payload.contains("Peer") || !payload["Peer"].is_object()) {
            return results;
        }
        std::set<std::string> seen;
        for (auto it = payload["Peer"].begin(); it != payload["Peer"].end(); ++it) {
            const auto& peer = it.value();
            if (!peer.is_object() || !peer.contains("TailscaleIPs") || !peer["TailscaleIPs"].is_array()) {
                continue;
            }
            if (peer["TailscaleIPs"].empty()) {
                continue;
            }
            const std::string ip = peer["TailscaleIPs"][0].get<std::string>();
            if (!is_tailscale_ip(ip) || seen.count(ip)) {
                continue;
            }
            std::string host = peer.value("HostName", "");
            std::string dns = peer.value("DNSName", "");
            while (!dns.empty() && dns.back() == '.') {
                dns.pop_back();
            }
            std::string name = host;
            if (name.empty() && !dns.empty()) {
                const auto dot = dns.find('.');
                name = dot == std::string::npos ? dns : dns.substr(0, dot);
            }
            if (name.empty()) {
                name = ip;
            }
            seen.insert(ip);
            results.emplace_back(ip, name);
        }
    } catch (...) {
        return {};
    }
    return results;
}

std::vector<std::pair<std::string, std::string>> list_tailscale_status_peers() {
    const std::string output = run_command_capture(L"tailscale status --json");
    if (output.empty()) {
        return {};
    }
    return parse_tailscale_status_peers(output);
}

std::vector<std::string> parse_wg_show_dump_peers(
    const std::string& text,
    const std::set<std::string>& local_ips) {
    std::vector<std::string> results;
    std::set<std::string> seen;
    std::istringstream stream(text);
    std::string line;
    while (std::getline(stream, line)) {
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        if (line.empty() || line[0] == '#') {
            continue;
        }
        std::vector<std::string> parts;
        std::string part;
        std::istringstream row(line);
        while (std::getline(row, part, '\t')) {
            parts.push_back(part);
        }
        if (parts.size() == 5 || parts.size() < 8) {
            continue;
        }
        std::istringstream allowed(parts[4]);
        std::string token;
        while (std::getline(allowed, token, ',')) {
            while (!token.empty() && (token.front() == ' ' || token.front() == '\t')) {
                token.erase(token.begin());
            }
            while (!token.empty() && (token.back() == ' ' || token.back() == '\t')) {
                token.pop_back();
            }
            const auto slash = token.find('/');
            if (slash == std::string::npos) {
                continue;
            }
            int plen = 0;
            try {
                plen = std::stoi(token.substr(slash + 1));
            } catch (...) {
                continue;
            }
            if (plen != 32) {
                continue;
            }
            const std::string ip = token.substr(0, slash);
            unsigned a = 0, b = 0, c = 0, d = 0;
            if (std::sscanf(ip.c_str(), "%u.%u.%u.%u", &a, &b, &c, &d) != 4) {
                continue;
            }
            if (local_ips.count(ip) || seen.count(ip)) {
                continue;
            }
            seen.insert(ip);
            results.push_back(ip);
        }
    }
    return results;
}

std::vector<std::string> list_wireguard_peer_ips(const std::vector<std::string>& local_ips) {
    const std::string output = run_command_capture(L"wg show all dump");
    if (output.empty()) {
        return {};
    }
    return parse_wg_show_dump_peers(output, std::set<std::string>(local_ips.begin(), local_ips.end()));
}

std::vector<Peer> discover_tailscale_peers(
    const std::set<std::string>& known_ips,
    const std::set<std::string>& skip_ips,
    const std::atomic_bool* stop) {
    if (stop != nullptr && stop->load()) {
        return {};
    }
    const auto status_peers = list_tailscale_status_peers();
    std::vector<Peer> discovered;
    for (const auto& [ip, name] : status_peers) {
        if (stop != nullptr && stop->load()) {
            break;
        }
        if (known_ips.count(ip) || skip_ips.count(ip)) {
            continue;
        }
        Peer peer;
        peer.ip = ip;
        peer.name = name.empty() ? ip : name;
        discovered.push_back(std::move(peer));
    }
    return discovered;
}

std::vector<Peer> discover_wireguard_peers(
    const std::vector<std::string>& local_ips,
    const std::set<std::string>& known_ips,
    const std::set<std::string>& skip_ips,
    const std::atomic_bool* stop) {
    std::set<std::string> skipped = skip_ips;
    for (const auto& local_ip : local_ips) {
        const auto extra = skip_ips_for_network("wireguard", local_ip);
        skipped.insert(extra.begin(), extra.end());
    }

    const auto wg_ips = list_wireguard_peer_ips(local_ips);
    if (!wg_ips.empty()) {
        std::vector<Peer> discovered;
        for (const auto& ip : wg_ips) {
            if (stop != nullptr && stop->load()) {
                break;
            }
            if (known_ips.count(ip) || skipped.count(ip)) {
                continue;
            }
            if (!ping_host(ip, 800)) {
                continue;
            }
            Peer peer;
            peer.ip = ip;
            const std::string name = resolve_hostname(ip);
            peer.name = name.empty() ? ip : name;
            discovered.push_back(std::move(peer));
        }
        return discovered;
    }

    std::vector<Peer> found;
    std::set<std::string> known = known_ips;
    for (const auto& local_ip : local_ips) {
        if (stop != nullptr && stop->load()) {
            break;
        }
        auto discovered = discover_lan_peers(local_ip, known, skipped, stop);
        for (auto& peer : discovered) {
            known.insert(peer.ip);
            found.push_back(std::move(peer));
        }
    }
    return found;
}

std::vector<Peer> discover_network_peers(
    const std::string& network_type,
    const std::vector<std::string>& local_ips,
    const std::set<std::string>& known_ips,
    const std::atomic_bool* stop) {
    if (local_ips.empty() && network_type != "tailscale") {
        return {};
    }

    if (network_type == "radmin") {
        std::set<std::string> skipped;
        for (const auto& local_ip : local_ips) {
            const auto extra = skip_ips_for_network("radmin", local_ip);
            skipped.insert(extra.begin(), extra.end());
        }
        return discover_radmin_peers(local_ips, known_ips, skipped, stop);
    }
    if (network_type == "tailscale") {
        std::set<std::string> skipped;
        for (const auto& local_ip : local_ips) {
            const auto extra = skip_ips_for_network("tailscale", local_ip);
            skipped.insert(extra.begin(), extra.end());
            skipped.insert(local_ip);
        }
        return discover_tailscale_peers(known_ips, skipped, stop);
    }
    if (network_type == "wireguard") {
        return discover_wireguard_peers(local_ips, known_ips, {}, stop);
    }

    std::vector<Peer> found;
    std::set<std::string> known = known_ips;
    for (const auto& local_ip : unique_scan_ips(local_ips)) {
        if (stop != nullptr && stop->load()) {
            break;
        }
        auto discovered =
            discover_lan_peers(local_ip, known, skip_ips_for_network(network_type, local_ip), stop);
        for (auto& peer : discovered) {
            known.insert(peer.ip);
            found.push_back(std::move(peer));
        }
    }
    return found;
}

}  // namespace nm
