#include "test_assert.hpp"

#include "config.hpp"
#include "paths.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

class TempAppDir {
public:
    TempAppDir() {
        root_ = fs::temp_directory_path() / ("nm-cpp-tests-" + std::to_string(std::rand()));
        fs::create_directories(root_);
        nm::set_app_dir_override(root_);
    }

    ~TempAppDir() {
        nm::set_app_dir_override(std::nullopt);
        std::error_code ec;
        fs::remove_all(root_, ec);
    }

    const fs::path& path() const { return root_; }

private:
    fs::path root_;
};

nm::Peer make_peer(const std::string& ip, const std::string& name, bool hidden = false) {
    nm::Peer peer;
    peer.ip = ip;
    peer.name = name;
    peer.hidden = hidden;
    return peer;
}

}  // namespace

void test_monitor_config_peer_order() {
    nm::MonitorConfig config;
    config.peer_order = {"26.0.0.3", "26.0.0.1", "26.0.0.2"};

    nm::NetworkConfig net;
    net.name = "Radmin VPN";
    net.network_type = "radmin";
    net.peers = {
        make_peer("26.0.0.2", "A"),
        make_peer("26.0.0.3", "B"),
        make_peer("26.0.0.1", "C"),
        make_peer("26.0.0.9", "Oculto", true),
    };
    config.networks.push_back(net);

    const auto ordered = config.all_peers();
    NM_CHECK_EQ(ordered.size(), static_cast<size_t>(4));
    NM_CHECK_EQ(ordered[0].ip, std::string("26.0.0.3"));
    NM_CHECK_EQ(ordered[1].ip, std::string("26.0.0.1"));
    NM_CHECK_EQ(ordered[2].ip, std::string("26.0.0.2"));
    NM_CHECK_EQ(ordered[3].ip, std::string("26.0.0.9"));

    NM_CHECK_EQ(config.visible_peers().size(), static_cast<size_t>(3));
    NM_CHECK_EQ(config.hidden_peers().size(), static_cast<size_t>(1));
}

void test_save_default_and_load_config() {
    TempAppDir tmp;
    NM_CHECK(!fs::exists(tmp.path() / "peers.json"));

    const auto config = nm::load_config();
    NM_CHECK(fs::exists(tmp.path() / "peers.json"));
    NM_CHECK_EQ(config.interval_seconds, 15);
    NM_CHECK(config.notifications_enabled);
    NM_CHECK_EQ(config.networks.size(), static_cast<size_t>(2));
    NM_CHECK_EQ(config.networks[0].network_type, std::string("radmin"));
    NM_CHECK_EQ(config.networks[1].network_type, std::string("lan"));
}

void test_load_sample_config_and_state() {
    TempAppDir tmp;
    {
        std::ofstream out(tmp.path() / "peers.json", std::ios::binary);
        out << R"({
  "interval_seconds": 20,
  "auto_discover": true,
  "scan_interval_seconds": 300,
  "notifications_enabled": false,
  "peer_order": ["26.0.0.9", "26.0.0.5", "26.0.0.2"],
  "networks": [
    {
      "name": "Radmin VPN",
      "type": "radmin",
      "enabled": true,
      "peers": [
        {"name": "PC-B", "ip": "26.0.0.5"},
        {"name": "PC-A", "ip": "26.0.0.2", "muted": true},
        {"name": "Oculto", "ip": "26.0.0.9", "hidden": true}
      ]
    }
  ]
})";
    }

    const auto config = nm::load_config();
    NM_CHECK_EQ(config.interval_seconds, 20);
    NM_CHECK(!config.notifications_enabled);
    NM_CHECK_EQ(config.visible_peers().size(), static_cast<size_t>(2));
    NM_CHECK_EQ(config.hidden_peers().size(), static_cast<size_t>(1));
    NM_CHECK(!config.peer_order.empty());
    NM_CHECK_EQ(config.peer_order.back(), std::string("26.0.0.9"));

    bool muted = false;
    for (const auto& peer : config.all_peers()) {
        if (peer.ip == "26.0.0.2") {
            muted = peer.muted;
        }
    }
    NM_CHECK(muted);

    nm::StateMap state{{"26.0.0.2", true}, {"26.0.0.9", true}, {"26.0.0.5", false}};
    nm::save_state(state, config);
    const auto loaded = nm::load_state();
    NM_CHECK(loaded.count("26.0.0.2") == 1);
    NM_CHECK(loaded.at("26.0.0.2"));
    NM_CHECK(loaded.count("26.0.0.9") == 0);
}

void test_persist_discovered_peers() {
    TempAppDir tmp;
    nm::save_default_config();

    std::vector<nm::Peer> discovered{make_peer("26.0.0.42", "Novo")};
    nm::persist_discovered_peers("Radmin VPN", discovered);

    const auto config = nm::load_config();
    bool found = false;
    for (const auto& peer : config.all_peers()) {
        if (peer.ip == "26.0.0.42" && peer.name == "Novo") {
            found = true;
        }
    }
    NM_CHECK(found);
}

void test_update_peer_actions() {
    TempAppDir tmp;
    {
        std::ofstream out(tmp.path() / "peers.json", std::ios::binary);
        out << R"({
  "interval_seconds": 15,
  "auto_discover": true,
  "scan_interval_seconds": 300,
  "notifications_enabled": true,
  "peer_order": ["26.0.0.2", "26.0.0.3", "26.0.0.9"],
  "networks": [
    {
      "name": "Radmin VPN",
      "type": "radmin",
      "enabled": true,
      "peers": [
        {"name": "PC-A", "ip": "26.0.0.2"},
        {"name": "PC-B", "ip": "26.0.0.3"},
        {"name": "Oculto", "ip": "26.0.0.9", "hidden": true}
      ]
    }
  ]
})";
    }

    NM_CHECK(nm::update_peer_name("26.0.0.2", "Notebook"));
    NM_CHECK(nm::set_peer_muted("26.0.0.2", true));
    NM_CHECK(nm::set_peer_hidden("26.0.0.3", true));
    nm::set_notifications_enabled(false);
    NM_CHECK(nm::move_peer("26.0.0.2", "26.0.0.3"));
    NM_CHECK(nm::move_peer_to_end("26.0.0.2"));

    const auto config = nm::load_config();
    NM_CHECK(!config.notifications_enabled);
    NM_CHECK_EQ(config.peer_order.front(), std::string("26.0.0.2"));

    bool renamed = false;
    bool muted = false;
    bool hidden = false;
    for (const auto& peer : config.all_peers()) {
        if (peer.ip == "26.0.0.2") {
            renamed = peer.name == "Notebook";
            muted = peer.muted;
        }
        if (peer.ip == "26.0.0.3") {
            hidden = peer.hidden;
        }
    }
    NM_CHECK(renamed);
    NM_CHECK(muted);
    NM_CHECK(hidden);
}

void run_config_tests() {
    test_monitor_config_peer_order();
    test_save_default_and_load_config();
    test_load_sample_config_and_state();
    test_persist_discovered_peers();
    test_update_peer_actions();
}
