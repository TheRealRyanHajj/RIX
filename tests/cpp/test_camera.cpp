#include "easy3d/renderer.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {

int fail(const int code, const char* message) {
    std::cerr << message << '\n';
    return code;
}

} // namespace

int main() {
    easy3d::Camera camera = easy3d::Camera::look_at({0.0F, 0.0F, 5.0F},
                                                     {0.0F, 0.0F, 0.0F});
    camera.vertical_fov_degrees = 60.0F;
    camera.near_plane = 0.25F;
    camera.far_plane = 250.0F;

    if (!easy3d::almost_equal(camera.forward(), {0.0F, 0.0F, -1.0F}) ||
        !easy3d::almost_equal(camera.right(), {1.0F, 0.0F, 0.0F}) ||
        !easy3d::almost_equal(camera.up(), {0.0F, 1.0F, 0.0F})) {
        return fail(1, "camera look-at basis is incorrect");
    }

    const easy3d::Matrix4 view = camera.view_matrix();
    if (!easy3d::almost_equal(view.transform_point(camera.position), {}) ||
        !easy3d::almost_equal(view.transform_point({0.0F, 0.0F, 0.0F}),
                              {0.0F, 0.0F, -5.0F})) {
        return fail(2, "camera view transform is incorrect");
    }

    const float aspect_4_3 = easy3d::Camera::aspect_ratio(800, 600);
    const float aspect_8_3 = easy3d::Camera::aspect_ratio(1600, 600);
    const easy3d::Matrix4 projection_4_3 = camera.projection_matrix(aspect_4_3, false);
    const easy3d::Matrix4 projection_8_3 = camera.projection_matrix(aspect_8_3, false);
    if (!easy3d::almost_equal(projection_4_3.at(0, 0) * 0.5F,
                              projection_8_3.at(0, 0)) ||
        !easy3d::almost_equal(projection_4_3.at(1, 1), projection_8_3.at(1, 1))) {
        return fail(3, "camera projection did not respond correctly to aspect resize");
    }

    const easy3d::Vec3 d3d_near =
        projection_4_3.transform_point({0.0F, 0.0F, -camera.near_plane});
    const easy3d::Vec3 d3d_far =
        projection_4_3.transform_point({0.0F, 0.0F, -camera.far_plane});
    if (!easy3d::almost_equal(d3d_near.z, 0.0F, 1.0e-5F, 1.0e-5F) ||
        !easy3d::almost_equal(d3d_far.z, 1.0F, 1.0e-5F, 1.0e-5F)) {
        return fail(4, "D3D projection depth range is incorrect");
    }

    const easy3d::Matrix4 homogeneous = camera.projection_matrix(aspect_4_3, true);
    const float gl_near = homogeneous.transform_point({0.0F, 0.0F, -camera.near_plane}).z;
    const float gl_far = homogeneous.transform_point({0.0F, 0.0F, -camera.far_plane}).z;
    if (!easy3d::almost_equal(gl_near, -1.0F, 1.0e-5F, 1.0e-5F) ||
        !easy3d::almost_equal(gl_far, 1.0F, 1.0e-5F, 1.0e-5F)) {
        return fail(5, "homogeneous projection depth range is incorrect");
    }

    try {
        camera.near_plane = 0.0F;
        camera.validate();
        return fail(6, "invalid camera clipping planes were accepted");
    } catch (const std::invalid_argument&) {
        // Expected.
    }

    try {
        (void)easy3d::Camera::aspect_ratio(1280, 0);
        return fail(7, "zero-height camera viewport was accepted");
    } catch (const std::invalid_argument&) {
        // Expected.
    }

    try {
        (void)easy3d::Camera::look_at({}, {}, {0.0F, 1.0F, 0.0F});
        return fail(8, "degenerate camera look-at was accepted");
    } catch (const std::invalid_argument&) {
        // Expected.
    }

    std::cout << "easy3d_camera_tests: PASS\n";
    return 0;
}
