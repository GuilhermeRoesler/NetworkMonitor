#include "ping.hpp"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <iphlpapi.h>
#include <icmpapi.h>

#include <cctype>
#include <regex>
#include <string>
#include <vector>

namespace nm {
namespace {

std::string run_hidden(const std::wstring& command, DWORD timeout_ms) {
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
    const BOOL ok = CreateProcessW(
        nullptr,
        mutable_cmd.data(),
        nullptr,
        nullptr,
        TRUE,
        CREATE_NO_WINDOW,
        nullptr,
        nullptr,
        &si,
        &pi);

    CloseHandle(write_pipe);
    if (!ok) {
        CloseHandle(read_pipe);
        return {};
    }

    // Espera o processo com timeout; nunca bloquear para sempre em ReadFile
    // (ping.exe travado prendia o join do monitor e o terminal).
    std::string output;
    char buffer[512];
    const ULONGLONG deadline = GetTickCount64() + timeout_ms;
    for (;;) {
        DWORD available = 0;
        if (PeekNamedPipe(read_pipe, nullptr, 0, nullptr, &available, nullptr) && available > 0) {
            const DWORD to_read = available < sizeof(buffer) ? available : static_cast<DWORD>(sizeof(buffer));
            DWORD read = 0;
            if (ReadFile(read_pipe, buffer, to_read, &read, nullptr) && read > 0) {
                output.append(buffer, buffer + read);
            }
        }

        const DWORD wait = WaitForSingleObject(pi.hProcess, 20);
        if (wait == WAIT_OBJECT_0) {
            break;
        }
        if (GetTickCount64() >= deadline) {
            TerminateProcess(pi.hProcess, 1);
            WaitForSingleObject(pi.hProcess, 1000);
            break;
        }
    }

    DWORD available = 0;
    while (PeekNamedPipe(read_pipe, nullptr, 0, nullptr, &available, nullptr) && available > 0) {
        const DWORD to_read = available < sizeof(buffer) ? available : static_cast<DWORD>(sizeof(buffer));
        DWORD read = 0;
        if (!ReadFile(read_pipe, buffer, to_read, &read, nullptr) || read == 0) {
            break;
        }
        output.append(buffer, buffer + read);
    }

    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    CloseHandle(read_pipe);
    return output;
}

bool ping_via_icmp(const std::string& ip, int timeout_ms) {
    const HANDLE icmp = IcmpCreateFile();
    if (icmp == INVALID_HANDLE_VALUE) {
        return false;
    }

    IN_ADDR addr{};
    if (InetPtonA(AF_INET, ip.c_str(), &addr) != 1) {
        IcmpCloseHandle(icmp);
        return false;
    }

    constexpr int kPayload = 32;
    unsigned char request[kPayload]{};
    constexpr DWORD reply_size = sizeof(ICMP_ECHO_REPLY) + kPayload + 8;
    std::vector<unsigned char> reply(reply_size);

    const DWORD result = IcmpSendEcho(
        icmp,
        addr.S_un.S_addr,
        request,
        kPayload,
        nullptr,
        reply.data(),
        reply_size,
        static_cast<DWORD>(timeout_ms));

    IcmpCloseHandle(icmp);
    if (result == 0) {
        return false;
    }
    const auto* echo = reinterpret_cast<ICMP_ECHO_REPLY*>(reply.data());
    return echo->Status == IP_SUCCESS;
}

}  // namespace

bool ping_host(const std::string& ip, int timeout_ms) {
    if (ping_via_icmp(ip, timeout_ms)) {
        return true;
    }

    // Fallback alinhado à versão Python (timeout rígido = ping + folga)
    const DWORD process_timeout = static_cast<DWORD>(timeout_ms) + 2000u;
    const std::wstring cmd =
        L"ping -n 1 -w " + std::to_wstring(timeout_ms) + L" " + std::wstring(ip.begin(), ip.end());
    const std::string output = run_hidden(cmd, process_timeout);
    std::string lower = output;
    for (char& c : lower) {
        c = static_cast<char>(::tolower(static_cast<unsigned char>(c)));
    }
    return lower.find("ttl=") != std::string::npos || lower.find("ttl =") != std::string::npos;
}

std::string resolve_hostname(const std::string& ip) {
    const std::wstring cmd = L"ping -n 1 -a -w 1000 " + std::wstring(ip.begin(), ip.end());
    const std::string output = run_hidden(cmd, 4000);
    static const std::regex re(R"((?:Disparando|Pinging)\s+(\S+)\s+\[)", std::regex::icase);
    std::smatch match;
    if (!std::regex_search(output, match, re)) {
        return {};
    }
    std::string name = match[1].str();
    while (!name.empty() && name.back() == '.') {
        name.pop_back();
    }
    if (name.empty() || name == ip) {
        return {};
    }
    static const std::regex valid(R"(^[\w\-.]+$)");
    if (!std::regex_match(name, valid)) {
        return {};
    }
    return name;
}

}  // namespace nm
