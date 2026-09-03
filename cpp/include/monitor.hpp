#pragma once

#include "config.hpp"

#include <atomic>
#include <string>
#include <vector>

namespace nm {

StateMap check_peers(std::vector<Peer>& peers, const StateMap& previous, bool notifications_enabled);
void run_monitor_loop(std::atomic_bool& stop);
bool scan_network(const std::string& network_type);
void show_status();

}  // namespace nm
