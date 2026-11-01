#pragma once

#include <cmath>

namespace easy3d {

struct Vec2 final {
    float x{0.0F};
    float y{0.0F};

    [[nodiscard]] float length_squared() const noexcept;
    [[nodiscard]] float length() const noexcept;
    [[nodiscard]] Vec2 normalized() const;
    [[nodiscard]] float dot(Vec2 other) const noexcept;

    friend bool operator==(const Vec2&, const Vec2&) = default;
    friend Vec2 operator+(Vec2 left, Vec2 right) noexcept;
    friend Vec2 operator-(Vec2 left, Vec2 right) noexcept;
    friend Vec2 operator*(Vec2 value, float scalar) noexcept;
    friend Vec2 operator*(float scalar, Vec2 value) noexcept;
    friend Vec2 operator/(Vec2 value, float scalar);
};

struct Vec3 final {
    float x{0.0F};
    float y{0.0F};
    float z{0.0F};

    [[nodiscard]] float length_squared() const noexcept;
    [[nodiscard]] float length() const noexcept;
    [[nodiscard]] Vec3 normalized() const;
    [[nodiscard]] float dot(Vec3 other) const noexcept;
    [[nodiscard]] Vec3 cross(Vec3 other) const noexcept;

    friend bool operator==(const Vec3&, const Vec3&) = default;
    friend Vec3 operator+(Vec3 left, Vec3 right) noexcept;
    friend Vec3 operator-(Vec3 left, Vec3 right) noexcept;
    friend Vec3 operator-(Vec3 value) noexcept;
    friend Vec3 operator*(Vec3 value, float scalar) noexcept;
    friend Vec3 operator*(float scalar, Vec3 value) noexcept;
    friend Vec3 operator/(Vec3 value, float scalar);
};

struct Quat final {
    float w{1.0F};
    float x{0.0F};
    float y{0.0F};
    float z{0.0F};

    [[nodiscard]] float length_squared() const noexcept;
    [[nodiscard]] float length() const noexcept;
    [[nodiscard]] Quat normalized() const;
    [[nodiscard]] Quat conjugate() const noexcept;
    [[nodiscard]] Vec3 rotate(Vec3 vector) const;
    [[nodiscard]] Vec3 to_euler_degrees() const;
    [[nodiscard]] static Quat from_euler_degrees(Vec3 euler_degrees);

    friend bool operator==(const Quat&, const Quat&) = default;
    friend Quat operator*(Quat left, Quat right) noexcept;
};

struct Transform final {
    Vec3 position{};
    Quat rotation{};
    Vec3 scale{1.0F, 1.0F, 1.0F};

    friend bool operator==(const Transform&, const Transform&) = default;
};

[[nodiscard]] bool almost_equal(float left,
                                float right,
                                float absolute_tolerance = 1.0e-5F,
                                float relative_tolerance = 1.0e-5F) noexcept;
[[nodiscard]] bool almost_equal(Vec2 left,
                                Vec2 right,
                                float tolerance = 1.0e-5F) noexcept;
[[nodiscard]] bool almost_equal(Vec3 left,
                                Vec3 right,
                                float tolerance = 1.0e-5F) noexcept;
[[nodiscard]] bool almost_equal(Quat left,
                                Quat right,
                                float tolerance = 1.0e-5F) noexcept;

} // namespace easy3d
