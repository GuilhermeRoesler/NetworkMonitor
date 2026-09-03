#include "test_assert.hpp"

#include <cstdlib>
#include <ctime>
#include <iostream>

void run_network_tests();
void run_config_tests();

int main() {
    std::srand(static_cast<unsigned>(std::time(nullptr)));

    run_network_tests();
    run_config_tests();

    if (nm::test::failure_count() != 0) {
        std::cerr << nm::test::failure_count() << " falha(s) nos testes C++\n";
        return 1;
    }
    std::cout << "Todos os testes C++ passaram\n";
    return 0;
}
