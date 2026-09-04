#include "test_assert.hpp"

#include "network.hpp"

#include <string>
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
        "Ethernet adapter vEthernet (Default Switch):\n"
        "\n"
        "   IPv4 Address. . . . . . . . . . . : 172.20.80.1\n"
        "\n"
        "Ethernet adapter Local Area Connection:\n"
        "\n"
        "   IPv4 Address. . . . . . . . . . . : 169.254.12.34\n";

    const auto ifaces = nm::parse_ipconfig_interfaces(output);
    NM_CHECK(ifaces.size() == 3);
    NM_CHECK(ifaces[0].ip == "192.168.1.10");
    NM_CHECK(ifaces[0].network_type == "lan");
    NM_CHECK(ifaces[1].ip == "10.0.0.5");
    NM_CHECK(ifaces[1].network_type == "lan");
    NM_CHECK(ifaces[2].ip == "26.0.0.8");
    NM_CHECK(ifaces[2].network_type == "radmin");
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
    };
    const std::string text = nm::format_local_interfaces(ifaces);
    NM_CHECK(text.find("Radmin: 26.0.0.8") != std::string::npos);
    NM_CHECK(text.find("Ethernet: 192.168.1.10") != std::string::npos);
}

void run_network_tests() {
    test_is_radmin_ip();
    test_is_private_ip();
    test_subnet_prefix_24();
    test_skip_ips_for_network();
    test_parse_ipconfig_interfaces();
    test_unique_scan_ips();
    test_format_local_interfaces();
}
