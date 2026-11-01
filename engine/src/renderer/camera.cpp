#include "easy3d/renderer.hpp"

#include <glm/ext/matrix_clip_space.hpp>
#include <glm/ext/matrix_transform.hpp>
#include <glm/gtc/quaternion.hpp>
#include <glm/gtc/type_ptr.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>

namespace easy3d {
namespace {

[[nodiscard]] glm::vec3 to_glm(const Vec3 value) noexcept {
    return {value.x, value.y, value.z};
}

[[nodiscard]] glm::quat to_glm(const Quat value) noexcept {
    return {value.w, value.x, value.y, value.z};
}

[[nodiscard]] Quat from_glm(const glm::quat value) noexcept {
    return {value.w, value.x, value.y, value.z};
}

[[nodiscard]] Matrix4 from_glm(const glm::mat4& value) noexcept {
    Matrix4 result;
    std::copy_n(glm::value_ptr(value), result.values.size(), result.values.begin());
    return result;
}

[[nodiscard]] bool finite(const Vec3 value) noexcept {
    return std::isfinite(value.x) && std::isfinite(value.y) && std::isfinite(value.z);
}

} // namespace

float Matrix4::at(const std::size_t row, const std::size_t column) const {
    if (row >= 4 || column >= 4) {
        throw std::out_of_range("matrix row and column must be from 0 to 3");
    }
    return values[column * 4 + row];
}

const float* Matrix4::data() const noexcept {
    return values.data();
}

Vec3 Matrix4::transform_point(const Vec3 point) const {
    if (!finite(point)) {
        throw std::invalid_argument("matrix point must be finite");
    }
    const float x = values[0] * point.x + values[4] * point.y +
                    values[8] * point.z + values[12];
    const float y = values[1] * point.x + values[5] * point.y +
                    values[9] * point.z + values[13];
    const float z = values[2] * point.x + values[6] * point.y +
                    values[10] * point.z + values[14];
    const float w = values[3] * point.x + values[7] * point.y +
                    values[11] * point.z + values[15];
    if (!std::isfinite(w) || std::abs(w) <= 1.0e-12F) {
        throw std::domain_error("matrix point has an invalid homogeneous coordinate");
    }
    return {x / w, y / w, z / w};
}

Matrix4 operator*(const Matrix4& left, const Matrix4& right) noexcept {
    Matrix4 result;
    for (std::size_t column = 0; column < 4; ++column) {
        for (std::size_t row = 0; row < 4; ++row) {
            float value = 0.0F;
            for (std::size_t inner = 0; inner < 4; ++inner) {
                value += left.values[inner * 4 + row] *
                         right.values[column * 4 + inner];
            }
            result.values[column * 4 + row] = value;
        }
    }
    return result;
}

void Camera::validate() const {
    if (!finite(position)) {
        throw std::invalid_argument("camera position must be finite");
    }
    (void)rotation.normalized();
    if (!std::isfinite(vertical_fov_degrees) || vertical_fov_degrees <= 0.0F ||
        vertical_fov_degrees >= 180.0F) {
        throw std::invalid_argument("camera vertical FOV must be between 0 and 180 degrees");
    }
    if (!std::isfinite(near_plane) || near_plane <= 0.0F) {
        throw std::invalid_argument("camera near plane must be finite and positive");
    }
    if (!std::isfinite(far_plane) || far_plane <= near_plane) {
        throw std::invalid_argument("camera far plane must be finite and greater than near plane");
    }
    if (!std::isfinite(orthographic_height) || orthographic_height <= 0.0F) {
        throw std::invalid_argument("camera orthographic height must be finite and positive");
    }
}

Vec3 Camera::forward() const {
    validate();
    return rotation.normalized().rotate({0.0F, 0.0F, -1.0F});
}

Vec3 Camera::right() const {
    validate();
    return rotation.normalized().rotate({1.0F, 0.0F, 0.0F});
}

Vec3 Camera::up() const {
    validate();
    return rotation.normalized().rotate({0.0F, 1.0F, 0.0F});
}

Matrix4 Camera::view_matrix() const {
    validate();
    return from_glm(glm::lookAtRH(to_glm(position),
                                  to_glm(position + forward()),
                                  to_glm(up())));
}

Matrix4 Camera::projection_matrix(const float aspect, const bool homogeneous_depth) const {
    validate();
    if (!std::isfinite(aspect) || aspect <= 0.0F) {
        throw std::invalid_argument("camera aspect ratio must be finite and positive");
    }
    if (projection == CameraProjection::Orthographic) {
        const float half_height = orthographic_height * 0.5F;
        const float half_width = half_height * aspect;
        return from_glm(homogeneous_depth
                            ? glm::orthoRH_NO(-half_width,
                                              half_width,
                                              -half_height,
                                              half_height,
                                              near_plane,
                                              far_plane)
                            : glm::orthoRH_ZO(-half_width,
                                              half_width,
                                              -half_height,
                                              half_height,
                                              near_plane,
                                              far_plane));
    }
    const float radians = glm::radians(vertical_fov_degrees);
    return from_glm(homogeneous_depth
                        ? glm::perspectiveRH_NO(radians, aspect, near_plane, far_plane)
                        : glm::perspectiveRH_ZO(radians, aspect, near_plane, far_plane));
}

float Camera::aspect_ratio(const std::uint32_t width, const std::uint32_t height) {
    if (width == 0 || height == 0) {
        throw std::invalid_argument("camera viewport width and height must be positive");
    }
    return static_cast<float>(width) / static_cast<float>(height);
}

Camera Camera::look_at(const Vec3 camera_position, const Vec3 target, const Vec3 world_up) {
    if (!finite(camera_position) || !finite(target) || !finite(world_up)) {
        throw std::invalid_argument("camera look-at vectors must be finite");
    }
    const Vec3 direction = target - camera_position;
    if (direction.length_squared() <= 1.0e-12F) {
        throw std::invalid_argument("camera look-at target must differ from its position");
    }
    if (world_up.length_squared() <= 1.0e-12F) {
        throw std::invalid_argument("camera look-at up vector must be nonzero");
    }
    const Vec3 normalized_direction = direction.normalized();
    const Vec3 normalized_up = world_up.normalized();
    if (std::abs(normalized_direction.dot(normalized_up)) >= 0.9999F) {
        throw std::invalid_argument("camera look-at direction and up vector must not be parallel");
    }

    Camera camera;
    camera.position = camera_position;
    camera.rotation = from_glm(glm::quatLookAtRH(to_glm(normalized_direction),
                                                  to_glm(normalized_up)))
                          .normalized();
    return camera;
}

Frustum Frustum::from_view_projection(const Matrix4& matrix,
                                      const bool homogeneous_depth) {
    const auto make_plane = [](const std::array<float, 4>& coefficients) {
        const Vec3 normal{coefficients[0], coefficients[1], coefficients[2]};
        const float length = normal.length();
        if (!std::isfinite(length) || length <= 1.0e-12F ||
            !std::isfinite(coefficients[3])) {
            throw std::invalid_argument("view-projection matrix produces an invalid frustum");
        }
        return FrustumPlane{normal / length, coefficients[3] / length};
    };
    const auto row = [&matrix](const std::size_t index) {
        return std::array<float, 4>{matrix.at(index, 0),
                                    matrix.at(index, 1),
                                    matrix.at(index, 2),
                                    matrix.at(index, 3)};
    };
    const auto add = [](const std::array<float, 4>& left,
                        const std::array<float, 4>& right) {
        return std::array<float, 4>{left[0] + right[0],
                                    left[1] + right[1],
                                    left[2] + right[2],
                                    left[3] + right[3]};
    };
    const auto subtract = [](const std::array<float, 4>& left,
                             const std::array<float, 4>& right) {
        return std::array<float, 4>{left[0] - right[0],
                                    left[1] - right[1],
                                    left[2] - right[2],
                                    left[3] - right[3]};
    };

    const auto first = row(0);
    const auto second = row(1);
    const auto third = row(2);
    const auto fourth = row(3);
    Frustum result;
    result.planes = {
        make_plane(add(fourth, first)),
        make_plane(subtract(fourth, first)),
        make_plane(add(fourth, second)),
        make_plane(subtract(fourth, second)),
        make_plane(homogeneous_depth ? add(fourth, third) : third),
        make_plane(subtract(fourth, third)),
    };
    return result;
}

Frustum Frustum::from_camera(const Camera& camera,
                             const float aspect,
                             const bool homogeneous_depth) {
    return from_view_projection(camera.projection_matrix(aspect, homogeneous_depth) *
                                    camera.view_matrix(),
                                homogeneous_depth);
}

bool Frustum::intersects(const Bounds local_bounds,
                         const Transform& transform) const {
    const Vec3 center = (local_bounds.minimum + local_bounds.maximum) * 0.5F;
    const Vec3 extent = (local_bounds.maximum - local_bounds.minimum) * 0.5F;
    const Vec3 scaled_center{center.x * transform.scale.x,
                             center.y * transform.scale.y,
                             center.z * transform.scale.z};
    const Vec3 scaled_extent{std::abs(extent.x * transform.scale.x),
                             std::abs(extent.y * transform.scale.y),
                             std::abs(extent.z * transform.scale.z)};
    const Vec3 world_center = transform.position + transform.rotation.rotate(scaled_center);
    const float radius = scaled_extent.length();
    for (const FrustumPlane& plane : planes) {
        if (plane.normal.dot(world_center) + plane.distance < -radius) {
            return false;
        }
    }
    return true;
}

} // namespace easy3d
