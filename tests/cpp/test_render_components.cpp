#include "easy3d/scene.hpp"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <system_error>

namespace {

class TemporaryDirectory final {
public:
    TemporaryDirectory() : path_(create()) {}
    ~TemporaryDirectory() {
        std::error_code ignored;
        std::filesystem::remove_all(path_, ignored);
    }
    [[nodiscard]] const std::filesystem::path& path() const noexcept { return path_; }

private:
    [[nodiscard]] static std::filesystem::path create() {
        const std::filesystem::path root = std::filesystem::temp_directory_path();
        std::random_device random;
        for (int attempt = 0; attempt < 32; ++attempt) {
            const auto ticks = std::chrono::high_resolution_clock::now()
                                   .time_since_epoch()
                                   .count();
            const auto candidate =
                root / ("easy3d_render_component_test_" + std::to_string(ticks) + "_" +
                        std::to_string(random()));
            std::error_code error;
            if (std::filesystem::create_directory(candidate, error)) {
                return candidate;
            }
        }
        throw std::runtime_error(
            "failed to create unique render-component-test directory");
    }

    std::filesystem::path path_;
};

} // namespace

int main() {
    try {
        easy3d::Scene scene("render components");
        const easy3d::EntityHandle first = scene.create_entity("first cube");
        const easy3d::EntityHandle second = scene.create_entity("second cube");
        scene.add_primitive_renderer(first,
                                     easy3d::RenderKind::Cube,
                                     {0.25F, 0.5F, 0.75F, 1.0F});
        scene.add_primitive_renderer(second, easy3d::RenderKind::Cube);

        const easy3d::RenderComponent& first_component = scene.render_component(first);
        const easy3d::RenderComponent& second_component = scene.render_component(second);
        if (!scene.has_render_component(first) || first_component.kind != easy3d::RenderKind::Cube ||
            !first_component.mesh || first_component.mesh.get() != second_component.mesh.get() ||
            first_component.model || first_component.texture) {
            std::cerr << "primitive components did not share their immutable mesh\n";
            return 1;
        }

        try {
            scene.add_primitive_renderer(first, easy3d::RenderKind::Sphere);
            std::cerr << "duplicate singleton render component was accepted\n";
            return 2;
        } catch (const easy3d::EngineError&) {
            // Expected.
        }

        scene.set_render_color(first, {0.8F, 0.2F, 0.1F, 0.5F});
        scene.set_render_lit(first, false);
        if (scene.render_component(first).material.color !=
                easy3d::Color{0.8F, 0.2F, 0.1F, 0.5F} ||
            scene.render_component(first).material.lit) {
            std::cerr << "render component color mutation did not persist\n";
            return 3;
        }
        scene.remove_render_component(first);
        if (scene.has_render_component(first)) {
            std::cerr << "render component removal did not persist\n";
            return 4;
        }
        try {
            (void)scene.render_component(first);
            std::cerr << "missing render component lookup did not fail\n";
            return 5;
        } catch (const easy3d::EngineError&) {
            // Expected.
        }

        scene.destroy_entity(second);
        const easy3d::EntityHandle replacement = scene.create_entity("replacement");
        if (scene.has_render_component(replacement)) {
            std::cerr << "recycled entity slot retained a render component\n";
            return 6;
        }

        TemporaryDirectory temporary;
        const std::filesystem::path model_path = temporary.path() / "model.obj";
        {
            std::ofstream model(model_path, std::ios::binary);
            model << "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n";
            if (!model) {
                throw std::runtime_error("failed to create render-component OBJ fixture");
            }
        }
        const easy3d::EntityHandle model_entity = scene.create_entity("model");
        scene.add_model_renderer(model_entity, model_path, {0.5F, 0.75F, 1.0F, 1.0F});
        std::filesystem::remove(model_path);
        const easy3d::RenderComponent& model = scene.render_component(model_entity);
        if (model.kind != easy3d::RenderKind::Model || !model.model || model.mesh ||
            model.model->triangle_count() != 1) {
            std::cerr << "model render component did not retain its shared model asset\n";
            return 7;
        }

        std::cout << "easy3d_render_component_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "easy3d_render_component_tests: FAIL: " << error.what() << '\n';
        return 10;
    }
}
