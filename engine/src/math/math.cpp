#include "easy3d/math.hpp"

#include <glm/geometric.hpp>
#include <glm/gtc/quaternion.hpp>

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace easy3d {
namespace {

constexpr float minimum_norm = 1.0e-12F;

[[nodiscard]] glm::quat to_glm(const Quat value) noexcept {
    return {value.w, value.x, value.y, value.z};
}

[[nodiscard]] Quat from_glm(const glm::quat value) noexcept {
    return {value.w, value.x, value.y, value.z};
}

[[nodiscard]] glm::vec3 to_glm(const Vec3 value) noexcept {
    return {value.x, value.y, value.z};
}

[[nodiscard]] Vec3 from_glm(const glm::vec3 value) noexcept {
    return {value.x, value.y, value.z};
}

void require_nonzero(const float value, const char* operation) {
    if (!std::isfinite(value) || std::abs(value) <= minimum_norm) {
        throw std::domain_error(operation);
    }
}

} // namespace

float Vec2::length_squared() const noexcept {
    return x * x + y * y;
}

float Vec2::length() const noexcept {
    return std::sqrt(length_squared());
}

Vec2 Vec2::normalized() const {
    const float magnitude = length();
    require_nonzero(magnitude, "cannot normalize a zero-length Vec2");
    return *this / magnitude;
}

float Vec2::dot(const Vec2 other) const noexcept {
    return x * other.x + y * other.y;
}

Vec2 operator+(const Vec2 left, const Vec2 right) noexcept {
    return {left.x + right.x, left.y + right.y};
}

Vec2 operator-(const Vec2 left, const Vec2 right) noexcept {
    return {left.x - right.x, left.y - right.y};
}

Vec2 operator*(const Vec2 value, const float scalar) noexcept {
    return {value.x * scalar, value.y * scalar};
}

Vec2 operator*(const float scalar, const Vec2 value) noexcept {
    return value * scalar;
}

Vec2 operator/(const Vec2 value, const float scalar) {
    require_nonzero(scalar, "cannot divide Vec2 by zero");
    return {value.x / scalar, value.y / scalar};
}

float Vec3::length_squared() const noexcept {
    return x * x + y * y + z * z;
}

float Vec3::length() const noexcept {
    return std::sqrt(length_squared());
}

Vec3 Vec3::normalized() const {
    const float magnitude = length();
    require_nonzero(magnitude, "cannot normalize a zero-length Vec3");
    return *this / magnitude;
}

float Vec3::dot(const Vec3 other) const noexcept {
    return x * other.x + y * other.y + z * other.z;
}

Vec3 Vec3::cross(const Vec3 other) const noexcept {
    return {y * other.z - z * other.y,
            z * other.x - x * other.z,
            x * other.y - y * other.x};
}

Vec3 operator+(const Vec3 left, const Vec3 right) noexcept {
    return {left.x + right.x, left.y + right.y, left.z + right.z};
}

Vec3 operator-(const Vec3 left, const Vec3 right) noexcept {
    return {left.x - right.x, left.y - right.y, left.z - right.z};
}

Vec3 operator-(const Vec3 value) noexcept {
    return {-value.x, -value.y, -value.z};
}

Vec3 operator*(const Vec3 value, const float scalar) noexcept {
    return {value.x * scalar, value.y * scalar, value.z * scalar};
}

Vec3 operator*(const float scalar, const Vec3 value) noexcept {
    return value * scalar;
}

Vec3 operator/(const Vec3 value, const float scalar) {
    require_nonzero(scalar, "cannot divide Vec3 by zero");
    return {value.x / scalar, value.y / scalar, value.z / scalar};
}

float Quat::length_squared() const noexcept {
    return w * w + x * x + y * y + z * z;
}

float Quat::length() const noexcept {
    return std::sqrt(length_squared());
}

Quat Quat::normalized() const {
    const float magnitude = length();
    require_nonzero(magnitude, "cannot normalize a zero-length Quat");
    return {w / magnitude, x / magnitude, y / magnitude, z / magnitude};
}

Quat Quat::conjugate() const noexcept {
    return {w, -x, -y, -z};
}

Vec3 Quat::rotate(const Vec3 vector) const {
    return from_glm(to_glm(normalized()) * to_glm(vector));
}

Vec3 Quat::to_euler_degrees() const {
    return from_glm(glm::degrees(glm::eulerAngles(to_glm(normalized()))));
}

Quat Quat::from_euler_degrees(const Vec3 euler_degrees) {
    return from_glm(glm::quat(glm::radians(to_glm(euler_degrees)))).normalized();
}

Quat operator*(const Quat left, const Quat right) noexcept {
    return {left.w * right.w - left.x * right.x - left.y * right.y - left.z * right.z,
            left.w * right.x + left.x * right.w + left.y * right.z - left.z * right.y,
            left.w * right.y - left.x * right.z + left.y * right.w + left.z * right.x,
            left.w * right.z + left.x * right.y - left.y * right.x + left.z * right.w};
}

bool almost_equal(const float left,
                  const float right,
                  const float absolute_tolerance,
                  const float relative_tolerance) noexcept {
    const float difference = std::abs(left - right);
    return difference <= absolute_tolerance ||
           difference <= relative_tolerance * std::max(std::abs(left), std::abs(right));
}

bool almost_equal(const Vec2 left, const Vec2 right, const float tolerance) noexcept {
    return almost_equal(left.x, right.x, tolerance, tolerance) &&
           almost_equal(left.y, right.y, tolerance, tolerance);
}

bool almost_equal(const Vec3 left, const Vec3 right, const float tolerance) noexcept {
    return almost_equal(left.x, right.x, tolerance, tolerance) &&
           almost_equal(left.y, right.y, tolerance, tolerance) &&
           almost_equal(left.z, right.z, tolerance, tolerance);
}

bool almost_equal(const Quat left, const Quat right, const float tolerance) noexcept {
    const bool direct = almost_equal(left.w, right.w, tolerance, tolerance) &&
                        almost_equal(left.x, right.x, tolerance, tolerance) &&
                        almost_equal(left.y, right.y, tolerance, tolerance) &&
                        almost_equal(left.z, right.z, tolerance, tolerance);
    const bool negated = almost_equal(left.w, -right.w, tolerance, tolerance) &&
                         almost_equal(left.x, -right.x, tolerance, tolerance) &&
                         almost_equal(left.y, -right.y, tolerance, tolerance) &&
                         almost_equal(left.z, -right.z, tolerance, tolerance);
    return direct || negated;
}

} // namespace easy3d
