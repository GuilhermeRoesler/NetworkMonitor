#pragma once

#include <string>

namespace nm {

void set_console_logging_enabled(bool enabled);
void log_message(const std::string& message);

}  // namespace nm
