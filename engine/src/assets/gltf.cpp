#if defined(_MSC_VER)
#define _CRT_SECURE_NO_WARNINGS
#endif
#include "easy3d/assets.hpp"

#define CGLTF_IMPLEMENTATION
#include <cgltf.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <limits>
#include <memory>
#include <sstream>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace easy3d {
namespace {

constexpr std::uintmax_t maximum_container_bytes = 512ULL * 1024ULL * 1024ULL;
constexpr std::uintmax_t maximum_total_buffer_bytes = 512ULL * 1024ULL * 1024ULL;
constexpr std::size_t maximum_vertices_per_primitive = 10'000'000;
constexpr std::size_t maximum_joints = 256;
constexpr std::size_t maximum_animations = 128;
constexpr std::size_t maximum_animation_channels = 4'096;
constexpr std::size_t maximum_animation_keys = 1'000'000;

struct CgltfDeleter final {
    void operator()(cgltf_data* data) const noexcept { cgltf_free(data); }
};

using CgltfData = std::unique_ptr<cgltf_data, CgltfDeleter>;

[[nodiscard]] std::string result_name(const cgltf_result result) {
    switch (result) {
    case cgltf_result_success:
        return "success";
    case cgltf_result_data_too_short:
        return "data too short";
    case cgltf_result_unknown_format:
        return "unknown format";
    case cgltf_result_invalid_json:
        return "invalid JSON";
    case cgltf_result_invalid_gltf:
        return "invalid glTF";
    case cgltf_result_invalid_options:
        return "invalid parser options";
    case cgltf_result_file_not_found:
        return "file not found";
    case cgltf_result_io_error:
        return "I/O error";
    case cgltf_result_out_of_memory:
        return "out of memory";
    case cgltf_result_legacy_gltf:
        return "legacy glTF 1.x is unsupported";
    default:
        return "unknown parser result";
    }
}

[[nodiscard]] std::string lowercase(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](const unsigned char value) {
        return static_cast<char>(std::tolower(value));
    });
    return value;
}

[[nodiscard]] std::filesystem::path checked_path(const std::filesystem::path& path) {
    if (path.empty()) {
        throw MissingAssetError("glTF asset path is empty");
    }
    std::error_code error;
    if (!std::filesystem::is_regular_file(path, error) || error) {
        throw MissingAssetError("glTF asset does not exist or is not a file: " +
                                path.string());
    }
    const std::string extension = lowercase(path.extension().string());
    if (extension != ".gltf" && extension != ".glb") {
        throw AssetError("unsupported glTF format '" + path.extension().string() +
                         "' for asset: " + path.string() +
                         " (supported: .gltf, .glb)");
    }
    const std::uintmax_t size = std::filesystem::file_size(path, error);
    if (error) {
        throw AssetError("failed to inspect glTF asset '" + path.string() +
                         "': " + error.message());
    }
    if (size == 0 || size > maximum_container_bytes) {
        throw AssetError("glTF container must be non-empty and no larger than 512 MiB: " +
                         path.string());
    }
    std::filesystem::path canonical = std::filesystem::weakly_canonical(path, error);
    if (error) {
        throw AssetError("failed to resolve glTF asset path '" + path.string() +
                         "': " + error.message());
    }
    return canonical;
}

[[nodiscard]] std::filesystem::path decoded_external_path(
    const char* const uri,
    const std::filesystem::path& directory,
    const char* const label) {
    std::string decoded = uri;
    decoded.resize(cgltf_decode_uri(decoded.data()));
    if (decoded.empty() || decoded.find("://") != std::string::npos ||
        std::string_view(decoded).starts_with("file:")) {
        throw AssetError(std::string("glTF ") + label +
                         " must use a local relative path: " + decoded);
    }
    std::filesystem::path result = decoded;
    if (result.is_relative()) {
        result = directory / result;
    }
    return result;
}

void preflight_external_buffers(const cgltf_data& data,
                                const std::filesystem::path& source) {
    std::uintmax_t total_bytes = 0;
    for (std::size_t index = 0; index < data.buffers_count; ++index) {
        const cgltf_buffer& buffer = data.buffers[index];
        if (buffer.uri == nullptr || std::string_view(buffer.uri).starts_with("data:")) {
            continue;
        }
        const std::filesystem::path external =
            decoded_external_path(buffer.uri, source.parent_path(), "buffer URI");
        std::error_code error;
        if (!std::filesystem::is_regular_file(external, error) || error) {
            throw MissingAssetError("glTF references a missing external buffer: " +
                                    external.string());
        }
        const std::uintmax_t size = std::filesystem::file_size(external, error);
        if (error) {
            throw AssetError("failed to inspect glTF external buffer '" +
                             external.string() + "': " + error.message());
        }
        if (size > maximum_total_buffer_bytes - total_bytes) {
            throw AssetError("glTF external buffers exceed the 512 MiB limit: " +
                             source.string());
        }
        total_bytes += size;
    }
}

[[nodiscard]] std::string name_or(const char* const name,
                                  const std::string& fallback) {
    return name == nullptr || *name == '\0' ? fallback : std::string(name);
}

[[nodiscard]] bool finite(const float value) noexcept {
    return std::isfinite(value);
}

[[nodiscard]] Vec3 transform_point(const std::array<float, 16>& matrix,
                                   const Vec3 value) noexcept {
    return {
        matrix[0] * value.x + matrix[4] * value.y + matrix[8] * value.z + matrix[12],
        matrix[1] * value.x + matrix[5] * value.y + matrix[9] * value.z + matrix[13],
        matrix[2] * value.x + matrix[6] * value.y + matrix[10] * value.z + matrix[14],
    };
}

[[nodiscard]] Vec3 transform_normal(const std::array<float, 16>& matrix,
                                    const Vec3 value,
                                    const std::filesystem::path& path) {
    const float a = matrix[0];
    const float b = matrix[4];
    const float c = matrix[8];
    const float d = matrix[1];
    const float e = matrix[5];
    const float f = matrix[9];
    const float g = matrix[2];
    const float h = matrix[6];
    const float i = matrix[10];
    const float determinant = a * (e * i - f * h) - b * (d * i - f * g) +
                              c * (d * h - e * g);
    if (!finite(determinant) || std::abs(determinant) <= 1.0e-12F) {
        throw AssetError("glTF mesh node has a singular transform: " + path.string());
    }
    const float inverse = 1.0F / determinant;
    const Vec3 transformed{
        ((e * i - f * h) * value.x + (f * g - d * i) * value.y +
         (d * h - e * g) * value.z) * inverse,
        ((c * h - b * i) * value.x + (a * i - c * g) * value.y +
         (b * g - a * h) * value.z) * inverse,
        ((b * f - c * e) * value.x + (c * d - a * f) * value.y +
         (a * e - b * d) * value.z) * inverse,
    };
    if (transformed.length_squared() <= 1.0e-12F) {
        throw AssetError("glTF contains a zero-length transformed normal: " +
                         path.string());
    }
    return transformed.normalized();
}

[[nodiscard]] const cgltf_accessor* attribute(const cgltf_primitive& primitive,
                                               const cgltf_attribute_type type,
                                               const cgltf_int index = 0) {
    for (cgltf_size item = 0; item < primitive.attributes_count; ++item) {
        const cgltf_attribute& candidate = primitive.attributes[item];
        if (candidate.type == type && candidate.index == index) {
            return candidate.data;
        }
    }
    return nullptr;
}

[[nodiscard]] std::array<float, 4> read_float(const cgltf_accessor& accessor,
                                              const std::size_t index,
                                              const std::size_t components,
                                              const char* const label,
                                              const std::filesystem::path& path) {
    std::array<float, 4> value{};
    if (!cgltf_accessor_read_float(&accessor, index, value.data(), components)) {
        throw AssetError(std::string("failed to read glTF ") + label +
                         " accessor: " + path.string());
    }
    if (!std::all_of(value.begin(), value.begin() + static_cast<std::ptrdiff_t>(components),
                     [](const float component) { return finite(component); })) {
        throw AssetError(std::string("glTF ") + label +
                         " accessor contains a non-finite value: " + path.string());
    }
    return value;
}

void generate_normals(MeshData& mesh, const std::filesystem::path& path) {
    for (Vertex& vertex : mesh.vertices) {
        vertex.normal = {};
    }
    for (std::size_t offset = 0; offset < mesh.indices.size(); offset += 3) {
        Vertex& first = mesh.vertices[mesh.indices[offset]];
        Vertex& second = mesh.vertices[mesh.indices[offset + 1]];
        Vertex& third = mesh.vertices[mesh.indices[offset + 2]];
        const Vec3 normal = (second.position - first.position)
                                .cross(third.position - first.position);
        if (normal.length_squared() <= 1.0e-12F) {
            throw AssetError("glTF contains a degenerate triangle: " + path.string());
        }
        first.normal = first.normal + normal;
        second.normal = second.normal + normal;
        third.normal = third.normal + normal;
    }
    for (Vertex& vertex : mesh.vertices) {
        if (vertex.normal.length_squared() <= 1.0e-12F) {
            throw AssetError("glTF normal generation found an unused vertex: " +
                             path.string());
        }
        vertex.normal = vertex.normal.normalized();
    }
}

[[nodiscard]] MeshData import_primitive(const cgltf_primitive& primitive,
                                        const std::array<float, 16>& transform,
                                        const std::size_t joint_count,
                                        const std::filesystem::path& path) {
    if (primitive.has_draco_mesh_compression) {
        throw AssetError("KHR_draco_mesh_compression is unsupported: " + path.string());
    }
    if (primitive.type != cgltf_primitive_type_triangles) {
        throw AssetError("glTF primitive mode must be TRIANGLES: " + path.string());
    }
    const cgltf_accessor* positions =
        attribute(primitive, cgltf_attribute_type_position);
    if (positions == nullptr || positions->type != cgltf_type_vec3 ||
        positions->count == 0 || positions->count > maximum_vertices_per_primitive) {
        throw AssetError("glTF primitive requires 1..10000000 VEC3 positions: " +
                         path.string());
    }
    const cgltf_accessor* normals = attribute(primitive, cgltf_attribute_type_normal);
    const cgltf_accessor* texcoords =
        attribute(primitive, cgltf_attribute_type_texcoord, 0);
    const cgltf_accessor* colors = attribute(primitive, cgltf_attribute_type_color, 0);
    const cgltf_accessor* joints = attribute(primitive, cgltf_attribute_type_joints, 0);
    const cgltf_accessor* weights = attribute(primitive, cgltf_attribute_type_weights, 0);
    if (normals != nullptr &&
        (normals->type != cgltf_type_vec3 || normals->count != positions->count)) {
        throw AssetError("glTF NORMAL must be VEC3 and match POSITION count: " +
                         path.string());
    }
    if (texcoords != nullptr &&
        (texcoords->type != cgltf_type_vec2 || texcoords->count != positions->count)) {
        throw AssetError("glTF TEXCOORD_0 must be VEC2 and match POSITION count: " +
                         path.string());
    }
    if (colors != nullptr &&
        ((colors->type != cgltf_type_vec3 && colors->type != cgltf_type_vec4) ||
         colors->count != positions->count)) {
        throw AssetError("glTF COLOR_0 must be VEC3/VEC4 and match POSITION count: " +
                         path.string());
    }
    if ((joints == nullptr) != (weights == nullptr)) {
        throw AssetError("glTF skinning requires both JOINTS_0 and WEIGHTS_0: " +
                         path.string());
    }
    if (joints != nullptr && joint_count == 0) {
        throw AssetError("glTF JOINTS_0/WEIGHTS_0 require a skin on the mesh node: " +
                         path.string());
    }
    if (joints != nullptr &&
        (joints->type != cgltf_type_vec4 || weights->type != cgltf_type_vec4 ||
         joints->count != positions->count || weights->count != positions->count)) {
        throw AssetError(
            "glTF JOINTS_0 and WEIGHTS_0 must be VEC4 and match POSITION count: " +
            path.string());
    }

    MeshData mesh;
    mesh.vertices.reserve(positions->count);
    for (std::size_t index = 0; index < positions->count; ++index) {
        const auto position = read_float(*positions, index, 3, "POSITION", path);
        Vertex vertex;
        vertex.position = transform_point(transform,
                                          {position[0], position[1], position[2]});
        if (normals != nullptr) {
            const auto normal = read_float(*normals, index, 3, "NORMAL", path);
            vertex.normal = transform_normal(
                transform, {normal[0], normal[1], normal[2]}, path);
        }
        if (texcoords != nullptr) {
            const auto uv = read_float(*texcoords, index, 2, "TEXCOORD_0", path);
            vertex.uv = {uv[0], uv[1]};
        }
        if (colors != nullptr) {
            const std::size_t components = colors->type == cgltf_type_vec4 ? 4U : 3U;
            const auto color = read_float(*colors, index, components, "COLOR_0", path);
            vertex.color = {std::clamp(color[0], 0.0F, 1.0F),
                            std::clamp(color[1], 0.0F, 1.0F),
                            std::clamp(color[2], 0.0F, 1.0F),
                            components == 4 ? std::clamp(color[3], 0.0F, 1.0F)
                                            : 1.0F};
        }
        if (joints != nullptr) {
            std::array<cgltf_uint, 4> joint_values{};
            if (!cgltf_accessor_read_uint(joints, index, joint_values.data(),
                                          joint_values.size())) {
                throw AssetError("failed to read glTF JOINTS_0: " + path.string());
            }
            const auto weight_values = read_float(*weights, index, 4, "WEIGHTS_0", path);
            float total = 0.0F;
            for (std::size_t influence = 0; influence < 4; ++influence) {
                if (joint_values[influence] >= joint_count ||
                    joint_values[influence] > std::numeric_limits<std::uint8_t>::max()) {
                    throw AssetError("glTF JOINTS_0 index is out of range: " +
                                     path.string());
                }
                if (!finite(weight_values[influence]) || weight_values[influence] < 0.0F) {
                    throw AssetError("glTF WEIGHTS_0 must be finite and non-negative: " +
                                     path.string());
                }
                vertex.joints[influence] =
                    static_cast<std::uint8_t>(joint_values[influence]);
                vertex.weights[influence] = weight_values[influence];
                total += weight_values[influence];
            }
            if (!finite(total) || total <= 1.0e-8F) {
                throw AssetError("glTF skinned vertex has no effective weight: " +
                                 path.string());
            }
            for (float& weight : vertex.weights) weight /= total;
        }
        mesh.vertices.push_back(vertex);
    }

    const std::size_t index_count =
        primitive.indices == nullptr ? positions->count : primitive.indices->count;
    if (index_count == 0 || index_count % 3 != 0 ||
        index_count > std::numeric_limits<std::uint32_t>::max()) {
        throw AssetError("glTF triangle index count is invalid: " + path.string());
    }
    mesh.indices.reserve(index_count);
    for (std::size_t index = 0; index < index_count; ++index) {
        const std::size_t value = primitive.indices == nullptr
            ? index
            : cgltf_accessor_read_index(primitive.indices, index);
        if (value >= positions->count || value > std::numeric_limits<std::uint32_t>::max()) {
            throw AssetError("glTF index references an out-of-range vertex: " +
                             path.string());
        }
        mesh.indices.push_back(static_cast<std::uint32_t>(value));
    }
    if (normals == nullptr) {
        generate_normals(mesh, path);
    }
    generate_tangents(mesh);
    mesh.validate();
    return mesh;
}

[[nodiscard]] std::optional<std::filesystem::path> external_texture(
    const cgltf_texture_view& view,
    const std::string& material_name,
    const char* label,
    const std::filesystem::path& directory,
    std::vector<std::string>& warnings) {
    if (view.texture == nullptr || view.texture->image == nullptr) {
        return std::nullopt;
    }
    const cgltf_image& image = *view.texture->image;
    if (image.buffer_view != nullptr || image.uri == nullptr ||
        std::string_view(image.uri).starts_with("data:")) {
        warnings.push_back("embedded " + std::string(label) + " image for material '" +
                           material_name + "' is not rendered by the base-pose path");
        return std::nullopt;
    }
    std::filesystem::path texture =
        decoded_external_path(image.uri, directory, "image URI");
    std::error_code error;
    if (!std::filesystem::is_regular_file(texture, error) || error) {
        throw MissingAssetError("glTF material '" + material_name +
                                "' references a missing " + label + " image: " +
                                texture.string());
    }
    texture = std::filesystem::weakly_canonical(texture, error);
    if (error) {
        throw AssetError("failed to resolve glTF image path '" + texture.string() +
                         "': " + error.message());
    }
    return texture;
}

[[nodiscard]] std::optional<std::filesystem::path> companion_texture(
    const std::optional<std::filesystem::path>& base,
    const char* suffix) {
    if (!base.has_value()) {
        return std::nullopt;
    }
    const std::filesystem::path candidate =
        base->parent_path() / (base->stem().string() + suffix + ".png");
    std::error_code error;
    if (!std::filesystem::is_regular_file(candidate, error) || error) {
        return std::nullopt;
    }
    const std::filesystem::path canonical =
        std::filesystem::weakly_canonical(candidate, error);
    return error ? std::nullopt : std::optional<std::filesystem::path>(canonical);
}

void import_materials(const cgltf_data& data,
                      const std::filesystem::path& directory,
                      ModelData& model) {
    model.materials.push_back(ModelMaterial{});
    for (std::size_t index = 0; index < data.materials_count; ++index) {
        const cgltf_material& source = data.materials[index];
        ModelMaterial material;
        material.name = name_or(source.name, "material_" + std::to_string(index));
        material.authored_surface = true;
        material.double_sided = source.double_sided != 0;
        if (source.has_pbr_metallic_roughness) {
            const auto& pbr = source.pbr_metallic_roughness;
            material.diffuse_color = {
                std::clamp(pbr.base_color_factor[0], 0.0F, 1.0F),
                std::clamp(pbr.base_color_factor[1], 0.0F, 1.0F),
                std::clamp(pbr.base_color_factor[2], 0.0F, 1.0F),
                std::clamp(pbr.base_color_factor[3], 0.0F, 1.0F),
            };
            material.metallic = std::clamp(pbr.metallic_factor, 0.0F, 1.0F);
            material.roughness = std::clamp(pbr.roughness_factor, 0.04F, 1.0F);
        }
        const float emissive_strength =
            source.has_emissive_strength ? source.emissive_strength.emissive_strength
                                         : 1.0F;
        material.emission = std::clamp(
            std::max({source.emissive_factor[0],
                      source.emissive_factor[1],
                      source.emissive_factor[2]}) * emissive_strength,
            0.0F,
            100.0F);
        material.diffuse_texture =
            source.has_pbr_metallic_roughness
                ? external_texture(source.pbr_metallic_roughness.base_color_texture,
                                   material.name,
                                   "base-color",
                                   directory,
                                   model.warnings)
                : std::nullopt;
        material.normal_texture = external_texture(source.normal_texture,
                                                   material.name,
                                                   "normal",
                                                   directory,
                                                   model.warnings);
        material.emissive_texture = external_texture(source.emissive_texture,
                                                     material.name,
                                                     "emissive",
                                                     directory,
                                                     model.warnings);
        material.ambient_occlusion_texture = external_texture(source.occlusion_texture,
                                                              material.name,
                                                              "occlusion",
                                                              directory,
                                                              model.warnings);
        if (source.has_pbr_metallic_roughness) {
            const auto packed = external_texture(
                source.pbr_metallic_roughness.metallic_roughness_texture,
                material.name,
                "metallic-roughness",
                directory,
                model.warnings);
            material.roughness_texture = packed;
            material.metallic_texture = packed;
            material.packed_metallic_roughness = packed.has_value();
        }
        if (!material.normal_texture.has_value()) {
            material.normal_texture = companion_texture(material.diffuse_texture, "_normal");
        }
        if (!material.roughness_texture.has_value()) {
            material.roughness_texture =
                companion_texture(material.diffuse_texture, "_roughness");
        }
        if (!material.metallic_texture.has_value()) {
            material.metallic_texture =
                companion_texture(material.diffuse_texture, "_metallic");
        }
        if (!material.emissive_texture.has_value()) {
            material.emissive_texture =
                companion_texture(material.diffuse_texture, "_emissive");
        }
        if (!material.ambient_occlusion_texture.has_value()) {
            material.ambient_occlusion_texture =
                companion_texture(material.diffuse_texture, "_ao");
        }
        material.normal_strength = source.normal_texture.texture != nullptr
                                       ? std::clamp(source.normal_texture.scale, 0.0F, 8.0F)
                                       : 1.0F;
        if (source.alpha_mode == cgltf_alpha_mode_blend ||
            source.alpha_mode == cgltf_alpha_mode_mask) {
            model.warnings.push_back("material '" + material.name +
                                     "' alpha mode is rendered as ordinary opaque geometry");
        }
        model.materials.push_back(std::move(material));
    }
}

void import_node_mesh(const cgltf_data& data,
                      const cgltf_node& node,
                      const std::filesystem::path& path,
                      ModelData& model) {
    if (node.mesh == nullptr) {
        return;
    }
    std::array<float, 16> transform{};
    cgltf_node_transform_world(&node, transform.data());
    const std::string node_name = name_or(node.name, "node");
    const std::string mesh_name = name_or(node.mesh->name, "mesh");
    for (std::size_t primitive_index = 0;
         primitive_index < node.mesh->primitives_count;
         ++primitive_index) {
        const cgltf_primitive& primitive = node.mesh->primitives[primitive_index];
        std::size_t material_index = 0;
        if (primitive.material != nullptr) {
            material_index = static_cast<std::size_t>(primitive.material - data.materials) + 1U;
            if (material_index >= model.materials.size()) {
                throw AssetError("glTF primitive material index is invalid: " + path.string());
            }
        }
        model.parts.push_back({node_name + ":" + mesh_name + ":" +
                                   std::to_string(primitive_index),
                               import_primitive(
                                   primitive, transform,
                                   node.skin != nullptr ? node.skin->joints_count : 0U,
                                   path),
                               material_index});
    }
}

void import_node_tree(const cgltf_data& data,
                      const cgltf_node& node,
                      const std::filesystem::path& path,
                      ModelData& model,
                      const std::size_t depth) {
    if (depth > 256) {
        throw AssetError("glTF scene hierarchy exceeds 256 levels: " + path.string());
    }
    import_node_mesh(data, node, path, model);
    for (std::size_t index = 0; index < node.children_count; ++index) {
        if (node.children[index] == nullptr) {
            throw AssetError("glTF node contains a null child: " + path.string());
        }
        import_node_tree(data, *node.children[index], path, model, depth + 1U);
    }
}

[[nodiscard]] Transform joint_transform(const cgltf_node& node,
                                        const std::filesystem::path& path) {
    if (node.has_matrix) {
        throw AssetError("matrix-authored skeleton joints are unsupported; use TRS: " +
                         path.string());
    }
    Transform result;
    if (node.has_translation) {
        result.position = {node.translation[0], node.translation[1], node.translation[2]};
    }
    if (node.has_rotation) {
        result.rotation = Quat{node.rotation[3],
                               node.rotation[0],
                               node.rotation[1],
                               node.rotation[2]}.normalized();
    }
    if (node.has_scale) {
        result.scale = {node.scale[0], node.scale[1], node.scale[2]};
    }
    return result;
}

[[nodiscard]] std::unordered_map<const cgltf_node*, std::size_t> import_skeleton(
    const cgltf_data& data,
    const std::filesystem::path& path,
    ModelData& model) {
    std::unordered_map<const cgltf_node*, std::size_t> joint_indices;
    if (data.skins_count == 0) {
        return joint_indices;
    }
    if (data.skins_count > 1) {
        throw AssetError("Phase 6.4 supports one glTF skin per asset: " + path.string());
    }
    const cgltf_skin& source = data.skins[0];
    if (source.joints_count == 0 || source.joints_count > maximum_joints) {
        throw AssetError("glTF skin must contain 1..256 joints: " + path.string());
    }
    Skeleton skeleton;
    skeleton.name = name_or(source.name, "skeleton");
    skeleton.joints.resize(source.joints_count);
    joint_indices.reserve(source.joints_count);
    for (std::size_t index = 0; index < source.joints_count; ++index) {
        if (source.joints[index] == nullptr ||
            !joint_indices.emplace(source.joints[index], index).second) {
            throw AssetError("glTF skin contains a null or duplicate joint: " +
                             path.string());
        }
    }
    if (source.inverse_bind_matrices != nullptr &&
        (source.inverse_bind_matrices->type != cgltf_type_mat4 ||
         source.inverse_bind_matrices->count != source.joints_count)) {
        throw AssetError("glTF inverse bind accessor must be MAT4 per joint: " +
                         path.string());
    }
    for (std::size_t index = 0; index < source.joints_count; ++index) {
        const cgltf_node& node = *source.joints[index];
        SkeletonJoint& joint = skeleton.joints[index];
        joint.name = name_or(node.name, "joint_" + std::to_string(index));
        joint.local_bind = joint_transform(node, path);
        const cgltf_node* parent = node.parent;
        while (parent != nullptr && !joint_indices.contains(parent)) {
            parent = parent->parent;
        }
        if (parent != nullptr && parent != node.parent) {
            throw AssetError(
                "glTF joint chains with non-joint intermediary nodes are unsupported: " +
                path.string());
        }
        if (parent != nullptr) {
            joint.parent = static_cast<std::int32_t>(joint_indices.at(parent));
        }
        if (source.inverse_bind_matrices != nullptr) {
            if (!cgltf_accessor_read_float(source.inverse_bind_matrices,
                                           index,
                                           joint.inverse_bind.values.data(),
                                           16)) {
                throw AssetError("failed to read glTF inverse bind matrix: " +
                                 path.string());
            }
        }
    }
    skeleton.validate();
    model.skeleton = std::move(skeleton);
    return joint_indices;
}

[[nodiscard]] AnimationTarget animation_target(const cgltf_animation_path_type path,
                                               const std::filesystem::path& source) {
    switch (path) {
    case cgltf_animation_path_type_translation:
        return AnimationTarget::Translation;
    case cgltf_animation_path_type_rotation:
        return AnimationTarget::Rotation;
    case cgltf_animation_path_type_scale:
        return AnimationTarget::Scale;
    default:
        throw AssetError("glTF animation morph-weight channels are unsupported: " +
                         source.string());
    }
}

[[nodiscard]] AnimationInterpolation animation_interpolation(
    const cgltf_interpolation_type interpolation,
    const std::filesystem::path& path) {
    if (interpolation == cgltf_interpolation_type_linear) {
        return AnimationInterpolation::Linear;
    }
    if (interpolation == cgltf_interpolation_type_step) {
        return AnimationInterpolation::Step;
    }
    throw AssetError("glTF CUBICSPLINE animation is unsupported: " + path.string());
}

void import_animations(const cgltf_data& data,
                       const std::unordered_map<const cgltf_node*, std::size_t>& joints,
                       const std::filesystem::path& path,
                       ModelData& model) {
    if (data.animations_count > maximum_animations) {
        throw AssetError("glTF asset exceeds 128 animation clips: " + path.string());
    }
    for (std::size_t animation_index = 0;
         animation_index < data.animations_count;
         ++animation_index) {
        const cgltf_animation& source = data.animations[animation_index];
        if (source.channels_count > maximum_animation_channels) {
            throw AssetError("glTF clip exceeds 4096 channels: " + path.string());
        }
        AnimationClip clip;
        clip.name = name_or(source.name, "animation_" + std::to_string(animation_index));
        for (std::size_t channel_index = 0;
             channel_index < source.channels_count;
             ++channel_index) {
            const cgltf_animation_channel& source_channel =
                source.channels[channel_index];
            if (source_channel.target_node == nullptr || source_channel.sampler == nullptr) {
                throw AssetError("glTF animation channel is incomplete: " + path.string());
            }
            const auto joint = joints.find(source_channel.target_node);
            if (joint == joints.end()) {
                model.warnings.push_back("animation '" + clip.name +
                                         "' channel targeting a non-joint node was ignored");
                continue;
            }
            const cgltf_animation_sampler& sampler = *source_channel.sampler;
            if (sampler.input == nullptr || sampler.output == nullptr ||
                sampler.input->type != cgltf_type_scalar || sampler.input->count == 0 ||
                sampler.input->count > maximum_animation_keys ||
                sampler.output->count != sampler.input->count) {
                throw AssetError("glTF animation sampler input/output counts are invalid: " +
                                 path.string());
            }
            AnimationChannel channel;
            channel.joint_index = joint->second;
            channel.target = animation_target(source_channel.target_path, path);
            channel.interpolation = animation_interpolation(sampler.interpolation, path);
            const cgltf_type required_type = channel.target == AnimationTarget::Rotation
                ? cgltf_type_vec4
                : cgltf_type_vec3;
            if (sampler.output->type != required_type) {
                throw AssetError("glTF animation output accessor has the wrong vector type: " +
                                 path.string());
            }
            channel.times.reserve(sampler.input->count);
            channel.values.reserve(sampler.input->count);
            for (std::size_t key = 0; key < sampler.input->count; ++key) {
                const auto time = read_float(*sampler.input, key, 1, "animation time", path);
                if (time[0] < 0.0F ||
                    (!channel.times.empty() && time[0] <= channel.times.back())) {
                    throw AssetError("glTF animation times must be non-negative and increasing: " +
                                     path.string());
                }
                channel.times.push_back(time[0]);
                const std::size_t components =
                    channel.target == AnimationTarget::Rotation ? 4U : 3U;
                auto value = read_float(
                    *sampler.output, key, components, "animation output", path);
                if (channel.target == AnimationTarget::Rotation) {
                    const Quat rotation =
                        Quat{value[3], value[0], value[1], value[2]}.normalized();
                    value = {rotation.w, rotation.x, rotation.y, rotation.z};
                }
                channel.values.push_back(value);
            }
            clip.duration = std::max(clip.duration, channel.times.back());
            clip.channels.push_back(std::move(channel));
        }
        if (clip.channels.empty()) {
            model.warnings.push_back("animation '" + clip.name +
                                     "' had no skeletal channels and was ignored");
            continue;
        }
        clip.validate(model.skeleton->joints.size());
        model.animations.push_back(std::move(clip));
    }
}

[[nodiscard]] float quaternion_dot(const Quat left, const Quat right) noexcept {
    return left.w * right.w + left.x * right.x + left.y * right.y + left.z * right.z;
}

[[nodiscard]] Quat slerp(Quat left, Quat right, const float amount) {
    float cosine = quaternion_dot(left, right);
    if (cosine < 0.0F) {
        right = {-right.w, -right.x, -right.y, -right.z};
        cosine = -cosine;
    }
    if (cosine > 0.9995F) {
        return Quat{left.w + (right.w - left.w) * amount,
                    left.x + (right.x - left.x) * amount,
                    left.y + (right.y - left.y) * amount,
                    left.z + (right.z - left.z) * amount}.normalized();
    }
    const float angle = std::acos(std::clamp(cosine, -1.0F, 1.0F));
    const float sine = std::sin(angle);
    const float first = std::sin((1.0F - amount) * angle) / sine;
    const float second = std::sin(amount * angle) / sine;
    return Quat{left.w * first + right.w * second,
                left.x * first + right.x * second,
                left.y * first + right.y * second,
                left.z * first + right.z * second}.normalized();
}

} // namespace

void Skeleton::validate() const {
    if (joints.empty() || joints.size() > maximum_joints) {
        throw AssetError("skeleton must contain 1..256 joints");
    }
    for (std::size_t index = 0; index < joints.size(); ++index) {
        const SkeletonJoint& joint = joints[index];
        if (joint.parent < -1 || joint.parent >= static_cast<std::int32_t>(joints.size()) ||
            joint.parent == static_cast<std::int32_t>(index)) {
            throw AssetError("skeleton joint parent index is invalid");
        }
        if (!finite(joint.local_bind.position.x) || !finite(joint.local_bind.position.y) ||
            !finite(joint.local_bind.position.z) || !finite(joint.local_bind.scale.x) ||
            !finite(joint.local_bind.scale.y) || !finite(joint.local_bind.scale.z) ||
            !finite(joint.local_bind.rotation.w) ||
            !finite(joint.local_bind.rotation.x) ||
            !finite(joint.local_bind.rotation.y) ||
            !finite(joint.local_bind.rotation.z) ||
            joint.local_bind.rotation.length_squared() <= 1.0e-12F ||
            joint.local_bind.scale.x == 0.0F || joint.local_bind.scale.y == 0.0F ||
            joint.local_bind.scale.z == 0.0F) {
            throw AssetError("skeleton joint bind transform is invalid");
        }
        if (!std::all_of(joint.inverse_bind.values.begin(),
                         joint.inverse_bind.values.end(),
                         [](const float value) { return finite(value); })) {
            throw AssetError("skeleton inverse bind matrix contains a non-finite value");
        }
        std::size_t traversed = 0;
        std::int32_t parent = joint.parent;
        while (parent >= 0) {
            if (++traversed > joints.size()) {
                throw AssetError("skeleton joint hierarchy contains a cycle");
            }
            parent = joints[static_cast<std::size_t>(parent)].parent;
        }
    }
}

void AnimationChannel::validate(const std::size_t joint_count) const {
    if (joint_index >= joint_count || times.empty() || times.size() != values.size() ||
        times.size() > maximum_animation_keys) {
        throw AssetError("animation channel bounds are invalid");
    }
    for (std::size_t index = 0; index < times.size(); ++index) {
        if (!finite(times[index]) || times[index] < 0.0F ||
            (index > 0 && times[index] <= times[index - 1])) {
            throw AssetError("animation channel times must be finite and increasing");
        }
        if (!std::all_of(values[index].begin(), values[index].end(),
                         [](const float value) { return finite(value); })) {
            throw AssetError("animation channel contains a non-finite value");
        }
    }
}

void AnimationClip::validate(const std::size_t joint_count) const {
    if (!finite(duration) || duration < 0.0F || channels.empty() ||
        channels.size() > maximum_animation_channels) {
        throw AssetError("animation clip bounds are invalid");
    }
    for (const AnimationChannel& channel : channels) {
        channel.validate(joint_count);
        if (channel.times.back() > duration) {
            throw AssetError("animation channel extends beyond clip duration");
        }
    }
}

std::vector<Transform> AnimationClip::sample(const Skeleton& skeleton,
                                             const float time_seconds,
                                             const bool loop) const {
    skeleton.validate();
    validate(skeleton.joints.size());
    if (!finite(time_seconds) || time_seconds < 0.0F) {
        throw std::invalid_argument("animation sample time must be finite and non-negative");
    }
    float sample_time = time_seconds;
    if (duration > 0.0F) {
        sample_time = loop ? std::fmod(time_seconds, duration)
                           : std::min(time_seconds, duration);
    }
    std::vector<Transform> pose;
    pose.reserve(skeleton.joints.size());
    for (const SkeletonJoint& joint : skeleton.joints) {
        pose.push_back(joint.local_bind);
    }
    for (const AnimationChannel& channel : channels) {
        const auto upper = std::upper_bound(channel.times.begin(),
                                            channel.times.end(),
                                            sample_time);
        std::size_t first = 0;
        std::size_t second = 0;
        float amount = 0.0F;
        if (upper == channel.times.begin()) {
            first = second = 0;
        } else if (upper == channel.times.end()) {
            first = second = channel.times.size() - 1U;
        } else {
            second = static_cast<std::size_t>(upper - channel.times.begin());
            first = second - 1U;
            if (channel.interpolation == AnimationInterpolation::Linear) {
                amount = (sample_time - channel.times[first]) /
                         (channel.times[second] - channel.times[first]);
            }
        }
        const auto& left = channel.values[first];
        const auto& right = channel.values[second];
        Transform& joint = pose[channel.joint_index];
        if (channel.target == AnimationTarget::Rotation) {
            joint.rotation = slerp({left[0], left[1], left[2], left[3]},
                                   {right[0], right[1], right[2], right[3]},
                                   amount);
            continue;
        }
        const Vec3 value{left[0] + (right[0] - left[0]) * amount,
                         left[1] + (right[1] - left[1]) * amount,
                         left[2] + (right[2] - left[2]) * amount};
        if (channel.target == AnimationTarget::Translation) {
            joint.position = value;
        } else {
            joint.scale = value;
        }
    }
    return pose;
}

std::shared_ptr<const ModelData> load_gltf(const std::filesystem::path& path) {
    const std::filesystem::path canonical = checked_path(path);
    cgltf_options options{};
    cgltf_data* raw_data = nullptr;
    const cgltf_result parse_result =
        cgltf_parse_file(&options, canonical.string().c_str(), &raw_data);
    CgltfData data(raw_data);
    if (parse_result != cgltf_result_success || data == nullptr) {
        throw AssetError("failed to parse glTF asset '" + canonical.string() +
                         "': " + result_name(parse_result));
    }
    if (data->extensions_required_count != 0) {
        std::ostringstream extensions;
        for (std::size_t index = 0; index < data->extensions_required_count; ++index) {
            if (index != 0) {
                extensions << ", ";
            }
            extensions << data->extensions_required[index];
        }
        throw AssetError("glTF required extensions are unsupported (" +
                         extensions.str() + "): " + canonical.string());
    }
    std::uintmax_t total_buffer_bytes = 0;
    for (std::size_t index = 0; index < data->buffers_count; ++index) {
        if (data->buffers[index].size > maximum_total_buffer_bytes - total_buffer_bytes) {
            throw AssetError("glTF declared buffers exceed the 512 MiB limit: " +
                             canonical.string());
        }
        total_buffer_bytes += data->buffers[index].size;
    }
    preflight_external_buffers(*data, canonical);
    const cgltf_result load_result =
        cgltf_load_buffers(&options, data.get(), canonical.string().c_str());
    if (load_result == cgltf_result_file_not_found) {
        throw MissingAssetError("glTF references a missing external buffer: " +
                                canonical.string());
    }
    if (load_result != cgltf_result_success) {
        throw AssetError("failed to load glTF buffers for '" + canonical.string() +
                         "': " + result_name(load_result));
    }
    const cgltf_result validation_result = cgltf_validate(data.get());
    if (validation_result != cgltf_result_success) {
        throw AssetError("failed to validate glTF asset '" + canonical.string() +
                         "': " + result_name(validation_result));
    }

    auto model = std::make_shared<ModelData>();
    model->source_path = canonical;
    import_materials(*data, canonical.parent_path(), *model);
    if (data->scene != nullptr) {
        for (std::size_t index = 0; index < data->scene->nodes_count; ++index) {
            if (data->scene->nodes[index] == nullptr) {
                throw AssetError("glTF default scene contains a null root node: " +
                                 canonical.string());
            }
            import_node_tree(*data,
                             *data->scene->nodes[index],
                             canonical,
                             *model,
                             0);
        }
    } else {
        for (std::size_t index = 0; index < data->nodes_count; ++index) {
            if (data->nodes[index].parent == nullptr) {
                import_node_tree(*data, data->nodes[index], canonical, *model, 0);
            }
        }
    }
    const auto joints = import_skeleton(*data, canonical, *model);
    if (data->animations_count != 0 && !model->skeleton.has_value()) {
        model->warnings.push_back(
            "node animations were ignored because the asset has no supported skin");
    } else if (model->skeleton.has_value()) {
        import_animations(*data, joints, canonical, *model);
    }
    model->validate();
    return model;
}

} // namespace easy3d
