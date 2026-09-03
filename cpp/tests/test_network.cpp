#include "test_assert.hpp"

#include "network.hpp"

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

void run_network_tests() {
    test_is_radmin_ip();
    test_is_private_ip();
    test_subnet_prefix_24();
    test_skip_ips_for_network();
}
