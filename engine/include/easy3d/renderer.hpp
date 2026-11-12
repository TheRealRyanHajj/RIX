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
    // xyz is the tangent direction and w is the bitangent handedness.
    std::array<float, 4> tangent{1.0F, 0.0F, 0.0F, 1.0F};
    // Up to four linear-blend skin influences. A zero weight sum marks an
    // ordinary static vertex and leaves the joint indices unused.
    std::array<std::uint8_t, 4> joints{};
    std::array<float, 4> weights{};
};

struct Bounds final {
    Vec3 minimum{};
    Vec3 maximum{};
};

enum class TextureMode {
    Auto,
    Tile,
    Atlas,
    Sphere,
    Preserve,
};

enum class CullMode {
    Back,
    Front,
    None,
};

struct TextureMappingData final {
    // X-facing, Y-facing, and Z-facing UV repeat factors.
    std::array<Vec2, 3> repeat{{{1.0F, 1.0F}, {1.0F, 1.0F}, {1.0F, 1.0F}}};
    // Front, back, right, left, top, and bottom normalized atlas rectangles.
    std::array<std::array<float, 4>, 6> atlas{};
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
    CullMode cull_mode{CullMode::Back};
    float metallic{0.0F};
    float roughness{0.5F};
    float emission{0.0F};
    float normal_strength{1.0F};
    bool packed_metallic_roughness{false};
    bool casts_shadows{true};
    bool receives_shadows{true};

    void validate() const;
    friend bool operator==(const Material&, const Material&) = default;
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
    friend Matrix4 operator*(const Matrix4& left, const Matrix4& right) noexcept;
};

enum class CameraProjection {
    Perspective,
    Orthographic,
};

struct Camera final {
    Vec3 position{};
    Quat rotation{};
    float vertical_fov_degrees{60.0F};
    float near_plane{0.1F};
    float far_plane{1000.0F};
    CameraProjection projection{CameraProjection::Perspective};
    float orthographic_height{10.0F};

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

struct FrustumPlane final {
    Vec3 normal{};
    float distance{0.0F};
};

struct Frustum final {
    std::array<FrustumPlane, 6> planes{};

    [[nodiscard]] bool intersects(Bounds local_bounds,
                                  const Transform& world_transform) const;
    [[nodiscard]] static Frustum from_view_projection(const Matrix4& view_projection,
                                                      bool homogeneous_depth);
    [[nodiscard]] static Frustum from_camera(const Camera& camera,
                                             float aspect_ratio,
                                             bool homogeneous_depth);
};

[[nodiscard]] MeshData make_triangle_mesh();
[[nodiscard]] MeshData make_cube_mesh(float size = 1.0F);
[[nodiscard]] MeshData make_plane_mesh(float width = 1.0F, float depth = 1.0F);
[[nodiscard]] MeshData make_uv_sphere_mesh(float radius = 0.5F,
                                           std::uint32_t segments = 24,
                                           std::uint32_t rings = 16);
void generate_tangents(MeshData& mesh);
[[nodiscard]] TextureMappingData calculate_texture_mapping(
    TextureMode mode,
    Vec3 world_dimensions,
    std::uint32_t image_width,
    std::uint32_t image_height,
    float pixels_per_unit = 16.0F);

} // namespace easy3d
