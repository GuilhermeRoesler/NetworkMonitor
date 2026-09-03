#pragma once

#include <cstdlib>
#include <iostream>
#include <string>

namespace nm::test {

inline int& failure_count() {
    static int count = 0;
    return count;
}

inline void check(bool condition, const char* expression, const char* file, int line) {
    if (condition) {
        return;
    }
    ++failure_count();
    std::cerr << "FAIL " << file << ":" << line << " — " << expression << "\n";
}

}  // namespace nm::test

#define NM_CHECK(expr) ::nm::test::check(static_cast<bool>(expr), #expr, __FILE__, __LINE__)
#define NM_CHECK_EQ(a, b) \
    ::nm::test::check((a) == (b), #a " == " #b, __FILE__, __LINE__)
