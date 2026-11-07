#include "easy3d/renderer.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {

int fail(const int code, const char* message) {
    std::cerr << message << '\n';
    return code;
}

bool winding_matches_normals(const easy3d::MeshData& mesh) {
    for (std::size_t offset = 0; offset < mesh.indices.size(); offset += 3) {
        const easy3d::Vertex& first = mesh.vertices[mesh.indices[offset]];
        const easy3d::Vertex& second = mesh.vertices[mesh.indices[offset + 1]];
        const easy3d::Vertex& third = mesh.vertices[mesh.indices[offset + 2]];
        const easy3d::Vec3 geometric =
            (second.position - first.position).cross(third.position - first.position);
        if (geometric.length_squared() > 1.0e-10F && geometric.dot(first.normal) <= 0.0F) {
            return false;
        }
    }
    return true;
}

bool tangents_are_orthonormal(const easy3d::MeshData& mesh) {
    for (const easy3d::Vertex& vertex : mesh.vertices) {
        const easy3d::Vec3 tangent{
            vertex.tangent[0], vertex.tangent[1], vertex.tangent[2]};
        if (!easy3d::almost_equal(tangent.length(), 1.0F, 1.0e-4F, 1.0e-4F) ||
            std::abs(tangent.dot(vertex.normal)) > 1.0e-4F ||
            std::abs(std::abs(vertex.tangent[3]) - 1.0F) > 1.0e-4F) {
            return false;
        }
    }
    return true;
}

bool atlas_rect_matches(const std::array<float, 4>& actual,
                        const std::array<float, 4>& expected) {
    for (std::size_t index = 0; index < actual.size(); ++index) {
        if (!easy3d::almost_equal(actual[index], expected[index])) return false;
    }
    return true;
}

} // namespace

int main() {
    const easy3d::MeshData triangle = easy3d::make_triangle_mesh();
    if (triangle.vertices.size() != 3 || triangle.triangle_count() != 1 ||
        !winding_matches_normals(triangle) || !tangents_are_orthonormal(triangle)) {
        return fail(1, "triangle primitive is invalid");
    }

    const easy3d::MeshData cube = easy3d::make_cube_mesh(2.0F);
    const easy3d::Bounds cube_bounds = cube.bounds();
    if (cube.vertices.size() != 24 || cube.triangle_count() != 12 ||
        !easy3d::almost_equal(cube_bounds.minimum, {-1.0F, -1.0F, -1.0F}) ||
        !easy3d::almost_equal(cube_bounds.maximum, {1.0F, 1.0F, 1.0F}) ||
        !winding_matches_normals(cube) || !tangents_are_orthonormal(cube)) {
        return fail(2, "cube primitive is invalid");
    }

    const easy3d::MeshData plane = easy3d::make_plane_mesh(4.0F, 6.0F);
    const easy3d::Bounds plane_bounds = plane.bounds();
    if (plane.vertices.size() != 4 || plane.triangle_count() != 2 ||
        !easy3d::almost_equal(plane_bounds.minimum, {-2.0F, 0.0F, -3.0F}) ||
        !easy3d::almost_equal(plane_bounds.maximum, {2.0F, 0.0F, 3.0F}) ||
        plane.vertices[0].uv != easy3d::Vec2{0.0F, 0.0F} ||
        plane.vertices[1].uv != easy3d::Vec2{1.0F, 0.0F} ||
        plane.vertices[2].uv != easy3d::Vec2{1.0F, 1.0F} ||
        plane.vertices[3].uv != easy3d::Vec2{0.0F, 1.0F} ||
        !winding_matches_normals(plane) || !tangents_are_orthonormal(plane)) {
        return fail(3, "plane primitive is invalid");
    }

    const easy3d::MeshData sphere = easy3d::make_uv_sphere_mesh(2.0F, 8, 4);
    if (sphere.vertices.size() != 45 || sphere.triangle_count() != 64 ||
        !winding_matches_normals(sphere) || !tangents_are_orthonormal(sphere)) {
        return fail(4, "sphere primitive is invalid");
    }
    for (const easy3d::Vertex& vertex : sphere.vertices) {
        if (!easy3d::almost_equal(vertex.position.length(), 2.0F, 1.0e-4F, 1.0e-4F) ||
            !easy3d::almost_equal(vertex.normal.length(), 1.0F, 1.0e-4F, 1.0e-4F) ||
            vertex.uv.x < 0.0F || vertex.uv.x > 1.0F || vertex.uv.y < 0.0F ||
            vertex.uv.y > 1.0F) {
            return fail(5, "sphere radius, normals, or UV range are invalid");
        }
    }
    constexpr std::uint32_t sphere_segments = 8;
    constexpr std::uint32_t sphere_rings = 4;
    constexpr std::uint32_t sphere_stride = sphere_segments + 1;
    for (std::uint32_t ring = 0; ring <= sphere_rings; ++ring) {
        const easy3d::Vertex& first = sphere.vertices[ring * sphere_stride];
        const easy3d::Vertex& seam = sphere.vertices[ring * sphere_stride + sphere_segments];
        if (!easy3d::almost_equal(first.position, seam.position, 1.0e-4F) ||
            !easy3d::almost_equal(first.normal, seam.normal, 1.0e-4F) ||
            first.uv != easy3d::Vec2{0.0F,
                                     static_cast<float>(ring) /
                                         static_cast<float>(sphere_rings)} ||
            seam.uv != easy3d::Vec2{1.0F, first.uv.y}) {
            return fail(13, "sphere UV seam or top-left V orientation is incorrect");
        }
    }

    easy3d::MeshData invalid = triangle;
    invalid.indices[2] = 999;
    try {
        invalid.validate();
        return fail(6, "out-of-range mesh index was accepted");
    } catch (const std::out_of_range&) {
        // Expected.
    }


    easy3d::MeshData mirrored = easy3d::make_plane_mesh();
    const float original_handedness = mirrored.vertices.front().tangent[3];
    for (easy3d::Vertex& vertex : mirrored.vertices) {
        vertex.uv.x = 1.0F - vertex.uv.x;
    }
    easy3d::generate_tangents(mirrored);
    if (!tangents_are_orthonormal(mirrored) ||
        mirrored.vertices.front().tangent[3] == original_handedness) {
        return fail(9, "mirrored UV tangent handedness was not preserved");
    }

    const easy3d::TextureMappingData tiled = easy3d::calculate_texture_mapping(
        easy3d::TextureMode::Tile, {2.0F, 3.0F, 1.0F}, 16, 16, 16.0F);
    if (tiled.repeat[0] != easy3d::Vec2{1.0F, 3.0F} ||
        tiled.repeat[1] != easy3d::Vec2{2.0F, 1.0F} ||
        tiled.repeat[2] != easy3d::Vec2{2.0F, 3.0F}) {
        return fail(10, "nonuniform cuboid texel density is incorrect");
    }

    const easy3d::TextureMappingData parent_scaled =
        easy3d::calculate_texture_mapping(
            easy3d::TextureMode::Tile, {-4.0F, 6.0F, 2.0F}, 16, 16, 16.0F);
    if (parent_scaled.repeat[0] != easy3d::Vec2{2.0F, 6.0F} ||
        parent_scaled.repeat[2] != easy3d::Vec2{4.0F, 6.0F}) {
        return fail(11, "world/parent/mirrored scale texel density is incorrect");
    }

    const easy3d::TextureMappingData atlas = easy3d::calculate_texture_mapping(
        easy3d::TextureMode::Atlas, {2.0F, 3.0F, 1.0F}, 96, 80, 16.0F);
    if (!atlas_rect_matches(atlas.atlas[0], {1.0F / 6.0F, 1.0F / 5.0F,
                                              2.0F / 6.0F, 3.0F / 5.0F}) ||
        !atlas_rect_matches(atlas.atlas[1], {4.0F / 6.0F, 1.0F / 5.0F,
                                              2.0F / 6.0F, 3.0F / 5.0F}) ||
        !atlas_rect_matches(atlas.atlas[2], {3.0F / 6.0F, 1.0F / 5.0F,
                                              1.0F / 6.0F, 3.0F / 5.0F}) ||
        !atlas_rect_matches(atlas.atlas[3], {0.0F, 1.0F / 5.0F,
                                              1.0F / 6.0F, 3.0F / 5.0F}) ||
        !atlas_rect_matches(atlas.atlas[4], {1.0F / 6.0F, 0.0F,
                                              2.0F / 6.0F, 1.0F / 5.0F}) ||
        !atlas_rect_matches(atlas.atlas[5], {1.0F / 6.0F, 4.0F / 5.0F,
                                              2.0F / 6.0F, 1.0F / 5.0F})) {
        return fail(12, "rectangular cube atlas layout is incorrect");
    }

    if (easy3d::Color{1.0F, 0.0F, 0.5F, 1.0F}.rgba8() != 0xFF8000FFU) {
        return fail(7, "RGBA8 color packing failed");
    }

    try {
        (void)easy3d::make_cube_mesh(0.0F);
        return fail(8, "zero cube size was accepted");
    } catch (const std::invalid_argument&) {
        // Expected.
    }

    std::cout << "rix_mesh_tests: PASS\n";
    return 0;
}
