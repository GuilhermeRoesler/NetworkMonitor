#include "logging.hpp"

#include "paths.hpp"

#include <fstream>
#include <iostream>
#include <mutex>

namespace nm {
namespace {

std::mutex g_log_mutex;
bool g_console_logging_enabled = false;

}  // namespace

void set_console_logging_enabled(bool enabled) {
    std::lock_guard lock(g_log_mutex);
    g_console_logging_enabled = enabled;
}

void log_message(const std::string& message) {
    std::lock_guard lock(g_log_mutex);

    std::ofstream out(log_path(), std::ios::app | std::ios::binary);
    if (out) {
        out << message << "\n";
    }

    if (g_console_logging_enabled) {
        std::cout << message << std::endl;
    }
}

}  // namespace nm
