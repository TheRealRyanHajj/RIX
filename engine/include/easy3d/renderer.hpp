#pragma once

#include "easy3d/math.hpp"

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
    bool depth_test{true};
    bool depth_write{true};
    bool cull_back_faces{true};

    void validate() const;
};

[[nodiscard]] MeshData make_triangle_mesh();
[[nodiscard]] MeshData make_cube_mesh(float size = 1.0F);
[[nodiscard]] MeshData make_plane_mesh(float width = 1.0F, float depth = 1.0F);
[[nodiscard]] MeshData make_uv_sphere_mesh(float radius = 0.5F,
                                           std::uint32_t segments = 24,
                                           std::uint32_t rings = 16);

} // namespace easy3d
