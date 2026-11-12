#include "easy3d/assets.hpp"

#include <ufbx.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <limits>
#include <memory>
#include <optional>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace easy3d {
namespace {

constexpr std::uintmax_t maximum_fbx_bytes = 512ULL * 1024ULL * 1024ULL;
constexpr std::size_t maximum_joints = 256;
constexpr std::size_t maximum_vertices = 10'000'000;
constexpr std::size_t maximum_animations = 128;

struct SceneDeleter final {
    void operator()(ufbx_scene* scene) const noexcept { ufbx_free_scene(scene); }
};
struct BakedAnimationDeleter final {
    void operator()(ufbx_baked_anim* animation) const noexcept {
        ufbx_free_baked_anim(animation);
    }
};
using FbxScene = std::unique_ptr<ufbx_scene, SceneDeleter>;
using BakedAnimation = std::unique_ptr<ufbx_baked_anim, BakedAnimationDeleter>;

[[nodiscard]] std::string text(const ufbx_string value) {
    return value.data == nullptr ? std::string{} : std::string(value.data, value.length);
}
[[nodiscard]] std::string name_or(const ufbx_string value, std::string fallback) {
    std::string result = text(value);
    return result.empty() ? std::move(fallback) : result;
}
[[nodiscard]] float checked_float(const double value, const char* label) {
    if (!std::isfinite(value) ||
        value < -static_cast<double>(std::numeric_limits<float>::max()) ||
        value > static_cast<double>(std::numeric_limits<float>::max())) {
        throw AssetError(std::string("FBX contains an invalid ") + label);
    }
    return static_cast<float>(value);
}
[[nodiscard]] Vec3 vec3(const ufbx_vec3 value, const char* label) {
    return {checked_float(value.x, label), checked_float(value.y, label),
            checked_float(value.z, label)};
}
[[nodiscard]] Quat quat(const ufbx_quat value) {
    return Quat{checked_float(value.w, "rotation"),
                checked_float(value.x, "rotation"),
                checked_float(value.y, "rotation"),
                checked_float(value.z, "rotation")}.normalized();
}
[[nodiscard]] Transform transform(const ufbx_transform value) {
    return {vec3(value.translation, "translation"), quat(value.rotation),
            vec3(value.scale, "scale")};
}
[[nodiscard]] Matrix4 matrix(const ufbx_matrix& value) {
    Matrix4 result;
    result.values = {
        checked_float(value.m00, "matrix"), checked_float(value.m10, "matrix"),
        checked_float(value.m20, "matrix"), 0.0F,
        checked_float(value.m01, "matrix"), checked_float(value.m11, "matrix"),
        checked_float(value.m21, "matrix"), 0.0F,
        checked_float(value.m02, "matrix"), checked_float(value.m12, "matrix"),
        checked_float(value.m22, "matrix"), 0.0F,
        checked_float(value.m03, "matrix"), checked_float(value.m13, "matrix"),
        checked_float(value.m23, "matrix"), 1.0F,
    };
    return result;
}
[[nodiscard]] std::filesystem::path checked_path(const std::filesystem::path& path) {
    if (path.empty()) throw MissingAssetError("FBX asset path is empty");
    std::error_code error;
    if (!std::filesystem::is_regular_file(path, error) || error) {
        throw MissingAssetError("FBX asset does not exist or is not a file: " + path.string());
    }
    std::string extension = path.extension().string();
    std::transform(extension.begin(), extension.end(), extension.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    if (extension != ".fbx") {
        throw AssetError("FBX importer requires a .fbx asset: " + path.string());
    }
    const std::uintmax_t size = std::filesystem::file_size(path, error);
    if (error || size == 0 || size > maximum_fbx_bytes) {
        throw AssetError("FBX container must be non-empty and no larger than 512 MiB: " + path.string());
    }
    const auto canonical = std::filesystem::weakly_canonical(path, error);
    if (error) throw AssetError("failed to resolve FBX asset path: " + error.message());
    return canonical;
}
[[nodiscard]] std::string formatted_error(const ufbx_error& error) {
    std::array<char, 2048> buffer{};
    const std::size_t length = ufbx_format_error(buffer.data(), buffer.size(), &error);
    return std::string(buffer.data(), std::min(length, buffer.size() - 1U));
}

[[nodiscard]] std::optional<std::filesystem::path> texture_path(
    const ufbx_material_map& map, const std::filesystem::path& directory,
    const std::string& material, const char* usage,
    std::vector<std::string>& warnings) {
    if (!map.texture_enabled || map.texture == nullptr) return std::nullopt;
    const ufbx_texture& texture = *map.texture;
    if (texture.type != UFBX_TEXTURE_FILE) {
        warnings.push_back("material '" + material + "' uses an unsupported " + usage + " layered/procedural texture");
        return std::nullopt;
    }
    if (texture.content.size != 0) {
        warnings.push_back("material '" + material + "' has an embedded " + usage + " texture; embedded texture decoding is not yet supported");
        return std::nullopt;
    }
    std::filesystem::path result = text(texture.filename);
    if (result.empty()) result = text(texture.relative_filename);
    if (result.empty()) {
        warnings.push_back("material '" + material + "' has an unnamed " + usage + " texture");
        return std::nullopt;
    }
    if (result.is_relative()) result = directory / result;
    std::error_code error;
    if (!std::filesystem::is_regular_file(result, error) || error) {
        warnings.push_back("material '" + material + "' references a missing " + usage + " texture: " + result.string());
        return std::nullopt;
    }
    const auto canonical = std::filesystem::weakly_canonical(result, error);
    return error ? std::optional<std::filesystem::path>{result}
                 : std::optional<std::filesystem::path>{canonical};
}

void import_materials(const ufbx_scene& scene, const std::filesystem::path& directory,
                      ModelData& model) {
    model.materials.push_back(ModelMaterial{});
    for (std::size_t index = 0; index < scene.materials.count; ++index) {
        const ufbx_material& source = *scene.materials.data[index];
        ModelMaterial material;
        material.name = name_or(source.name, "material_" + std::to_string(index));
        const ufbx_material_map& base = source.pbr.base_color.has_value
            ? source.pbr.base_color : source.fbx.diffuse_color;
        if (base.has_value) {
            material.diffuse_color = {
                std::clamp(checked_float(base.value_vec4.x, "material color"), 0.0F, 1.0F),
                std::clamp(checked_float(base.value_vec4.y, "material color"), 0.0F, 1.0F),
                std::clamp(checked_float(base.value_vec4.z, "material color"), 0.0F, 1.0F),
                base.value_components >= 4 ? std::clamp(checked_float(base.value_vec4.w, "material alpha"), 0.0F, 1.0F) : 1.0F};
        }
        if (source.pbr.roughness.has_value) material.roughness = std::clamp(checked_float(source.pbr.roughness.value_real, "roughness"), 0.04F, 1.0F);
        if (source.pbr.metalness.has_value) material.metallic = std::clamp(checked_float(source.pbr.metalness.value_real, "metalness"), 0.0F, 1.0F);
        if (source.pbr.emission_factor.has_value) material.emission = std::clamp(checked_float(source.pbr.emission_factor.value_real, "emission"), 0.0F, 100.0F);
        material.double_sided = source.features.double_sided.enabled;
        material.authored_surface = true;
        material.diffuse_texture = texture_path(base, directory, material.name, "base-color", model.warnings);
        const ufbx_material_map& normal = source.pbr.normal_map.texture != nullptr ? source.pbr.normal_map : source.fbx.normal_map;
        material.normal_texture = texture_path(normal, directory, material.name, "normal", model.warnings);
        material.roughness_texture = texture_path(source.pbr.roughness, directory, material.name, "roughness", model.warnings);
        material.metallic_texture = texture_path(source.pbr.metalness, directory, material.name, "metallic", model.warnings);
        material.emissive_texture = texture_path(source.pbr.emission_color, directory, material.name, "emissive", model.warnings);
        material.ambient_occlusion_texture = texture_path(source.pbr.ambient_occlusion, directory, material.name, "ambient-occlusion", model.warnings);
        if (source.pbr.opacity.has_value && source.pbr.opacity.value_real < 0.999) model.warnings.push_back("material '" + material.name + "' transparency is rendered as opaque geometry");
        model.materials.push_back(std::move(material));
    }
}

void add_joint_with_parents(const ufbx_node* node, const ufbx_node* scene_root,
                            std::vector<const ufbx_node*>& nodes,
                            std::unordered_set<const ufbx_node*>& seen) {
    if (node == nullptr || node == scene_root || seen.contains(node)) return;
    add_joint_with_parents(node->parent, scene_root, nodes, seen);
    if (seen.emplace(node).second) nodes.push_back(node);
}
[[nodiscard]] std::unordered_map<const ufbx_node*, std::size_t> import_skeleton(
    const ufbx_scene& scene, ModelData& model) {
    std::vector<const ufbx_node*> nodes;
    std::unordered_set<const ufbx_node*> seen;
    for (std::size_t si = 0; si < scene.skin_deformers.count; ++si) {
        const ufbx_skin_deformer& skin = *scene.skin_deformers.data[si];
        if (skin.skinning_method != UFBX_SKINNING_METHOD_LINEAR && skin.skinning_method != UFBX_SKINNING_METHOD_RIGID) {
            model.warnings.push_back("skin '" + name_or(skin.name, "unnamed") + "' uses dual-quaternion data; RIX imports normalized linear weights");
        }
        for (std::size_t ci = 0; ci < skin.clusters.count; ++ci) add_joint_with_parents(skin.clusters.data[ci]->bone_node, scene.root_node, nodes, seen);
    }
    // Animation-only Mixamo FBX files contain a bone hierarchy but no skin
    // deformer. Preserve that hierarchy so their clips can be attached to a
    // separately loaded character mesh.
    if (nodes.empty()) {
        for (std::size_t ni = 0; ni < scene.nodes.count; ++ni) {
            const ufbx_node* node = scene.nodes.data[ni];
            if (node != nullptr && node->bone != nullptr) {
                add_joint_with_parents(node, scene.root_node, nodes, seen);
            }
        }
    }
    std::unordered_map<const ufbx_node*, std::size_t> indices;
    if (nodes.empty()) return indices;
    if (nodes.size() > maximum_joints) throw AssetError("FBX skeleton exceeds RIX's 256-joint limit");
    Skeleton skeleton;
    skeleton.name = "fbx_skeleton";
    indices.reserve(nodes.size());
    for (const ufbx_node* node : nodes) indices.emplace(node, indices.size());
    std::vector<ufbx_matrix> global_bind;
    global_bind.reserve(nodes.size());
    for (std::size_t index = 0; index < nodes.size(); ++index) {
        const ufbx_node& node = *nodes[index];
        SkeletonJoint joint;
        joint.name = name_or(node.name, "joint_" + std::to_string(index));
        joint.local_bind = transform(node.local_transform);
        global_bind.push_back(node.node_to_world);
        if (node.parent != nullptr) {
            const auto parent = indices.find(node.parent);
            if (parent != indices.end()) joint.parent = static_cast<std::int32_t>(parent->second);
            else joint.local_bind = transform(ufbx_matrix_to_transform(&node.node_to_world));
        }
        const ufbx_matrix inverse = ufbx_matrix_invert(&node.node_to_world);
        joint.inverse_bind = matrix(inverse);
        skeleton.joints.push_back(std::move(joint));
    }
    // Cluster bind_to_world is the authoritative rest transform. The node's
    // current transform is not necessarily the authored bind pose (Mixamo
    // files commonly differ), so derive both local rest transforms and
    // inverse binds from cluster bind data when it exists.
    std::vector<bool> has_cluster_bind(skeleton.joints.size(), false);
    for (std::size_t skin_index = 0;
         skin_index < scene.skin_deformers.count; ++skin_index) {
        const ufbx_skin_deformer& skin = *scene.skin_deformers.data[skin_index];
        for (std::size_t cluster_index = 0;
             cluster_index < skin.clusters.count; ++cluster_index) {
            const ufbx_skin_cluster& cluster = *skin.clusters.data[cluster_index];
            const auto found = indices.find(cluster.bone_node);
            if (found == indices.end()) {
                throw AssetError("FBX skin cluster bone is absent from the skeleton");
            }
            const Matrix4 bind = matrix(
                ufbx_matrix_invert(&cluster.bind_to_world));
            SkeletonJoint& joint = skeleton.joints[found->second];
            if (has_cluster_bind[found->second]) {
                for (std::size_t component = 0;
                     component < bind.values.size(); ++component) {
                    if (std::abs(bind.values[component] -
                                 joint.inverse_bind.values[component]) > 1.0e-4F) {
                        throw AssetError(
                            "FBX meshes use incompatible bind matrices for joint '" +
                            joint.name + "'");
                    }
                }
            } else {
                joint.inverse_bind = bind;
                global_bind[found->second] = cluster.bind_to_world;
                has_cluster_bind[found->second] = true;
            }
        }
    }
    for (std::size_t index = 0; index < skeleton.joints.size(); ++index) {
        const std::int32_t parent = skeleton.joints[index].parent;
        if (parent >= 0) {
            const ufbx_matrix parent_to_local = ufbx_matrix_invert(
                &global_bind[static_cast<std::size_t>(parent)]);
            const ufbx_matrix local_bind = ufbx_matrix_mul(
                &parent_to_local, &global_bind[index]);
            skeleton.joints[index].local_bind = transform(
                ufbx_matrix_to_transform(&local_bind));
        } else {
            skeleton.joints[index].local_bind = transform(
                ufbx_matrix_to_transform(&global_bind[index]));
        }
    }
    skeleton.validate();
    model.skeleton = std::move(skeleton);
    return indices;
}

[[nodiscard]] std::size_t material_index(const ufbx_scene& scene, const ufbx_node& node,
                                         const ufbx_mesh& mesh, std::size_t face_index) {
    if (face_index >= mesh.face_material.count) return 0;
    const std::uint32_t slot = mesh.face_material.data[face_index];
    if (slot == UFBX_NO_INDEX || slot >= node.materials.count || node.materials.data[slot] == nullptr) return 0;
    const ufbx_material* material = node.materials.data[slot];
    if (material->typed_id >= scene.materials.count) throw AssetError("FBX face references an invalid material");
    return static_cast<std::size_t>(material->typed_id) + 1U;
}
void apply_weights(Vertex& vertex, const ufbx_mesh& mesh, std::size_t corner,
                   const std::unordered_map<const ufbx_node*, std::size_t>& joints,
                   ModelData& model, bool& warned_excess) {
    if (mesh.skin_deformers.count == 0) return;
    const ufbx_skin_deformer& skin = *mesh.skin_deformers.data[0];
    if (corner >= mesh.vertex_indices.count) throw AssetError("FBX mesh corner has no logical vertex");
    const std::uint32_t logical = mesh.vertex_indices.data[corner];
    if (logical >= skin.vertices.count) throw AssetError("FBX skin has no weights for a mesh vertex");
    const ufbx_skin_vertex& source = skin.vertices.data[logical];
    const std::size_t count = std::min<std::size_t>(source.num_weights, 4U);
    float total = 0.0F;
    for (std::size_t influence = 0; influence < count; ++influence) {
        const std::size_t wi = source.weight_begin + influence;
        if (wi >= skin.weights.count) throw AssetError("FBX skin weight range is invalid");
        const ufbx_skin_weight& weight = skin.weights.data[wi];
        if (weight.cluster_index >= skin.clusters.count) throw AssetError("FBX skin weight references an invalid cluster");
        const auto joint = joints.find(skin.clusters.data[weight.cluster_index]->bone_node);
        if (joint == joints.end()) throw AssetError("FBX skin cluster bone is absent from the skeleton");
        const float amount = checked_float(weight.weight, "skin weight");
        if (amount < 0.0F) throw AssetError("FBX skin weight is negative");
        vertex.joints[influence] = static_cast<std::uint8_t>(joint->second);
        vertex.weights[influence] = amount;
        total += amount;
    }
    if (source.num_weights > 4 && !warned_excess) {
        model.warnings.push_back("skin vertices exceeding four influences were truncated and renormalized");
        warned_excess = true;
    }
    if (total <= 1.0e-8F) throw AssetError("FBX skinned vertex has zero total weight");
    for (float& weight : vertex.weights) weight /= total;
}
[[nodiscard]] Vertex import_vertex(const ufbx_matrix& geometry_to_world,
                                   const ufbx_mesh& mesh,
                                   std::size_t corner,
                                   const std::unordered_map<const ufbx_node*, std::size_t>& joints,
                                   ModelData& model, bool& warned_excess) {
    Vertex vertex;
    const ufbx_vec3 source_position = ufbx_get_vertex_vec3(&mesh.vertex_position, corner);
    vertex.position = vec3(
        ufbx_transform_position(&geometry_to_world, source_position),
        "vertex position");
    const ufbx_matrix normal_matrix = ufbx_matrix_for_normals(&geometry_to_world);
    vertex.normal = vec3(
        ufbx_transform_direction(
            &normal_matrix, ufbx_get_vertex_vec3(&mesh.vertex_normal, corner)),
        "vertex normal").normalized();
    if (mesh.vertex_uv.exists) {
        const ufbx_vec2 uv = ufbx_get_vertex_vec2(&mesh.vertex_uv, corner);
        vertex.uv = {checked_float(uv.x, "texture coordinate"), 1.0F - checked_float(uv.y, "texture coordinate")};
    }
    if (mesh.vertex_color.exists) {
        const ufbx_vec4 color = ufbx_get_vertex_vec4(&mesh.vertex_color, corner);
        vertex.color = {std::clamp(checked_float(color.x, "vertex color"), 0.0F, 1.0F), std::clamp(checked_float(color.y, "vertex color"), 0.0F, 1.0F), std::clamp(checked_float(color.z, "vertex color"), 0.0F, 1.0F), std::clamp(checked_float(color.w, "vertex color"), 0.0F, 1.0F)};
    }
    apply_weights(vertex, mesh, corner, joints, model, warned_excess);
    return vertex;
}
void import_meshes(const ufbx_scene& scene,
                   const std::unordered_map<const ufbx_node*, std::size_t>& joints,
                   ModelData& model) {
    bool warned_excess = false, warned_multiple = false;
    for (std::size_t ni = 0; ni < scene.nodes.count; ++ni) {
        const ufbx_node& node = *scene.nodes.data[ni];
        if (node.mesh == nullptr || node.mesh->num_triangles == 0) continue;
        const ufbx_mesh& mesh = *node.mesh;
        if (!mesh.vertex_position.exists || !mesh.vertex_normal.exists) throw AssetError("FBX mesh has no usable positions or normals");
        if (mesh.skin_deformers.count > 1 && !warned_multiple) { model.warnings.push_back("meshes with multiple skin deformers use the first deformer"); warned_multiple = true; }
        ufbx_matrix geometry_to_world = node.geometry_to_world;
        if (mesh.skin_deformers.count != 0) {
            const ufbx_skin_deformer& skin = *mesh.skin_deformers.data[0];
            if (skin.clusters.count == 0) {
                throw AssetError("FBX skin deformer contains no bone clusters");
            }
            const ufbx_skin_cluster& first = *skin.clusters.data[0];
            geometry_to_world = ufbx_matrix_mul(
                &first.bind_to_world, &first.geometry_to_bone);
            const Matrix4 expected = matrix(geometry_to_world);
            for (std::size_t cluster_index = 1;
                 cluster_index < skin.clusters.count; ++cluster_index) {
                const ufbx_skin_cluster& cluster =
                    *skin.clusters.data[cluster_index];
                const ufbx_matrix candidate_matrix = ufbx_matrix_mul(
                    &cluster.bind_to_world, &cluster.geometry_to_bone);
                const Matrix4 candidate = matrix(candidate_matrix);
                for (std::size_t component = 0;
                     component < expected.values.size(); ++component) {
                    if (std::abs(expected.values[component] -
                                 candidate.values[component]) > 1.0e-4F) {
                        throw AssetError(
                            "FBX skin clusters disagree on the mesh bind transform");
                    }
                }
            }
        }
        std::unordered_map<std::size_t, MeshData> parts;
        std::vector<std::uint32_t> triangles(mesh.max_face_triangles * 3U);
        for (std::size_t fi = 0; fi < mesh.faces.count; ++fi) {
            const ufbx_face face = mesh.faces.data[fi];
            if (face.num_indices < 3) continue;
            const std::uint32_t triangle_count = ufbx_triangulate_face(
                triangles.data(), triangles.size(), &mesh, face);
            if (triangle_count == 0) throw AssetError("ufbx failed to triangulate an FBX polygon");
            const std::size_t count = static_cast<std::size_t>(triangle_count) * 3U;
            MeshData& part = parts[material_index(scene, node, mesh, fi)];
            if (part.vertices.size() + count > maximum_vertices) throw AssetError("FBX mesh exceeds RIX's ten-million-vertex limit");
            for (std::size_t item = 0; item < count; ++item) {
                part.indices.push_back(static_cast<std::uint32_t>(part.vertices.size()));
                part.vertices.push_back(import_vertex(
                    geometry_to_world, mesh, triangles[item], joints,
                    model, warned_excess));
            }
        }
        for (auto& [material, mesh_data] : parts) {
            if (mesh_data.indices.empty()) continue;
            generate_tangents(mesh_data);
            model.parts.push_back({name_or(node.name, "node_" + std::to_string(ni)) + ":" + name_or(mesh.name, "mesh") + ":" + std::to_string(material), std::move(mesh_data), material});
        }
    }
}

void append_vec3_channel(std::size_t joint, const ufbx_baked_vec3_list& keys,
                         AnimationTarget target, double begin, AnimationClip& clip) {
    if (keys.count == 0) return;
    AnimationChannel channel;
    channel.joint_index = joint;
    channel.target = target;
    for (std::size_t i = 0; i < keys.count; ++i) {
        const ufbx_baked_vec3& key = keys.data[i];
        const float time = std::max(0.0F, checked_float(key.time - begin, "animation time"));
        if (!channel.times.empty() && time <= channel.times.back()) continue;
        channel.times.push_back(time);
        channel.values.push_back({checked_float(key.value.x, "animation value"), checked_float(key.value.y, "animation value"), checked_float(key.value.z, "animation value"), 0.0F});
    }
    if (!channel.times.empty()) { clip.duration = std::max(clip.duration, channel.times.back()); clip.channels.push_back(std::move(channel)); }
}
void import_animations(const ufbx_scene& scene,
                       const std::unordered_map<const ufbx_node*, std::size_t>& joints,
                       ModelData& model) {
    if (!model.skeleton.has_value() || scene.anim_stacks.count == 0) return;
    if (scene.anim_stacks.count > maximum_animations) throw AssetError("FBX exceeds RIX's 128-animation limit");
    for (std::size_t si = 0; si < scene.anim_stacks.count; ++si) {
        const ufbx_anim_stack& stack = *scene.anim_stacks.data[si];
        ufbx_bake_opts options{};
        options.resample_rate = scene.settings.frames_per_second > 0.0 ? scene.settings.frames_per_second : 30.0;
        options.maximum_sample_rate = 120.0;
        ufbx_error error{};
        BakedAnimation baked(ufbx_bake_anim(&scene, stack.anim, &options, &error));
        if (!baked) throw AssetError("failed to bake FBX animation '" + text(stack.name) + "': " + formatted_error(error));
        AnimationClip clip;
        clip.name = name_or(stack.name, "animation_" + std::to_string(si));
        clip.duration = std::max(0.0F, checked_float(baked->playback_duration, "animation duration"));
        for (std::size_t bi = 0; bi < baked->nodes.count; ++bi) {
            const ufbx_baked_node& bn = baked->nodes.data[bi];
            if (bn.typed_id >= scene.nodes.count) throw AssetError("baked FBX animation references an invalid node");
            const auto found = joints.find(scene.nodes.data[bn.typed_id]);
            if (found == joints.end()) continue;
            append_vec3_channel(found->second, bn.translation_keys, AnimationTarget::Translation, baked->playback_time_begin, clip);
            if (bn.rotation_keys.count != 0) {
                AnimationChannel channel;
                channel.joint_index = found->second;
                channel.target = AnimationTarget::Rotation;
                std::optional<Quat> previous_rotation;
                for (std::size_t ki = 0; ki < bn.rotation_keys.count; ++ki) {
                    const ufbx_baked_quat& key = bn.rotation_keys.data[ki];
                    const float time = std::max(0.0F, checked_float(key.time - baked->playback_time_begin, "animation time"));
                    if (!channel.times.empty() && time <= channel.times.back()) continue;
                    Quat rotation = quat(key.value);
                    if (previous_rotation.has_value()) {
                        const float dot = previous_rotation->w * rotation.w +
                                          previous_rotation->x * rotation.x +
                                          previous_rotation->y * rotation.y +
                                          previous_rotation->z * rotation.z;
                        if (dot < 0.0F) {
                            rotation = {-rotation.w, -rotation.x,
                                        -rotation.y, -rotation.z};
                        }
                    }
                    previous_rotation = rotation;
                    channel.times.push_back(time);
                    channel.values.push_back({rotation.w, rotation.x, rotation.y, rotation.z});
                }
                if (!channel.times.empty()) { clip.duration = std::max(clip.duration, channel.times.back()); clip.channels.push_back(std::move(channel)); }
            }
            append_vec3_channel(found->second, bn.scale_keys, AnimationTarget::Scale, baked->playback_time_begin, clip);
        }
        if (clip.channels.empty()) { model.warnings.push_back("animation '" + clip.name + "' contains no skeletal channels"); continue; }
        clip.validate(model.skeleton->joints.size());
        model.animations.push_back(std::move(clip));
    }
}

} // namespace

std::shared_ptr<const ModelData> load_fbx(const std::filesystem::path& path) {
    const std::filesystem::path canonical = checked_path(path);
    ufbx_load_opts options{};
    options.target_axes = {UFBX_COORDINATE_AXIS_POSITIVE_X, UFBX_COORDINATE_AXIS_POSITIVE_Y, UFBX_COORDINATE_AXIS_POSITIVE_Z};
    options.target_unit_meters = 1.0;
    options.space_conversion = UFBX_SPACE_CONVERSION_ADJUST_TRANSFORMS;
    options.geometry_transform_handling = UFBX_GEOMETRY_TRANSFORM_HANDLING_PRESERVE;
    options.generate_missing_normals = true;
    options.normalize_normals = true;
    options.normalize_tangents = true;
    options.clean_skin_weights = true;
    options.node_depth_limit = 256;
    options.ignore_missing_external_files = true;
    ufbx_error error{};
    FbxScene scene(ufbx_load_file(canonical.string().c_str(), &options, &error));
    if (!scene) throw AssetError("failed to parse FBX asset '" + canonical.string() + "': " + formatted_error(error));
    auto model = std::make_shared<ModelData>();
    model->source_path = canonical;
    import_materials(*scene, canonical.parent_path(), *model);
    for (std::size_t i = 0; i < scene->metadata.warnings.count; ++i) model->warnings.push_back("ufbx: " + text(scene->metadata.warnings.data[i].description));
    const auto joints = import_skeleton(*scene, *model);
    import_meshes(*scene, joints, *model);
    import_animations(*scene, joints, *model);
    model->validate();
    return model;
}

} // namespace easy3d
