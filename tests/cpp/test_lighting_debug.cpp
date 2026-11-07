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

        const easy3d::EntityHandle point = scene.create_entity("point");
        scene.add_light_component(point,
                                  easy3d::LightKind::Point,
                                  {1.0F, 0.2F, 0.1F, 1.0F},
                                  8.0F,
                                  12.0F,
                                  20.0F,
                                  45.0F,
                                  true,
                                  512,
                                  0.004F);
        scene.set_light_properties(point, 15.0F, 24.0F, 50.0F, true, 1024, 0.003F);
        const easy3d::LightComponent& point_light = scene.light_component(point);
        if (point_light.kind != easy3d::LightKind::Point ||
            point_light.range != 15.0F || !point_light.casts_shadows ||
            point_light.shadow_resolution != 1024 || point_light.shadow_bias != 0.003F) {
            std::cerr << "point light properties did not persist\n";
            return 11;
        }
        try {
            scene.set_light_properties(point, 10.0F, 60.0F, 40.0F, false, 0, 0.002F);
            std::cerr << "invalid spot cone angles were accepted\n";
            return 12;
        } catch (const std::invalid_argument&) {
            // Expected.
        }

        scene.set_procedural_skybox({0.1F, 0.2F, 0.8F, 1.0F},
                                    {0.6F, 0.7F, 0.9F, 1.0F},
                                    {0.02F, 0.03F, 0.05F, 1.0F},
                                    1.25F,
                                    30.0F);
        if (!scene.skybox().has_value() ||
            scene.skybox()->kind != easy3d::SkyboxKind::Procedural ||
            scene.skybox()->brightness != 1.25F) {
            std::cerr << "procedural skybox did not persist\n";
            return 13;
        }
        scene.clear_skybox();
        if (scene.skybox().has_value()) {
            std::cerr << "skybox disable did not persist\n";
            return 14;
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

        std::cout << "rix_lighting_debug_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "rix_lighting_debug_tests: FAIL: " << error.what() << '\n';
        return 10;
    }
}
