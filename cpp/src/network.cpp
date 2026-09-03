#include "network.hpp"

#include "ping.hpp"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <iphlpapi.h>

#include <atomic>
#include <cctype>
#include <cstdio>
#include <mutex>
#include <regex>
#include <sstream>
#include <thread>
#include <vector>

namespace nm {
namespace {

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

std::string dword_to_ip(DWORD value) {
    // Registro Radmin guarda IPv4 em ordem de rede (big-endian dword)
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

std::optional<std::string> radmin_from_ipconfig() {
    const std::string text = run_ipconfig();
    std::istringstream stream(text);
    std::string line;
    bool in_block = false;
    std::vector<std::string> block;
    while (std::getline(stream, line)) {
        if (line.find("Radmin VPN") != std::string::npos) {
            in_block = true;
            block.clear();
            continue;
        }
        if (in_block) {
            if (line.empty() || (line.size() == 1 && line[0] == '\r')) {
                if (!block.empty()) {
                    break;
                }
            } else {
                block.push_back(line);
            }
        }
    }
    static const std::regex re(R"(IPv4[^:]*:\s*([\d.]+))", std::regex::icase);
    for (const auto& entry : block) {
        std::smatch match;
        if (std::regex_search(entry, match, re)) {
            return match[1].str();
        }
    }
    return std::nullopt;
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

std::optional<std::string> lan_from_ipconfig() {
    const std::string text = run_ipconfig();
    std::istringstream stream(text);
    std::string line;
    std::string current_adapter;
    static const std::regex re(R"(IPv4[^:]*:\s*([\d.]+))", std::regex::icase);

    while (std::getline(stream, line)) {
        if (!line.empty() && line[0] != ' ' && line[0] != '\t') {
            current_adapter = line;
            while (!current_adapter.empty() && (current_adapter.back() == '\r' || current_adapter.back() == ':')) {
                current_adapter.pop_back();
            }
            continue;
        }
        std::string adapter_lower = current_adapter;
        for (char& c : adapter_lower) {
            c = static_cast<char>(::tolower(static_cast<unsigned char>(c)));
        }
        const char* skips[] = {"radmin", "loopback", "virtual", "vethernet", "vmware", "hyper-v"};
        bool skip = false;
        for (const char* token : skips) {
            if (adapter_lower.find(token) != std::string::npos) {
                skip = true;
                break;
            }
        }
        if (skip) {
            continue;
        }
        std::smatch match;
        if (!std::regex_search(line, match, re)) {
            continue;
        }
        const std::string candidate = match[1].str();
        if (candidate.rfind("169.254.", 0) == 0) {
            continue;
        }
        if (is_private_ip(candidate) && !is_radmin_ip(candidate)) {
            return candidate;
        }
    }
    return std::nullopt;
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

}  // namespace

std::optional<std::string> get_radmin_ip() {
    if (const auto dword = read_radmin_reg_ipv4()) {
        return dword_to_ip(*dword);
    }
    return radmin_from_ipconfig();
}

std::optional<std::string> get_lan_ip() {
    if (auto ip = lan_from_udp()) {
        return ip;
    }
    return lan_from_ipconfig();
}

std::optional<std::string> get_local_ip(const std::string& network_type) {
    if (network_type == "lan") {
        return get_lan_ip();
    }
    return get_radmin_ip();
}

std::string subnet_prefix_24(const std::string& ip) {
    const unsigned base = ip_to_u32(ip) & 0xFFFFFF00u;
    return u32_to_ip(base) + "/24";
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
    const std::set<std::string>& skip_ips) {
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
                const size_t index = next.fetch_add(1);
                if (index >= candidates.size()) {
                    break;
                }
                const std::string& ip = candidates[index];
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
