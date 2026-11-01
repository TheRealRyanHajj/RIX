#include "easy3d/core.hpp"

#include <iostream>
#include <stdexcept>
#include <string_view>

int main() {
    if (std::string_view(easy3d::engine_version()) != "0.1.0") {
        std::cerr << "unexpected engine version\n";
        return 1;
    }
    if (easy3d::native_add(20, 22) != 42) {
        std::cerr << "native_add failed\n";
        return 2;
    }

    try {
        easy3d::Engine invalid({"Easy3D", 0, 720, true, 0.0});
        (void)invalid;
        std::cerr << "invalid dimensions were accepted\n";
        return 3;
    } catch (const std::invalid_argument&) {
        // Expected: validation is non-GPU and does not initialize SDL/bgfx.
    }

    easy3d::Engine engine;
    engine.stop();
    if (engine.is_running() || engine.frame_count() != 0) {
        std::cerr << "new Engine has invalid state\n";
        return 4;
    }

    std::cout << "easy3d_core_tests: PASS\n";
    return 0;
}

