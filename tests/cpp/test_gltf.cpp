#include "easy3d/assets.hpp"

#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <vector>

namespace {

class TemporaryDirectory final {
public:
    TemporaryDirectory() {
        const auto ticks = std::chrono::steady_clock::now().time_since_epoch().count();
        path_ = std::filesystem::temp_directory_path() /
                ("rix_gltf_test_" + std::to_string(ticks));
        std::filesystem::create_directories(path_);
    }
    ~TemporaryDirectory() {
        std::error_code error;
        std::filesystem::remove_all(path_, error);
    }
    [[nodiscard]] const std::filesystem::path& path() const noexcept { return path_; }

private:
    std::filesystem::path path_;
};

template <typename Value>
void append(std::vector<std::uint8_t>& bytes,
            const std::initializer_list<Value> values) {
    const std::size_t old_size = bytes.size();
    bytes.resize(old_size + values.size() * sizeof(Value));
    std::memcpy(bytes.data() + old_size, values.begin(), values.size() * sizeof(Value));
}

void write_bytes(const std::filesystem::path& path,
                 const std::vector<std::uint8_t>& bytes) {
    std::ofstream output(path, std::ios::binary);
    output.write(reinterpret_cast<const char*>(bytes.data()),
                 static_cast<std::streamsize>(bytes.size()));
}

[[nodiscard]] std::vector<std::uint8_t> asset_binary() {
    std::vector<std::uint8_t> bytes;
    append<float>(bytes, {0, 0, 0, 1, 0, 0, 0, 1, 0});
    append<float>(bytes, {0, 0, 1, 0, 0, 1, 0, 0, 1});
    append<float>(bytes, {0, 0, 1, 0, 0, 1});
    append<std::uint16_t>(bytes, {0, 1, 2});
    append<std::uint16_t>(bytes, {0}); // Align MAT4 data to four bytes.
    for (int matrix = 0; matrix < 2; ++matrix) {
        append<float>(bytes, {1, 0, 0, 0,
                              0, 1, 0, 0,
                              0, 0, 1, 0,
                              0, 0, 0, 1});
    }
    append<float>(bytes, {0, 1});
    append<float>(bytes, {0, 1, 0, 1, 2, 0});
    return bytes;
}

[[nodiscard]] std::string asset_json(const bool embedded_buffer) {
    const std::string buffer = embedded_buffer
        ? R"({"byteLength":264})"
        : R"({"uri":"asset.bin","byteLength":264})";
    return std::string(R"({
"asset":{"version":"2.0","generator":"RIX test"},
"buffers":[)") + buffer + R"(],
"bufferViews":[
 {"buffer":0,"byteOffset":0,"byteLength":36},
 {"buffer":0,"byteOffset":36,"byteLength":36},
 {"buffer":0,"byteOffset":72,"byteLength":24},
 {"buffer":0,"byteOffset":96,"byteLength":6},
 {"buffer":0,"byteOffset":104,"byteLength":128},
 {"buffer":0,"byteOffset":232,"byteLength":8},
 {"buffer":0,"byteOffset":240,"byteLength":24}
],
"accessors":[
 {"bufferView":0,"componentType":5126,"count":3,"type":"VEC3","min":[0,0,0],"max":[1,1,0]},
 {"bufferView":1,"componentType":5126,"count":3,"type":"VEC3"},
 {"bufferView":2,"componentType":5126,"count":3,"type":"VEC2"},
 {"bufferView":3,"componentType":5123,"count":3,"type":"SCALAR"},
 {"bufferView":4,"componentType":5126,"count":2,"type":"MAT4"},
 {"bufferView":5,"componentType":5126,"count":2,"type":"SCALAR","min":[0],"max":[1]},
 {"bufferView":6,"componentType":5126,"count":2,"type":"VEC3"}
],
"images":[{"uri":"packed.png"}],
"textures":[{"source":0}],
"materials":[{"name":"Copper","doubleSided":true,"pbrMetallicRoughness":{"baseColorFactor":[0.8,0.2,0.1,1],"metallicFactor":0.3,"roughnessFactor":0.7,"metallicRoughnessTexture":{"index":0}},"emissiveFactor":[0.2,0.1,0]}],
"meshes":[{"name":"Triangle","primitives":[{"attributes":{"POSITION":0,"NORMAL":1,"TEXCOORD_0":2},"indices":3,"material":0}]}],
"nodes":[
 {"name":"MeshNode","mesh":0,"skin":0,"translation":[2,0,0],"children":[1]},
 {"name":"Root","children":[2]},
 {"name":"Tip","translation":[0,1,0]}
],
"skins":[{"name":"Rig","joints":[1,2],"skeleton":1,"inverseBindMatrices":4}],
"animations":[{"name":"Wave","samplers":[{"input":5,"output":6,"interpolation":"LINEAR"}],"channels":[{"sampler":0,"target":{"node":2,"path":"translation"}}]}],
"scenes":[{"name":"Main","nodes":[0]}],"scene":0
})";
}

void write_gltf(const std::filesystem::path& directory) {
    const std::vector<std::uint8_t> bytes = asset_binary();
    write_bytes(directory / "asset.bin", bytes);
    write_bytes(directory / "packed.png", {0});
    std::ofstream output(directory / "asset.gltf", std::ios::binary);
    output << asset_json(false);
}

void write_gltf_without_normals(const std::filesystem::path& directory) {
    std::string json = asset_json(false);
    const std::string attribute = ",\"NORMAL\":1";
    const std::size_t offset = json.find(attribute);
    if (offset == std::string::npos) {
        throw std::runtime_error("test fixture NORMAL attribute was not found");
    }
    json.erase(offset, attribute.size());
    std::ofstream output(directory / "generated_normals.gltf", std::ios::binary);
    output << json;
}

void append_u32(std::vector<std::uint8_t>& bytes, const std::uint32_t value) {
    append<std::uint32_t>(bytes, {value});
}

void write_glb(const std::filesystem::path& path) {
    std::string json = asset_json(true);
    while (json.size() % 4 != 0) {
        json.push_back(' ');
    }
    std::vector<std::uint8_t> binary = asset_binary();
    while (binary.size() % 4 != 0) {
        binary.push_back(0);
    }
    std::vector<std::uint8_t> glb;
    append_u32(glb, 0x46546C67U);
    append_u32(glb, 2U);
    append_u32(glb, static_cast<std::uint32_t>(
                        12 + 8 + json.size() + 8 + binary.size()));
    append_u32(glb, static_cast<std::uint32_t>(json.size()));
    append_u32(glb, 0x4E4F534AU);
    glb.insert(glb.end(), json.begin(), json.end());
    append_u32(glb, static_cast<std::uint32_t>(binary.size()));
    append_u32(glb, 0x004E4942U);
    glb.insert(glb.end(), binary.begin(), binary.end());
    write_bytes(path, glb);
}

int fail(const int code, const char* const message) {
    std::cerr << message << '\n';
    return code;
}

} // namespace

int main() {
    try {
        TemporaryDirectory temporary;
        write_gltf(temporary.path());
        write_gltf_without_normals(temporary.path());
        write_glb(temporary.path() / "asset.glb");

        const auto gltf = easy3d::load_gltf(temporary.path() / "asset.gltf");
        if (gltf->parts.size() != 1 || gltf->triangle_count() != 1 ||
            gltf->materials.size() != 2 || !gltf->skeleton.has_value() ||
            gltf->animations.size() != 1) {
            return fail(1, "glTF geometry/material/skeleton/clip counts are incorrect");
        }
        const easy3d::Vertex& first = gltf->parts[0].mesh.vertices[0];
        if (!easy3d::almost_equal(first.position, {2.0F, 0.0F, 0.0F}) ||
            !easy3d::almost_equal(first.normal, {0.0F, 0.0F, 1.0F}) ||
            first.uv != easy3d::Vec2{0.0F, 0.0F} ||
            gltf->parts[0].mesh.vertices[1].uv != easy3d::Vec2{1.0F, 0.0F} ||
            gltf->parts[0].mesh.vertices[2].uv != easy3d::Vec2{0.0F, 1.0F}) {
            return fail(2, "glTF node or normal transform was not baked");
        }
        const easy3d::ModelMaterial& material = gltf->materials[1];
        if (!easy3d::almost_equal(material.metallic, 0.3F) ||
            !easy3d::almost_equal(material.roughness, 0.7F) ||
            !easy3d::almost_equal(material.emission, 0.2F) ||
            !material.packed_metallic_roughness ||
             !material.double_sided ||
            material.metallic_texture != material.roughness_texture) {
            return fail(3, "glTF PBR material factors were not imported");
        }
        const easy3d::Skeleton& skeleton = *gltf->skeleton;
        if (skeleton.joints.size() != 2 || skeleton.joints[0].parent != -1 ||
            skeleton.joints[1].parent != 0 || skeleton.joints[1].name != "Tip") {
            return fail(4, "glTF skeleton hierarchy is incorrect");
        }
        const auto pose = gltf->animations[0].sample(skeleton, 0.5F, false);
        if (pose.size() != 2 ||
            !easy3d::almost_equal(pose[1].position, {0.5F, 1.5F, 0.0F})) {
            return fail(5, "glTF animation interpolation is incorrect");
        }
        const auto looped = gltf->animations[0].sample(skeleton, 1.5F, true);
        if (!easy3d::almost_equal(looped[1].position, pose[1].position)) {
            return fail(6, "glTF animation looping is incorrect");
        }
        easy3d::AnimationClip rotation_clip;
        rotation_clip.name = "rotation";
        rotation_clip.duration = 1.0F;
        rotation_clip.channels.push_back({
            0,
            easy3d::AnimationTarget::Rotation,
            easy3d::AnimationInterpolation::Linear,
            {0.0F, 1.0F},
            {{1.0F, 0.0F, 0.0F, 0.0F}, {0.0F, 0.0F, 0.0F, 1.0F}},
        });
        const auto rotated = rotation_clip.sample(skeleton, 0.5F, false);
        const float root = std::sqrt(0.5F);
        if (!easy3d::almost_equal(rotated[0].rotation,
                                  {root, 0.0F, 0.0F, root})) {
            return fail(7, "animation quaternion slerp is incorrect");
        }
        easy3d::AnimationClip step_clip;
        step_clip.name = "step";
        step_clip.duration = 1.0F;
        step_clip.channels.push_back({
            0,
            easy3d::AnimationTarget::Translation,
            easy3d::AnimationInterpolation::Step,
            {0.0F, 1.0F},
            {{0.0F, 0.0F, 0.0F, 0.0F}, {10.0F, 0.0F, 0.0F, 0.0F}},
        });
        if (!easy3d::almost_equal(
                step_clip.sample(skeleton, 0.5F, false)[0].position,
                {0.0F, 0.0F, 0.0F})) {
            return fail(8, "animation STEP sampling is incorrect");
        }

        const auto generated =
            easy3d::load_gltf(temporary.path() / "generated_normals.gltf");
        if (!easy3d::almost_equal(generated->parts[0].mesh.vertices[0].normal,
                                  {0.0F, 0.0F, 1.0F})) {
            return fail(9, "missing glTF normals were not generated");
        }

        const auto glb = easy3d::load_gltf(temporary.path() / "asset.glb");
        if (glb->triangle_count() != 1 || !glb->skeleton.has_value() ||
            glb->animations.size() != 1) {
            return fail(10, "GLB import did not match glTF import");
        }

        easy3d::ModelCache cache;
        if (cache.load(temporary.path() / "asset.gltf")->triangle_count() != 1 ||
            cache.load(temporary.path() / "asset.glb")->triangle_count() != 1 ||
            cache.size() != 2) {
            return fail(11, "model cache did not dispatch glTF and GLB");
        }

        std::filesystem::remove(temporary.path() / "asset.bin");
        try {
            (void)easy3d::load_gltf(temporary.path() / "asset.gltf");
            return fail(12, "missing external glTF buffer was accepted");
        } catch (const easy3d::MissingAssetError&) {
        }

        std::cout << "rix_gltf_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "rix_gltf_tests: FAIL: " << error.what() << '\n';
        return 13;
    }
}
