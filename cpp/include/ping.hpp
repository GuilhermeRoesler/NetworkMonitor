#pragma once

#include <string>

namespace nm {

bool ping_host(const std::string& ip, int timeout_ms = 1000);
std::string resolve_hostname(const std::string& ip);

}  // namespace nm
