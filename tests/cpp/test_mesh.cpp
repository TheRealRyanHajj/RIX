#include "easy3d/renderer.hpp"

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

} // namespace

int main() {
    const easy3d::MeshData triangle = easy3d::make_triangle_mesh();
    if (triangle.vertices.size() != 3 || triangle.triangle_count() != 1 ||
        !winding_matches_normals(triangle)) {
        return fail(1, "triangle primitive is invalid");
    }

    const easy3d::MeshData cube = easy3d::make_cube_mesh(2.0F);
    const easy3d::Bounds cube_bounds = cube.bounds();
    if (cube.vertices.size() != 24 || cube.triangle_count() != 12 ||
        !easy3d::almost_equal(cube_bounds.minimum, {-1.0F, -1.0F, -1.0F}) ||
        !easy3d::almost_equal(cube_bounds.maximum, {1.0F, 1.0F, 1.0F}) ||
        !winding_matches_normals(cube)) {
        return fail(2, "cube primitive is invalid");
    }

    const easy3d::MeshData plane = easy3d::make_plane_mesh(4.0F, 6.0F);
    const easy3d::Bounds plane_bounds = plane.bounds();
    if (plane.vertices.size() != 4 || plane.triangle_count() != 2 ||
        !easy3d::almost_equal(plane_bounds.minimum, {-2.0F, 0.0F, -3.0F}) ||
        !easy3d::almost_equal(plane_bounds.maximum, {2.0F, 0.0F, 3.0F}) ||
        !winding_matches_normals(plane)) {
        return fail(3, "plane primitive is invalid");
    }

    const easy3d::MeshData sphere = easy3d::make_uv_sphere_mesh(2.0F, 8, 4);
    if (sphere.vertices.size() != 45 || sphere.triangle_count() != 64 ||
        !winding_matches_normals(sphere)) {
        return fail(4, "sphere primitive is invalid");
    }
    for (const easy3d::Vertex& vertex : sphere.vertices) {
        if (!easy3d::almost_equal(vertex.position.length(), 2.0F, 1.0e-4F, 1.0e-4F) ||
            !easy3d::almost_equal(vertex.normal.length(), 1.0F, 1.0e-4F, 1.0e-4F)) {
            return fail(5, "sphere radius or normals are invalid");
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

    if (easy3d::Color{1.0F, 0.0F, 0.5F, 1.0F}.rgba8() != 0xFF8000FFU) {
        return fail(7, "RGBA8 color packing failed");
    }

    try {
        (void)easy3d::make_cube_mesh(0.0F);
        return fail(8, "zero cube size was accepted");
    } catch (const std::invalid_argument&) {
        // Expected.
    }

    std::cout << "easy3d_mesh_tests: PASS\n";
    return 0;
}
