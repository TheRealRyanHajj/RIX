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

[[nodiscard]] bool finite(const std::array<float, 4>& value) noexcept {
    return std::all_of(value.begin(), value.end(), [](const float component) {
        return finite(component);
    });
}

[[nodiscard]] Vec3 tangent_xyz(const Vertex& vertex) noexcept {
    return {vertex.tangent[0], vertex.tangent[1], vertex.tangent[2]};
}

[[nodiscard]] Vec3 fallback_tangent(const Vec3 normal) {
    const Vec3 axis = std::abs(normal.y) < 0.999F ? Vec3{0.0F, 1.0F, 0.0F}
                                                  : Vec3{1.0F, 0.0F, 0.0F};
    return axis.cross(normal).normalized();
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
            !finite(vertex.color) || !finite(vertex.tangent)) {
            throw std::invalid_argument("mesh vertex attributes must be finite");
        }
        if (vertex.normal.length_squared() <= 1.0e-12F) {
            throw std::invalid_argument("mesh vertex normals must be nonzero");
        }
        (void)vertex.color.rgba8();
        if (tangent_xyz(vertex).length_squared() <= 1.0e-12F ||
            std::abs(std::abs(vertex.tangent[3]) - 1.0F) > 1.0e-4F) {
            throw std::invalid_argument(
                "mesh tangents must be nonzero with handedness -1 or 1");
        }
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
    if (!std::isfinite(normal_strength) || normal_strength < 0.0F ||
        normal_strength > 8.0F) {
        throw std::invalid_argument("material normal strength must be in [0, 8]");
    }
}

void generate_tangents(MeshData& mesh) {
    if (mesh.vertices.empty() || mesh.indices.empty() || mesh.indices.size() % 3 != 0) {
        throw std::invalid_argument("cannot generate tangents for an incomplete mesh");
    }
    std::vector<Vec3> tangents(mesh.vertices.size());
    std::vector<Vec3> bitangents(mesh.vertices.size());
    for (std::size_t triangle = 0; triangle < mesh.indices.size(); triangle += 3) {
        const std::uint32_t ia = mesh.indices[triangle];
        const std::uint32_t ib = mesh.indices[triangle + 1];
        const std::uint32_t ic = mesh.indices[triangle + 2];
        if (ia >= mesh.vertices.size() || ib >= mesh.vertices.size() ||
            ic >= mesh.vertices.size()) {
            throw std::out_of_range("mesh index references a missing vertex");
        }
        const Vertex& a = mesh.vertices[ia];
        const Vertex& b = mesh.vertices[ib];
        const Vertex& c = mesh.vertices[ic];
        const Vec3 edge1 = b.position - a.position;
        const Vec3 edge2 = c.position - a.position;
        const Vec2 delta1 = b.uv - a.uv;
        const Vec2 delta2 = c.uv - a.uv;
        const float determinant = delta1.x * delta2.y - delta1.y * delta2.x;
        if (std::abs(determinant) <= 1.0e-12F) {
            continue;
        }
        const float inverse = 1.0F / determinant;
        const Vec3 tangent = (edge1 * delta2.y - edge2 * delta1.y) * inverse;
        const Vec3 bitangent = (edge2 * delta1.x - edge1 * delta2.x) * inverse;
        for (const std::uint32_t index : {ia, ib, ic}) {
            tangents[index] = tangents[index] + tangent;
            bitangents[index] = bitangents[index] + bitangent;
        }
    }
    for (std::size_t index = 0; index < mesh.vertices.size(); ++index) {
        Vertex& vertex = mesh.vertices[index];
        const Vec3 normal = vertex.normal.normalized();
        Vec3 tangent = tangents[index] - normal * normal.dot(tangents[index]);
        if (tangent.length_squared() <= 1.0e-12F) {
            tangent = fallback_tangent(normal);
        } else {
            tangent = tangent.normalized();
        }
        const float handedness = normal.cross(tangent).dot(bitangents[index]) < 0.0F
                                     ? -1.0F
                                     : 1.0F;
        vertex.tangent = {tangent.x, tangent.y, tangent.z, handedness};
    }
}

TextureMappingData calculate_texture_mapping(const TextureMode mode,
                                             const Vec3 world_dimensions,
                                             const std::uint32_t image_width,
                                             const std::uint32_t image_height,
                                             const float pixels_per_unit) {
    if (!finite(world_dimensions) || image_width == 0 || image_height == 0 ||
        !finite(pixels_per_unit) || pixels_per_unit <= 0.0F) {
        throw std::invalid_argument("texture mapping inputs must be finite and positive");
    }
    const float width = std::max(std::abs(world_dimensions.x), 1.0e-6F);
    const float height = std::max(std::abs(world_dimensions.y), 1.0e-6F);
    const float depth = std::max(std::abs(world_dimensions.z), 1.0e-6F);
    const float texture_width = static_cast<float>(image_width);
    const float texture_height = static_cast<float>(image_height);
    TextureMappingData result;
    if (mode == TextureMode::Tile) {
        result.repeat = {{
            {depth * pixels_per_unit / texture_width,
             height * pixels_per_unit / texture_height},
            {width * pixels_per_unit / texture_width,
             depth * pixels_per_unit / texture_height},
            {width * pixels_per_unit / texture_width,
             height * pixels_per_unit / texture_height},
        }};
    } else if (mode == TextureMode::Sphere) {
        const float horizontal_diameter = (width + depth) * 0.5F;
        result.repeat[0] = {
            horizontal_diameter * pi * pixels_per_unit / texture_width,
            height * pi * 0.5F * pixels_per_unit / texture_height,
        };
    } else if (mode == TextureMode::Atlas) {
        const float atlas_width = width * 2.0F + depth * 2.0F;
        const float atlas_height = height + depth * 2.0F;
        const auto rect = [&](const std::size_t index,
                              const float x,
                              const float y,
                              const float w,
                              const float h) {
            result.atlas[index] = {
                x / atlas_width,
                y / atlas_height,
                w / atlas_width,
                h / atlas_height,
            };
        };
        rect(0, depth, depth, width, height);
        rect(1, depth + width + depth, depth, width, height);
        rect(2, depth + width, depth, depth, height);
        rect(3, 0.0F, depth, depth, height);
        rect(4, depth, 0.0F, width, depth);
        rect(5, depth, depth + height, width, depth);
    }
    return result;
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
    generate_tangents(mesh);
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
    generate_tangents(mesh);
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
    generate_tangents(mesh);
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
    generate_tangents(mesh);
    mesh.validate();
    return mesh;
}

} // namespace easy3d
