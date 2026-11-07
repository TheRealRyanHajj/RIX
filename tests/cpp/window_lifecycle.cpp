#include "easy3d/core.hpp"

#include <chrono>
#include <iostream>
#include <thread>

int main() {
    easy3d::Engine engine({"RIX native lifecycle", 640, 360, false, 120.0});
    std::thread stopper([&engine] {
        std::this_thread::sleep_for(std::chrono::milliseconds(750));
        engine.stop();
    });
    engine.run();
    stopper.join();
    std::cout << "frames=" << engine.frame_count() << " running=" << engine.is_running() << '\n';
    return 0;
}
