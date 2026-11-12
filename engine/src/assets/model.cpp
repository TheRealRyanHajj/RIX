#include "easy3d/assets.hpp"

#include <tiny_obj_loader.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <limits>
#include <map>
#include <sstream>
#include <system_error>
#include <unordered_map>
#include <utility>

namespace easy3d {
namespace {

struct VertexKey final {
    int vertex{-1};
    int normal{-1};
    int texcoord{-1};

    friend bool operator==(const VertexKey&, const VertexKey&) = default;
};

struct VertexKeyHash final {
    [[nodiscard]] std::size_t operator()(const VertexKey& key) const noexcept {
        std::size_t value = std::hash<int>{}(key.vertex);
        value ^= std::hash<int>{}(key.normal) + 0x9e3779b9U + (value << 6U) + (value >> 2U);
        value ^= std::hash<int>{}(key.texcoord) + 0x9e3779b9U + (value << 6U) +
                 (value >> 2U);
        return value;
    }
};

struct PartBuilder final {
    MeshData mesh;
    std::unordered_map<VertexKey, std::uint32_t, VertexKeyHash> vertices;
};

[[nodiscard]] std::string lowercase(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](const unsigned char character) {
        return static_cast<char>(std::tolower(character));
    });
    return value;
}

[[nodiscard]] std::filesystem::path checked_obj_path(const std::filesystem::path& path) {
    if (path.empty()) {
        throw MissingAssetError("model asset path is empty");
    }
    std::error_code error;
    if (!std::filesystem::is_regular_file(path, error) || error) {
        throw MissingAssetError("model asset does not exist or is not a file: " +
                                path.string());
    }
    if (lowercase(path.extension().string()) != ".obj") {
        throw AssetError("unsupported model format '" + path.extension().string() +
                         "' for asset: " + path.string() + " (supported: .obj)");
    }
    std::filesystem::path canonical = std::filesystem::weakly_canonical(path, error);
    if (error) {
        throw AssetError("failed to resolve model asset path '" + path.string() +
                         "': " + error.message());
    }
    return canonical;
}

[[nodiscard]] std::filesystem::path checked_model_path(
    const std::filesystem::path& path) {
    if (path.empty()) {
        throw MissingAssetError("model asset path is empty");
    }
    std::error_code error;
    if (!std::filesystem::is_regular_file(path, error) || error) {
        throw MissingAssetError("model asset does not exist or is not a file: " +
                                path.string());
    }
    const std::string extension = lowercase(path.extension().string());
    if (extension != ".obj" && extension != ".gltf" && extension != ".glb" &&
        extension != ".fbx") {
        throw AssetError("unsupported model format '" + path.extension().string() +
                         "' for asset: " + path.string() +
                         " (supported: .obj, .gltf, .glb, .fbx)");
    }
    std::filesystem::path canonical = std::filesystem::weakly_canonical(path, error);
    if (error) {
        throw AssetError("failed to resolve model asset path '" + path.string() +
                         "': " + error.message());
    }
    return canonical;
}

[[nodiscard]] std::string model_cache_key(const std::filesystem::path& canonical) {
    std::string key = canonical.generic_string();
#if defined(_WIN32)
    key = lowercase(std::move(key));
#endif
    return key;
}

[[nodiscard]] float component(const std::vector<tinyobj::real_t>& values,
                              const int index,
                              const int channel,
                              const char* attribute,
                              const std::filesystem::path& path) {
    if (index < 0) {
        throw AssetError(std::string("OBJ contains a missing ") + attribute +
                         " index: " + path.string());
    }
    const std::size_t offset = static_cast<std::size_t>(index) * 3U +
                               static_cast<std::size_t>(channel);
    if (offset >= values.size()) {
        throw AssetError(std::string("OBJ contains an out-of-range ") + attribute +
                         " index: " + path.string());
    }
    return static_cast<float>(values[offset]);
}

[[nodiscard]] Vec3 position_at(const tinyobj::attrib_t& attributes,
                               const tinyobj::index_t index,
                               const std::filesystem::path& path) {
    return {
        component(attributes.vertices, index.vertex_index, 0, "position", path),
        component(attributes.vertices, index.vertex_index, 1, "position", path),
        component(attributes.vertices, index.vertex_index, 2, "position", path),
    };
}

[[nodiscard]] Vec3 normal_at(const tinyobj::attrib_t& attributes,
                             const tinyobj::index_t index,
                             const std::filesystem::path& path) {
    return Vec3{
        component(attributes.normals, index.normal_index, 0, "normal", path),
        component(attributes.normals, index.normal_index, 1, "normal", path),
        component(attributes.normals, index.normal_index, 2, "normal", path),
    }.normalized();
}

[[nodiscard]] Vec2 uv_at(const tinyobj::attrib_t& attributes,
                         const tinyobj::index_t index,
                         const std::filesystem::path& path) {
    if (index.texcoord_index < 0) {
        return {};
    }
    const std::size_t offset = static_cast<std::size_t>(index.texcoord_index) * 2U;
    if (offset + 1U >= attributes.texcoords.size()) {
        throw AssetError("OBJ contains an out-of-range texture coordinate index: " +
                         path.string());
    }
    return {static_cast<float>(attributes.texcoords[offset]),
            1.0F - static_cast<float>(attributes.texcoords[offset + 1U])};
}

[[nodiscard]] Color color_at(const tinyobj::attrib_t& attributes,
                             const tinyobj::index_t index) {
    if (index.vertex_index < 0) {
        return {};
    }
    const std::size_t offset = static_cast<std::size_t>(index.vertex_index) * 3U;
    if (offset + 2U >= attributes.colors.size()) {
        return {};
    }
    return {std::clamp(static_cast<float>(attributes.colors[offset]), 0.0F, 1.0F),
            std::clamp(static_cast<float>(attributes.colors[offset + 1U]), 0.0F, 1.0F),
            std::clamp(static_cast<float>(attributes.colors[offset + 2U]), 0.0F, 1.0F),
            1.0F};
}

[[nodiscard]] std::uint32_t append_vertex(PartBuilder& part,
                                          const tinyobj::attrib_t& attributes,
                                          const tinyobj::index_t index,
                                          const std::filesystem::path& path) {
    const VertexKey key{index.vertex_index, index.normal_index, index.texcoord_index};
    const auto found = part.vertices.find(key);
    if (found != part.vertices.end()) {
        return found->second;
    }
    if (part.mesh.vertices.size() >= std::numeric_limits<std::uint32_t>::max()) {
        throw AssetError("OBJ exceeds RIX's 32-bit vertex limit: " + path.string());
    }
    const std::uint32_t result = static_cast<std::uint32_t>(part.mesh.vertices.size());
    part.mesh.vertices.push_back(
        {position_at(attributes, index, path),
         normal_at(attributes, index, path),
         uv_at(attributes, index, path),
         color_at(attributes, index)});
    part.vertices.emplace(key, result);
    return result;
}

void append_flat_triangle(PartBuilder& part,
                          const tinyobj::attrib_t& attributes,
                          const std::array<tinyobj::index_t, 3>& indices,
                          const std::filesystem::path& path) {
    const std::array<Vec3, 3> positions{
        position_at(attributes, indices[0], path),
        position_at(attributes, indices[1], path),
        position_at(attributes, indices[2], path),
    };
    const Vec3 cross = (positions[1] - positions[0]).cross(positions[2] - positions[0]);
    if (cross.length_squared() <= 1.0e-12F) {
        throw AssetError("OBJ contains a degenerate triangle: " + path.string());
    }
    const Vec3 normal = cross.normalized();
    for (std::size_t corner = 0; corner < indices.size(); ++corner) {
        if (part.mesh.vertices.size() >= std::numeric_limits<std::uint32_t>::max()) {
            throw AssetError("OBJ exceeds RIX's 32-bit vertex limit: " + path.string());
        }
        part.mesh.indices.push_back(static_cast<std::uint32_t>(part.mesh.vertices.size()));
        part.mesh.vertices.push_back({positions[corner],
                                      normal,
                                      uv_at(attributes, indices[corner], path),
                                      color_at(attributes, indices[corner])});
    }
}

[[nodiscard]] std::optional<std::filesystem::path> resolve_material_texture(
    const std::string& filename,
    const std::filesystem::path& directory,
    const std::string& material_name,
    const char* label) {
    if (filename.empty()) {
        return std::nullopt;
    }
    std::filesystem::path texture = filename;
    if (texture.is_relative()) {
        texture = directory / texture;
    }
    std::error_code error;
    if (!std::filesystem::is_regular_file(texture, error) || error) {
        throw MissingAssetError("OBJ material '" + material_name +
                                "' references a missing " + label + " texture: " +
                                texture.string());
    }
    texture = std::filesystem::weakly_canonical(texture, error);
    if (error) {
        throw AssetError("failed to resolve OBJ " + std::string(label) +
                         " texture path '" + texture.string() + "': " +
                         error.message());
    }
    return texture;
}

[[nodiscard]] std::optional<std::filesystem::path> discovered_companion(
    const std::optional<std::filesystem::path>& base,
    const char* suffix) {
    if (!base.has_value()) {
        return std::nullopt;
    }
    const std::filesystem::path candidate =
        base->parent_path() / (base->stem().string() + suffix + ".png");
    std::error_code error;
    return std::filesystem::is_regular_file(candidate, error) && !error
               ? std::optional<std::filesystem::path>(
                     std::filesystem::weakly_canonical(candidate, error))
               : std::nullopt;
}

[[nodiscard]] ModelMaterial convert_material(const tinyobj::material_t& source,
                                             const std::filesystem::path& directory) {
    ModelMaterial material;
    material.name = source.name.empty() ? "unnamed" : source.name;
    material.diffuse_color = {
        std::clamp(static_cast<float>(source.diffuse[0]), 0.0F, 1.0F),
        std::clamp(static_cast<float>(source.diffuse[1]), 0.0F, 1.0F),
        std::clamp(static_cast<float>(source.diffuse[2]), 0.0F, 1.0F),
        std::clamp(static_cast<float>(source.dissolve), 0.0F, 1.0F),
    };
    material.diffuse_texture = resolve_material_texture(
        source.diffuse_texname, directory, material.name, "diffuse");
    material.normal_texture = resolve_material_texture(
        source.normal_texname, directory, material.name, "normal");
    material.roughness_texture = resolve_material_texture(
        source.roughness_texname, directory, material.name, "roughness");
    material.metallic_texture = resolve_material_texture(
        source.metallic_texname, directory, material.name, "metallic");
    material.emissive_texture = resolve_material_texture(
        source.emissive_texname, directory, material.name, "emissive");
    material.ambient_occlusion_texture = resolve_material_texture(
        source.ambient_texname, directory, material.name, "ambient-occlusion");
    if (!material.normal_texture.has_value()) {
        material.normal_texture = discovered_companion(material.diffuse_texture, "_normal");
    }
    if (!material.roughness_texture.has_value()) {
        material.roughness_texture =
            discovered_companion(material.diffuse_texture, "_roughness");
    }
    if (!material.metallic_texture.has_value()) {
        material.metallic_texture =
            discovered_companion(material.diffuse_texture, "_metallic");
    }
    if (!material.emissive_texture.has_value()) {
        material.emissive_texture =
            discovered_companion(material.diffuse_texture, "_emissive");
    }
    if (!material.ambient_occlusion_texture.has_value()) {
        material.ambient_occlusion_texture =
            discovered_companion(material.diffuse_texture, "_ao");
    }
    return material;
}

} // namespace

void ModelData::validate() const {
    if (source_path.empty()) {
        throw AssetError("model source path must not be empty");
    }
    if (materials.empty()) {
        throw AssetError("model must contain at least the default material");
    }
    if (parts.empty() && !(skeleton.has_value() && !animations.empty())) {
        throw AssetError("model contains no renderable mesh parts: " + source_path.string());
    }
    for (const ModelPart& part : parts) {
        if (part.material_index >= materials.size()) {
            throw AssetError("model part references an out-of-range material");
        }
        part.mesh.validate();
        for (const Vertex& vertex : part.mesh.vertices) {
            for (std::size_t influence = 0; influence < vertex.weights.size(); ++influence) {
                if (vertex.weights[influence] > 0.0F &&
                    (!skeleton.has_value() ||
                     vertex.joints[influence] >= skeleton->joints.size())) {
                    throw AssetError("model vertex references an out-of-range joint");
                }
            }
        }
        const ModelMaterial& material = materials[part.material_index];
        const bool textured = material.diffuse_texture.has_value() ||
                              material.normal_texture.has_value() ||
                              material.roughness_texture.has_value() ||
                              material.metallic_texture.has_value() ||
                              material.emissive_texture.has_value() ||
                              material.ambient_occlusion_texture.has_value();
        if (textured) {
            const Vec2 first = part.mesh.vertices.front().uv;
            const bool has_area = std::any_of(
                part.mesh.vertices.begin(), part.mesh.vertices.end(),
                [&](const Vertex& vertex) {
                    return std::abs(vertex.uv.x - first.x) > 1.0e-6F ||
                           std::abs(vertex.uv.y - first.y) > 1.0e-6F;
                });
            if (!has_area) {
                throw AssetError("textured model part '" + part.name +
                                 "' has no usable authored UV coordinates");
            }
        }
    }
    for (const ModelMaterial& material : materials) {
        if (!std::isfinite(material.metallic) || material.metallic < 0.0F ||
            material.metallic > 1.0F || !std::isfinite(material.roughness) ||
            material.roughness < 0.04F || material.roughness > 1.0F ||
            !std::isfinite(material.emission) || material.emission < 0.0F ||
            material.emission > 100.0F || !std::isfinite(material.normal_strength) ||
            material.normal_strength < 0.0F || material.normal_strength > 8.0F) {
            throw AssetError("model material surface values are invalid");
        }
    }
    if (skeleton.has_value()) {
        skeleton->validate();
        for (const AnimationClip& animation : animations) {
            animation.validate(skeleton->joints.size());
        }
    } else if (!animations.empty()) {
        throw AssetError("model animations require a skeleton");
    }
}

std::size_t ModelData::triangle_count() const noexcept {
    std::size_t result = 0;
    for (const ModelPart& part : parts) {
        result += part.mesh.triangle_count();
    }
    return result;
}

std::shared_ptr<const ModelData> load_obj(const std::filesystem::path& path) {
    const std::filesystem::path canonical = checked_obj_path(path);
    tinyobj::ObjReaderConfig config;
    config.mtl_search_path = canonical.parent_path().string();
    config.triangulate = true;
    config.vertex_color = true;

    tinyobj::ObjReader reader;
    if (!reader.ParseFromFile(canonical.string(), config)) {
        std::string detail = reader.Error();
        if (detail.empty()) {
            detail = "unknown parser failure";
        }
        throw AssetError("failed to parse OBJ asset '" + canonical.string() + "': " + detail);
    }

    const std::string parser_warning = reader.Warning();
    if (parser_warning.find("Failed to load material file(s)") != std::string::npos ||
        parser_warning.find("Material file [") != std::string::npos) {
        throw MissingAssetError("OBJ references a missing material library in asset '" +
                                canonical.string() + "': " + parser_warning);
    }
    if (parser_warning.find("not found in .mtl") != std::string::npos) {
        throw AssetError("OBJ references an unknown material in asset '" +
                         canonical.string() + "': " + parser_warning);
    }

    auto model = std::make_shared<ModelData>();
    model->source_path = canonical;
    model->materials.push_back(ModelMaterial{});
    for (const tinyobj::material_t& material : reader.GetMaterials()) {
        model->materials.push_back(convert_material(material, canonical.parent_path()));
    }
    if (!parser_warning.empty()) {
        model->warnings.push_back(parser_warning);
    }

    const tinyobj::attrib_t& attributes = reader.GetAttrib();
    for (const tinyobj::shape_t& shape : reader.GetShapes()) {
        std::map<int, PartBuilder> builders;
        std::size_t index_offset = 0;
        for (std::size_t face = 0; face < shape.mesh.num_face_vertices.size(); ++face) {
            const std::size_t corners = shape.mesh.num_face_vertices[face];
            if (corners != 3 || index_offset + corners > shape.mesh.indices.size()) {
                throw AssetError("OBJ triangulation produced an invalid face in asset: " +
                                 canonical.string());
            }
            const int source_material =
                face < shape.mesh.material_ids.size() ? shape.mesh.material_ids[face] : -1;
            if (source_material < -1 ||
                source_material >= static_cast<int>(reader.GetMaterials().size())) {
                throw AssetError("OBJ face references an out-of-range material: " +
                                 canonical.string());
            }
            PartBuilder& part = builders[source_material];
            std::array<tinyobj::index_t, 3> triangle{
                shape.mesh.indices[index_offset],
                shape.mesh.indices[index_offset + 1U],
                shape.mesh.indices[index_offset + 2U],
            };
            index_offset += corners;
            const bool complete_normals = std::all_of(
                triangle.begin(), triangle.end(), [](const tinyobj::index_t index) {
                    return index.normal_index >= 0;
                });
            if (!complete_normals) {
                append_flat_triangle(part, attributes, triangle, canonical);
            } else {
                for (const tinyobj::index_t index : triangle) {
                    part.mesh.indices.push_back(
                        append_vertex(part, attributes, index, canonical));
                }
            }
        }
        for (auto& [source_material, builder] : builders) {
            if (builder.mesh.indices.empty()) {
                continue;
            }
            const std::size_t material_index =
                source_material < 0 ? 0U : static_cast<std::size_t>(source_material) + 1U;
            const std::string shape_name = shape.name.empty() ? "unnamed" : shape.name;
            model->parts.push_back({shape_name + ":" +
                                        model->materials[material_index].name,
                                    std::move(builder.mesh),
                                    material_index});
        }
    }
    for (ModelPart& part : model->parts) {
        generate_tangents(part.mesh);
    }
    model->validate();
    return model;
}

std::shared_ptr<const ModelData> ModelCache::load(const std::filesystem::path& path) {
    const std::filesystem::path canonical = checked_model_path(path);
    const std::string key = model_cache_key(canonical);
    std::scoped_lock lock(mutex_);
    const auto found = models_.find(key);
    if (found != models_.end()) {
        return found->second;
    }
    const std::string extension = lowercase(canonical.extension().string());
    std::shared_ptr<const ModelData> model;
    if (extension == ".obj") {
        model = load_obj(canonical);
    } else if (extension == ".fbx") {
        model = load_fbx(canonical);
    } else {
        model = load_gltf(canonical);
    }
    models_.emplace(key, model);
    return model;
}

std::size_t ModelCache::size() const noexcept {
    std::scoped_lock lock(mutex_);
    return models_.size();
}

void ModelCache::clear() noexcept {
    std::scoped_lock lock(mutex_);
    models_.clear();
}

} // namespace easy3d
