#include "easy3d/scene.hpp"

#include <iostream>

int main() {
    try {
        easy3d::Scene scene("lighting and debug");
        easy3d::Camera camera = easy3d::Camera::look_at(
            {1.0F, 4.0F, 9.0F}, {0.0F, 1.0F, 0.0F});
        camera.vertical_fov_degrees = 50.0F;
        camera.near_plane = 0.2F;
        camera.far_plane = 250.0F;
        scene.set_camera(camera);
        if (!easy3d::almost_equal(scene.camera().position, {1.0F, 4.0F, 9.0F}) ||
            scene.camera().vertical_fov_degrees != 50.0F ||
            scene.camera().far_plane != 250.0F) {
            std::cerr << "scene camera assignment did not persist\n";
            return 1;
        }

        const easy3d::EntityHandle sun = scene.create_entity("sun");
        scene.add_light_component(sun,
                                  easy3d::LightKind::Directional,
                                  {1.0F, 0.8F, 0.6F, 1.0F},
                                  1.5F);
        if (!scene.has_light_component(sun) ||
            scene.light_component(sun).kind != easy3d::LightKind::Directional ||
            scene.light_component(sun).intensity != 1.5F) {
            std::cerr << "directional light component was not retained\n";
            return 2;
        }
        scene.set_light_color(sun, {0.5F, 0.6F, 0.7F, 1.0F});
        scene.set_light_intensity(sun, 2.0F);
        if (scene.light_component(sun).color != easy3d::Color{0.5F, 0.6F, 0.7F, 1.0F} ||
            scene.light_component(sun).intensity != 2.0F) {
            std::cerr << "light mutation did not persist\n";
            return 3;
        }
        try {
            scene.set_light_intensity(sun, -1.0F);
            std::cerr << "negative light intensity was accepted\n";
            return 4;
        } catch (const std::invalid_argument&) {
            // Expected.
        }
        try {
            scene.add_light_component(sun, easy3d::LightKind::Ambient);
            std::cerr << "duplicate singleton light was accepted\n";
            return 5;
        } catch (const easy3d::EngineError&) {
            // Expected.
        }

        scene.add_debug_line({{0.0F, 0.0F, 0.0F},
                              {1.0F, 0.0F, 0.0F},
                              {1.0F, 0.0F, 0.0F, 1.0F},
                              true});
        scene.add_debug_line({{0.0F, 0.0F, 0.0F},
                              {0.0F, 1.0F, 0.0F},
                              {0.0F, 1.0F, 0.0F, 1.0F},
                              false});
        if (scene.debug_lines().size() != 2 || scene.debug_lines()[1].depth_test) {
            std::cerr << "debug lines were not retained with depth state\n";
            return 6;
        }
        try {
            scene.add_debug_line({{1.0F, 1.0F, 1.0F}, {1.0F, 1.0F, 1.0F}});
            std::cerr << "zero-length debug line was accepted\n";
            return 7;
        } catch (const std::invalid_argument&) {
            // Expected.
        }

        scene.destroy_entity(sun);
        const easy3d::EntityHandle replacement = scene.create_entity("replacement");
        if (scene.has_light_component(replacement)) {
            std::cerr << "recycled entity slot retained a light component\n";
            return 8;
        }
        scene.clear();
        if (!scene.debug_lines().empty()) {
            std::cerr << "scene clear retained debug lines\n";
            return 9;
        }

        std::cout << "easy3d_lighting_debug_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "easy3d_lighting_debug_tests: FAIL: " << error.what() << '\n';
        return 10;
    }
}
