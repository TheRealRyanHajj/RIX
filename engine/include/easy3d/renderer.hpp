#pragma once

#include "easy3d/math.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace easy3d {

struct Color final {
    float r{1.0F};
    float g{1.0F};
    float b{1.0F};
    float a{1.0F};

    [[nodiscard]] std::uint32_t rgba8() const;
    friend bool operator==(const Color&, const Color&) = default;
};

struct Vertex final {
    Vec3 position{};
    Vec3 normal{0.0F, 1.0F, 0.0F};
    Vec2 uv{};
    Color color{};
};

struct Bounds final {
    Vec3 minimum{};
    Vec3 maximum{};
};

struct MeshData final {
    std::vector<Vertex> vertices;
    std::vector<std::uint32_t> indices;

    void validate() const;
    [[nodiscard]] Bounds bounds() const;
    [[nodiscard]] std::size_t triangle_count() const noexcept;
};

struct Material final {
    Color color{};
    bool lit{true};
    bool depth_test{true};
    bool depth_write{true};
    bool cull_back_faces{true};

    void validate() const;
};

struct DebugLine final {
    Vec3 start{};
    Vec3 end{};
    Color color{};
    bool depth_test{true};

    void validate() const;
};

struct Matrix4 final {
    // Column-major storage, matching bgfx and the renderer shader convention.
    std::array<float, 16> values{
        1.0F, 0.0F, 0.0F, 0.0F,
        0.0F, 1.0F, 0.0F, 0.0F,
        0.0F, 0.0F, 1.0F, 0.0F,
        0.0F, 0.0F, 0.0F, 1.0F,
    };

    [[nodiscard]] float at(std::size_t row, std::size_t column) const;
    [[nodiscard]] const float* data() const noexcept;
    [[nodiscard]] Vec3 transform_point(Vec3 point) const;

    friend bool operator==(const Matrix4&, const Matrix4&) = default;
};

struct Camera final {
    Vec3 position{};
    Quat rotation{};
    float vertical_fov_degrees{60.0F};
    float near_plane{0.1F};
    float far_plane{1000.0F};

    void validate() const;
    [[nodiscard]] Vec3 forward() const;
    [[nodiscard]] Vec3 right() const;
    [[nodiscard]] Vec3 up() const;
    [[nodiscard]] Matrix4 view_matrix() const;
    [[nodiscard]] Matrix4 projection_matrix(float aspect_ratio,
                                            bool homogeneous_depth) const;

    [[nodiscard]] static float aspect_ratio(std::uint32_t width,
                                            std::uint32_t height);
    [[nodiscard]] static Camera look_at(Vec3 position,
                                        Vec3 target,
                                        Vec3 up = {0.0F, 1.0F, 0.0F});
};

[[nodiscard]] MeshData make_triangle_mesh();
[[nodiscard]] MeshData make_cube_mesh(float size = 1.0F);
[[nodiscard]] MeshData make_plane_mesh(float width = 1.0F, float depth = 1.0F);
[[nodiscard]] MeshData make_uv_sphere_mesh(float radius = 0.5F,
                                           std::uint32_t segments = 24,
                                           std::uint32_t rings = 16);

} // namespace easy3d
