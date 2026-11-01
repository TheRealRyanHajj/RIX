#include "easy3d/assets.hpp"

#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

namespace {

class TemporaryDirectory final {
public:
    TemporaryDirectory()
        : path_(std::filesystem::temp_directory_path() /
                ("easy3d_model_test_" + std::to_string(++sequence_))) {
        std::filesystem::create_directories(path_);
    }
    ~TemporaryDirectory() { std::filesystem::remove_all(path_); }
    [[nodiscard]] const std::filesystem::path& path() const noexcept { return path_; }

private:
    static inline std::uint64_t sequence_{0};
    std::filesystem::path path_;
};

void write_text(const std::filesystem::path& path, const std::string& text) {
    std::ofstream stream(path, std::ios::binary);
    stream << text;
    if (!stream) {
        throw std::runtime_error("failed to create model test fixture");
    }
}

[[nodiscard]] bool approximately(const float left, const float right) {
    return std::abs(left - right) <= 1.0e-5F;
}

} // namespace

int main() {
    try {
        TemporaryDirectory temporary;
        write_text(temporary.path() / "albedo.png", "fixture");
        write_text(temporary.path() / "quad.mtl",
                   "newmtl Surface\n"
                   "Kd 0.25 0.5 0.75\n"
                   "d 0.8\n"
                   "map_Kd albedo.png\n");
        const std::filesystem::path quad_path = temporary.path() / "quad.obj";
        write_text(quad_path,
                   "mtllib quad.mtl\n"
                   "o Quad\n"
                   "v -1 0 0\n"
                   "v 1 0 0\n"
                   "v 1 2 0\n"
                   "v -1 2 0\n"
                   "vt 0 0\n"
                   "vt 1 0\n"
                   "vt 1 1\n"
                   "vt 0 1\n"
                   "vn 0 0 2\n"
                   "usemtl Surface\n"
                   "f 1/1/1 2/2/1 3/3/1 4/4/1\n");

        const auto quad = easy3d::load_obj(quad_path);
        if (quad->parts.size() != 1 || quad->materials.size() != 2 ||
            quad->triangle_count() != 2 || quad->parts[0].mesh.vertices.size() != 4 ||
            quad->parts[0].material_index != 1) {
            std::cerr << "triangulated/material-split OBJ metadata is incorrect\n";
            return 1;
        }
        const easy3d::ModelMaterial& material = quad->materials[1];
        if (material.name != "Surface" || !approximately(material.diffuse_color.r, 0.25F) ||
            !approximately(material.diffuse_color.g, 0.5F) ||
            !approximately(material.diffuse_color.b, 0.75F) ||
            !approximately(material.diffuse_color.a, 0.8F) ||
            !material.diffuse_texture.has_value() ||
            material.diffuse_texture->filename() != "albedo.png") {
            std::cerr << "MTL diffuse material conversion is incorrect\n";
            return 2;
        }

        bool uv_origin_found = false;
        for (const easy3d::Vertex& vertex : quad->parts[0].mesh.vertices) {
            if (vertex.position == easy3d::Vec3{-1.0F, 0.0F, 0.0F}) {
                uv_origin_found = vertex.uv == easy3d::Vec2{0.0F, 1.0F};
            }
            if (!easy3d::almost_equal(vertex.normal, {0.0F, 0.0F, 1.0F})) {
                std::cerr << "provided OBJ normals were not normalized/preserved\n";
                return 3;
            }
        }
        if (!uv_origin_found) {
            std::cerr << "OBJ V coordinate was not converted to top-left texture space\n";
            return 4;
        }

        easy3d::ModelCache cache;
        const auto first = cache.load(quad_path);
        const auto second = cache.load(temporary.path() / "." / "quad.obj");
        if (first.get() != second.get() || cache.size() != 1) {
            std::cerr << "canonical OBJ cache did not share model data\n";
            return 5;
        }
        cache.clear();
        if (cache.size() != 0 || first->triangle_count() != 2) {
            std::cerr << "model cache clear invalidated an outstanding resource\n";
            return 6;
        }

        const std::filesystem::path flat_path = temporary.path() / "flat.obj";
        write_text(flat_path,
                   "v 0 0 0\n"
                   "v 1 0 0\n"
                   "v 0 1 0\n"
                   "f 1 2 3\n");
        const auto flat = easy3d::load_obj(flat_path);
        if (flat->parts.size() != 1 || flat->parts[0].mesh.vertices.size() != 3 ||
            !easy3d::almost_equal(flat->parts[0].mesh.vertices[0].normal,
                                  {0.0F, 0.0F, 1.0F})) {
            std::cerr << "missing OBJ normals were not generated per triangle\n";
            return 7;
        }

        write_text(temporary.path() / "missing_texture.mtl",
                   "newmtl Broken\nmap_Kd absent.png\n");
        const std::filesystem::path missing_texture = temporary.path() / "missing_texture.obj";
        write_text(missing_texture,
                   "mtllib missing_texture.mtl\n"
                   "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
                   "usemtl Broken\nf 1 2 3\n");
        bool missing_failed = false;
        try {
            (void)easy3d::load_obj(missing_texture);
        } catch (const easy3d::MissingAssetError& error) {
            missing_failed = std::string(error.what()).find("absent.png") != std::string::npos;
        }
        if (!missing_failed) {
            std::cerr << "missing MTL texture did not produce MissingAssetError\n";
            return 8;
        }

        const std::filesystem::path missing_mtl = temporary.path() / "missing_mtl.obj";
        write_text(missing_mtl,
                   "mtllib absent.mtl\n"
                   "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n");
        try {
            (void)easy3d::load_obj(missing_mtl);
            std::cerr << "missing MTL library was silently accepted\n";
            return 9;
        } catch (const easy3d::MissingAssetError&) {
            // Expected.
        }

        const std::filesystem::path malformed = temporary.path() / "malformed.obj";
        write_text(malformed, "v 0 0 0\nv 1 0 0\nf 1 2 99\n");
        try {
            (void)easy3d::load_obj(malformed);
            std::cerr << "malformed OBJ was accepted\n";
            return 10;
        } catch (const easy3d::AssetError&) {
            // Expected.
        }

        try {
            (void)easy3d::load_obj(temporary.path() / "missing.obj");
            std::cerr << "missing OBJ was accepted\n";
            return 11;
        } catch (const easy3d::MissingAssetError&) {
            // Expected.
        }

        std::cout << "easy3d_model_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "easy3d_model_tests: FAIL: " << error.what() << '\n';
        return 20;
    }
}
