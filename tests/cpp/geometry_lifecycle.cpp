#include "easy3d/core.hpp"

#include <chrono>
#include <exception>
#include <iostream>
#include <thread>

int main() {
    try {
        easy3d::EngineConfig config;
        config.title = "Easy3D indexed geometry diagnostic";
        config.width = 960;
        config.height = 540;
        config.vsync = false;
        config.fps_limit = 120.0;
        config.geometry_diagnostic = true;

        easy3d::Engine engine(config);
        std::jthread stopper([&engine] {
            std::this_thread::sleep_for(std::chrono::seconds(10));
            engine.stop();
        });
        engine.run();
        if (engine.frame_count() == 0) {
            std::cerr << "geometry diagnostic rendered zero frames\n";
            return 2;
        }
        std::cout << "easy3d_geometry_lifecycle: PASS frames=" << engine.frame_count() << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "easy3d_geometry_lifecycle: FAIL: " << error.what() << '\n';
        return 1;
    }
}
