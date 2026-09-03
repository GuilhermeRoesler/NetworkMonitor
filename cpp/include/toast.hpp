#pragma once

#include "monitor.hpp"

#include <string>

namespace nm {

class ToastManager {
public:
    ToastManager();
    ~ToastManager();

    void show_transition(const PeerTransitionEvent& event);

private:
    std::wstring app_id_;
    bool initialized_{false};

    void ensure_shortcut();
};

}  // namespace nm
