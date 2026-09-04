#include "test_assert.hpp"

#include "network.hpp"

#include <string>
#include <unordered_map>
#include <vector>

void test_is_radmin_ip() {
    NM_CHECK(nm::is_radmin_ip("26.0.0.1"));
    NM_CHECK(nm::is_radmin_ip("26.255.255.255"));
    NM_CHECK(!nm::is_radmin_ip("192.168.1.1"));
    NM_CHECK(!nm::is_radmin_ip("10.26.0.1"));
}

void test_is_private_ip() {
    NM_CHECK(nm::is_private_ip("10.0.0.1"));
    NM_CHECK(nm::is_private_ip("172.16.5.10"));
    NM_CHECK(nm::is_private_ip("192.168.0.50"));
    NM_CHECK(!nm::is_private_ip("26.0.0.2"));
    NM_CHECK(!nm::is_private_ip("8.8.8.8"));
    NM_CHECK(!nm::is_private_ip("169.254.1.1"));
    NM_CHECK(!nm::is_private_ip("not-an-ip"));
}

void test_is_tailscale_ip() {
    NM_CHECK(nm::is_tailscale_ip("100.64.0.1"));
    NM_CHECK(nm::is_tailscale_ip("100.127.255.255"));
    NM_CHECK(!nm::is_tailscale_ip("100.63.0.1"));
    NM_CHECK(!nm::is_tailscale_ip("192.168.1.1"));
}

void test_adapter_id_and_default_enabled() {
    NM_CHECK_EQ(nm::adapter_id("lan", "Ethernet"), std::string("lan:ethernet"));
    NM_CHECK(nm::default_adapter_enabled("lan"));
    NM_CHECK(!nm::default_adapter_enabled("tailscale"));

    const nm::LocalInterface tailscale{"Tailscale", "100.64.1.2", "tailscale"};
    const nm::LocalInterface ethernet{"Ethernet", "192.168.1.10", "lan"};
    NM_CHECK(!nm::is_adapter_monitored(tailscale, {}));
    NM_CHECK(nm::is_adapter_monitored(ethernet, {}));
    NM_CHECK(nm::is_adapter_monitored(tailscale, {{"tailscale:tailscale", true}}));
}

void test_subnet_prefix_24() {
    NM_CHECK_EQ(nm::subnet_prefix_24("26.0.0.42"), std::string("26.0.0.0/24"));
    NM_CHECK_EQ(nm::subnet_prefix_24("192.168.1.50"), std::string("192.168.1.0/24"));
}

void test_skip_ips_for_network() {
    const auto radmin = nm::skip_ips_for_network("radmin", "26.0.0.10");
    NM_CHECK(radmin.count("26.0.0.10") == 1);
    NM_CHECK(radmin.count("26.0.0.1") == 1);

    const auto lan = nm::skip_ips_for_network("lan", "192.168.1.50");
    NM_CHECK(lan.count("192.168.1.50") == 1);
    NM_CHECK(lan.count("192.168.1.1") == 1);
}

void test_parse_ipconfig_interfaces() {
    const std::string output =
        "Ethernet adapter Ethernet:\n"
        "\n"
        "   IPv4 Address. . . . . . . . . . . : 192.168.1.10\n"
        "\n"
        "Wireless LAN adapter Wi-Fi:\n"
        "\n"
        "   IPv4 Address. . . . . . . . . . . : 10.0.0.5\n"
        "\n"
        "Ethernet adapter Radmin VPN:\n"
        "\n"
        "   IPv4 Address. . . . . . . . . . . : 26.0.0.8\n"
        "\n"
        "Ethernet adapter Tailscale:\n"
        "\n"
        "   IPv4 Address. . . . . . . . . . . : 100.64.1.20\n"
        "\n"
        "Ethernet adapter WireGuard Tunnel:\n"
        "\n"
        "   IPv4 Address. . . . . . . . . . . : 10.8.0.2\n"
        "\n"
        "Ethernet adapter vEthernet (Default Switch):\n"
        "\n"
        "   IPv4 Address. . . . . . . . . . . : 172.20.80.1\n"
        "\n"
        "Ethernet adapter Local Area Connection:\n"
        "\n"
        "   IPv4 Address. . . . . . . . . . . : 169.254.12.34\n";

    const auto ifaces = nm::parse_ipconfig_interfaces(output);
    NM_CHECK(ifaces.size() == 5);
    NM_CHECK(ifaces[0].ip == "192.168.1.10");
    NM_CHECK(ifaces[0].network_type == "lan");
    NM_CHECK(ifaces[1].ip == "10.0.0.5");
    NM_CHECK(ifaces[1].network_type == "lan");
    NM_CHECK(ifaces[2].ip == "26.0.0.8");
    NM_CHECK(ifaces[2].network_type == "radmin");
    NM_CHECK(ifaces[3].ip == "100.64.1.20");
    NM_CHECK(ifaces[3].network_type == "tailscale");
    NM_CHECK(ifaces[4].ip == "10.8.0.2");
    NM_CHECK(ifaces[4].network_type == "wireguard");
}

void test_unique_scan_ips() {
    const std::vector<std::string> ips{"192.168.1.10", "192.168.1.20", "10.0.0.5"};
    const auto unique = nm::unique_scan_ips(ips);
    NM_CHECK(unique.size() == 2);
    NM_CHECK(unique[0] == "192.168.1.10");
    NM_CHECK(unique[1] == "10.0.0.5");
}

void test_format_local_interfaces() {
    const std::vector<nm::LocalInterface> ifaces{
        {"Radmin VPN", "26.0.0.8", "radmin"},
        {"Ethernet", "192.168.1.10", "lan"},
        {"Tailscale", "100.64.1.2", "tailscale"},
    };
    const std::string text = nm::format_local_interfaces(ifaces);
    NM_CHECK(text.find("Radmin VPN: 26.0.0.8") != std::string::npos);
    NM_CHECK(text.find("Ethernet: 192.168.1.10") != std::string::npos);
    NM_CHECK(text.find("Tailscale: 100.64.1.2") != std::string::npos);
}

void run_network_tests() {
    test_is_radmin_ip();
    test_is_private_ip();
    test_is_tailscale_ip();
    test_adapter_id_and_default_enabled();
    test_subnet_prefix_24();
    test_skip_ips_for_network();
    test_parse_ipconfig_interfaces();
    test_unique_scan_ips();
    test_format_local_interfaces();
}
