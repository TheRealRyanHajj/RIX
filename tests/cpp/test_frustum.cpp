#include "easy3d/renderer.hpp"

#include <iostream>

namespace {

int check_depth_convention(const bool homogeneous_depth) {
    easy3d::Camera camera = easy3d::Camera::look_at(
        {0.0F, 0.0F, 5.0F}, {0.0F, 0.0F, 0.0F});
    camera.vertical_fov_degrees = 60.0F;
    camera.near_plane = 0.1F;
    camera.far_plane = 100.0F;
    const easy3d::Frustum frustum =
        easy3d::Frustum::from_camera(camera, 1.0F, homogeneous_depth);
    const easy3d::Bounds cube{{-0.5F, -0.5F, -0.5F},
                              {0.5F, 0.5F, 0.5F}};

    if (!frustum.intersects(cube, {})) {
        std::cerr << "origin cube was culled\n";
        return 1;
    }
    if (frustum.intersects(cube, {{100.0F, 0.0F, 0.0F}})) {
        std::cerr << "far-right cube was visible\n";
        return 2;
    }
    if (frustum.intersects(cube, {{0.0F, 0.0F, 10.0F}})) {
        std::cerr << "behind-camera cube was visible\n";
        return 3;
    }
    if (frustum.intersects(cube, {{0.0F, 0.0F, -150.0F}})) {
        std::cerr << "past-far-plane cube was visible\n";
        return 4;
    }
    easy3d::Transform large_edge;
    large_edge.position = {4.0F, 0.0F, 0.0F};
    large_edge.scale = {5.0F, 1.0F, 1.0F};
    if (!frustum.intersects(cube, large_edge)) {
        std::cerr << "conservative scaled edge cube was culled\n";
        return 5;
    }
    return 0;
}

} // namespace

int main() {
    try {
        const int d3d_result = check_depth_convention(false);
        if (d3d_result != 0) {
            return d3d_result;
        }
        const int homogeneous_result = check_depth_convention(true);
        if (homogeneous_result != 0) {
            return homogeneous_result + 10;
        }

        easy3d::Matrix4 translation;
        translation.values[12] = 2.0F;
        easy3d::Matrix4 scale;
        scale.values[0] = 2.0F;
        const easy3d::Vec3 transformed =
            (translation * scale).transform_point({1.0F, 0.0F, 0.0F});
        if (!easy3d::almost_equal(transformed, {4.0F, 0.0F, 0.0F})) {
            std::cerr << "matrix multiplication order is incorrect\n";
            return 21;
        }

        std::cout << "easy3d_frustum_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "easy3d_frustum_tests: FAIL: " << error.what() << '\n';
        return 22;
    }
}
