#include "easy3d/renderer.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace easy3d {
namespace {

constexpr float pi = 3.14159265358979323846F;

[[nodiscard]] bool finite(const float value) noexcept {
    return std::isfinite(value);
}

[[nodiscard]] bool finite(const Vec2 value) noexcept {
    return finite(value.x) && finite(value.y);
}

[[nodiscard]] bool finite(const Vec3 value) noexcept {
    return finite(value.x) && finite(value.y) && finite(value.z);
}

[[nodiscard]] bool finite(const Color value) noexcept {
    return finite(value.r) && finite(value.g) && finite(value.b) && finite(value.a);
}

void require_positive(const float value, const char* label) {
    if (!finite(value) || value <= 0.0F) {
        throw std::invalid_argument(label);
    }
}

void append_face(MeshData& mesh,
                 const std::array<Vec3, 4>& positions,
                 const Vec3 normal) {
    const std::uint32_t base = static_cast<std::uint32_t>(mesh.vertices.size());
    constexpr std::array<Vec2, 4> uvs{{{0.0F, 0.0F},
                                       {1.0F, 0.0F},
                                       {1.0F, 1.0F},
                                       {0.0F, 1.0F}}};
    for (std::size_t index = 0; index < positions.size(); ++index) {
        mesh.vertices.push_back(Vertex{positions[index], normal, uvs[index], {}});
    }
    mesh.indices.insert(mesh.indices.end(), {base, base + 1, base + 2, base, base + 2, base + 3});
}

[[nodiscard]] std::uint8_t color_channel(const float value) {
    if (!finite(value) || value < 0.0F || value > 1.0F) {
        throw std::invalid_argument("color channels must be finite values from 0 to 1");
    }
    return static_cast<std::uint8_t>(std::lround(value * 255.0F));
}

} // namespace

std::uint32_t Color::rgba8() const {
    const std::uint32_t red = color_channel(r);
    const std::uint32_t green = color_channel(g);
    const std::uint32_t blue = color_channel(b);
    const std::uint32_t alpha = color_channel(a);
    return red | (green << 8U) | (blue << 16U) | (alpha << 24U);
}

void MeshData::validate() const {
    if (vertices.empty()) {
        throw std::invalid_argument("mesh must contain at least one vertex");
    }
    if (indices.empty() || indices.size() % 3 != 0) {
        throw std::invalid_argument("mesh indices must contain complete triangles");
    }
    for (const Vertex& vertex : vertices) {
        if (!finite(vertex.position) || !finite(vertex.normal) || !finite(vertex.uv) ||
            !finite(vertex.color)) {
            throw std::invalid_argument("mesh vertex attributes must be finite");
        }
        if (vertex.normal.length_squared() <= 1.0e-12F) {
            throw std::invalid_argument("mesh vertex normals must be nonzero");
        }
        (void)vertex.color.rgba8();
    }
    for (const std::uint32_t index : indices) {
        if (index >= vertices.size()) {
            throw std::out_of_range("mesh index references a missing vertex");
        }
    }
}

Bounds MeshData::bounds() const {
    if (vertices.empty()) {
        throw std::invalid_argument("cannot calculate bounds for an empty mesh");
    }
    Bounds result{vertices.front().position, vertices.front().position};
    for (const Vertex& vertex : vertices) {
        result.minimum.x = std::min(result.minimum.x, vertex.position.x);
        result.minimum.y = std::min(result.minimum.y, vertex.position.y);
        result.minimum.z = std::min(result.minimum.z, vertex.position.z);
        result.maximum.x = std::max(result.maximum.x, vertex.position.x);
        result.maximum.y = std::max(result.maximum.y, vertex.position.y);
        result.maximum.z = std::max(result.maximum.z, vertex.position.z);
    }
    return result;
}

std::size_t MeshData::triangle_count() const noexcept {
    return indices.size() / 3;
}

void Material::validate() const {
    (void)color.rgba8();
    if (!std::isfinite(metallic) || metallic < 0.0F || metallic > 1.0F) {
        throw std::invalid_argument("material metallic must be in [0, 1]");
    }
    if (!std::isfinite(roughness) || roughness < 0.04F || roughness > 1.0F) {
        throw std::invalid_argument("material roughness must be in [0.04, 1]");
    }
    if (!std::isfinite(emission) || emission < 0.0F || emission > 100.0F) {
        throw std::invalid_argument("material emission must be in [0, 100]");
    }
}

void DebugLine::validate() const {
    if (!finite(start) || !finite(end)) {
        throw std::invalid_argument("debug line endpoints must be finite");
    }
    if ((end - start).length_squared() <= 1.0e-12F) {
        throw std::invalid_argument("debug line endpoints must be distinct");
    }
    (void)color.rgba8();
}

MeshData make_triangle_mesh() {
    MeshData mesh{
        {
            {{-0.5F, -0.5F, 0.0F}, {0.0F, 0.0F, 1.0F}, {0.0F, 0.0F}, {1.0F, 0.2F, 0.2F, 1.0F}},
            {{0.5F, -0.5F, 0.0F}, {0.0F, 0.0F, 1.0F}, {1.0F, 0.0F}, {0.2F, 1.0F, 0.2F, 1.0F}},
            {{0.0F, 0.5F, 0.0F}, {0.0F, 0.0F, 1.0F}, {0.5F, 1.0F}, {0.2F, 0.4F, 1.0F, 1.0F}},
        },
        {0, 1, 2},
    };
    mesh.validate();
    return mesh;
}

MeshData make_cube_mesh(const float size) {
    require_positive(size, "cube size must be finite and positive");
    const float h = size * 0.5F;
    MeshData mesh;
    mesh.vertices.reserve(24);
    mesh.indices.reserve(36);

    append_face(mesh, {{{-h, -h, h}, {h, -h, h}, {h, h, h}, {-h, h, h}}}, {0.0F, 0.0F, 1.0F});
    append_face(mesh, {{{h, -h, -h}, {-h, -h, -h}, {-h, h, -h}, {h, h, -h}}}, {0.0F, 0.0F, -1.0F});
    append_face(mesh, {{{h, -h, h}, {h, -h, -h}, {h, h, -h}, {h, h, h}}}, {1.0F, 0.0F, 0.0F});
    append_face(mesh, {{{-h, -h, -h}, {-h, -h, h}, {-h, h, h}, {-h, h, -h}}}, {-1.0F, 0.0F, 0.0F});
    append_face(mesh, {{{-h, h, h}, {h, h, h}, {h, h, -h}, {-h, h, -h}}}, {0.0F, 1.0F, 0.0F});
    append_face(mesh, {{{-h, -h, -h}, {h, -h, -h}, {h, -h, h}, {-h, -h, h}}}, {0.0F, -1.0F, 0.0F});
    mesh.validate();
    return mesh;
}

MeshData make_plane_mesh(const float width, const float depth) {
    require_positive(width, "plane width must be finite and positive");
    require_positive(depth, "plane depth must be finite and positive");
    const float x = width * 0.5F;
    const float z = depth * 0.5F;
    MeshData mesh{
        {
            {{-x, 0.0F, -z}, {0.0F, 1.0F, 0.0F}, {0.0F, 0.0F}, {}},
            {{x, 0.0F, -z}, {0.0F, 1.0F, 0.0F}, {1.0F, 0.0F}, {}},
            {{x, 0.0F, z}, {0.0F, 1.0F, 0.0F}, {1.0F, 1.0F}, {}},
            {{-x, 0.0F, z}, {0.0F, 1.0F, 0.0F}, {0.0F, 1.0F}, {}},
        },
        {0, 2, 1, 0, 3, 2},
    };
    mesh.validate();
    return mesh;
}

MeshData make_uv_sphere_mesh(const float radius,
                             const std::uint32_t segments,
                             const std::uint32_t rings) {
    require_positive(radius, "sphere radius must be finite and positive");
    if (segments < 3 || rings < 2) {
        throw std::invalid_argument("sphere requires at least 3 segments and 2 rings");
    }
    const std::uint64_t vertex_count = static_cast<std::uint64_t>(segments + 1) * (rings + 1);
    if (vertex_count > std::numeric_limits<std::uint32_t>::max()) {
        throw std::invalid_argument("sphere tessellation exceeds 32-bit mesh limits");
    }

    MeshData mesh;
    mesh.vertices.reserve(static_cast<std::size_t>(vertex_count));
    mesh.indices.reserve(static_cast<std::size_t>(segments) * rings * 6U);

    for (std::uint32_t ring = 0; ring <= rings; ++ring) {
        const float v = static_cast<float>(ring) / static_cast<float>(rings);
        const float phi = v * pi;
        const float sin_phi = std::sin(phi);
        const float cos_phi = std::cos(phi);
        for (std::uint32_t segment = 0; segment <= segments; ++segment) {
            const float u = static_cast<float>(segment) / static_cast<float>(segments);
            const float theta = u * 2.0F * pi;
            const Vec3 normal{sin_phi * std::cos(theta), cos_phi, sin_phi * std::sin(theta)};
            mesh.vertices.push_back(Vertex{normal * radius, normal, {u, v}, {}});
        }
    }

    const std::uint32_t stride = segments + 1;
    for (std::uint32_t ring = 0; ring < rings; ++ring) {
        for (std::uint32_t segment = 0; segment < segments; ++segment) {
            const std::uint32_t a = ring * stride + segment;
            const std::uint32_t b = a + 1;
            const std::uint32_t c = a + stride;
            const std::uint32_t d = c + 1;
            mesh.indices.insert(mesh.indices.end(), {a, b, c, b, d, c});
        }
    }
    mesh.validate();
    return mesh;
}

} // namespace easy3d
