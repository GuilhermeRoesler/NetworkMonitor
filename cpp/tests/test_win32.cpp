#include "test_assert.hpp"

#include "win32_helpers.hpp"

void run_win32_tests() {
    NM_CHECK_EQ(nm::snap_icon_size(1), 16);
    NM_CHECK_EQ(nm::snap_icon_size(16), 16);
    NM_CHECK_EQ(nm::snap_icon_size(17), 24);
    NM_CHECK_EQ(nm::snap_icon_size(32), 32);
    NM_CHECK_EQ(nm::snap_icon_size(33), 48);
    NM_CHECK_EQ(nm::snap_icon_size(64), 64);
    NM_CHECK_EQ(nm::snap_icon_size(300), 256);

    const auto at_96 = nm::window_icon_sizes(96);
    NM_CHECK_EQ(at_96.first, 32);
    NM_CHECK_EQ(at_96.second, 64);

    const auto at_144 = nm::window_icon_sizes(144);
    NM_CHECK(at_144.first >= 32);
    NM_CHECK(at_144.second > at_144.first);

    NM_CHECK_EQ(nm::kTrayIconSize, 64);
}
