#include "easy3d/scene.hpp"

#define GLM_ENABLE_EXPERIMENTAL
#include <glm/gtc/matrix_transform.hpp>
#include <glm/gtc/quaternion.hpp>
#include <glm/gtc/type_ptr.hpp>
#include <glm/gtx/matrix_decompose.hpp>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace easy3d {
namespace {

std::atomic_uint64_t next_world_id{1};
constexpr float minimum_scale = 1.0e-6F;
constexpr float degrees_to_radians = 0.01745329251994329577F;
constexpr float radians_to_degrees = 57.295779513082320876F;

[[nodiscard]] const std::shared_ptr<const MeshData>& primitive_mesh(const RenderKind kind) {
    static const auto cube = std::make_shared<const MeshData>(make_cube_mesh());
    static const auto plane = std::make_shared<const MeshData>(make_plane_mesh());
    static const auto sphere = std::make_shared<const MeshData>(make_uv_sphere_mesh());
    switch (kind) {
    case RenderKind::Cube:
        return cube;
    case RenderKind::Plane:
        return plane;
    case RenderKind::Sphere:
        return sphere;
    case RenderKind::Model:
        throw std::invalid_argument("Model renderers require an OBJ asset path");
    }
    throw std::invalid_argument("unknown primitive render kind");
}

[[nodiscard]] glm::vec3 to_glm(const Vec3 value) noexcept {
    return {value.x, value.y, value.z};
}

[[nodiscard]] glm::quat to_glm(const Quat value) noexcept {
    return {value.w, value.x, value.y, value.z};
}

[[nodiscard]] Vec3 from_glm(const glm::vec3 value) noexcept {
    return {value.x, value.y, value.z};
}

[[nodiscard]] Quat from_glm(const glm::quat value) noexcept {
    return {value.w, value.x, value.y, value.z};
}

[[nodiscard]] glm::mat4 to_glm(const std::array<float, 16>& matrix) noexcept {
    return glm::make_mat4(matrix.data());
}

[[nodiscard]] std::array<float, 16> from_glm(const glm::mat4& matrix) noexcept {
    std::array<float, 16> result{};
    const float* values = glm::value_ptr(matrix);
    std::copy_n(values, result.size(), result.begin());
    return result;
}

[[nodiscard]] glm::mat4 compose_matrix(const Transform& transform) noexcept {
    return glm::translate(glm::mat4(1.0F), to_glm(transform.position)) *
           glm::mat4_cast(to_glm(transform.rotation)) *
           glm::scale(glm::mat4(1.0F), to_glm(transform.scale));
}

[[nodiscard]] Transform decompose_matrix(const glm::mat4& matrix) {
    glm::vec3 scale{};
    glm::quat rotation{};
    glm::vec3 translation{};
    glm::vec3 skew{};
    glm::vec4 perspective{};
    if (!glm::decompose(matrix, scale, rotation, translation, skew, perspective)) {
        throw EngineError("transform matrix could not be decomposed");
    }
    return Transform{from_glm(translation), from_glm(rotation).normalized(), from_glm(scale)};
}

[[nodiscard]] bool finite(const Vec3 value) noexcept {
    return std::isfinite(value.x) && std::isfinite(value.y) && std::isfinite(value.z);
}

[[nodiscard]] bool finite(const Quat value) noexcept {
    return std::isfinite(value.w) && std::isfinite(value.x) && std::isfinite(value.y) &&
           std::isfinite(value.z);
}

[[nodiscard]] bool nonzero(const Vec3 value) noexcept {
    return value.length_squared() > 1.0e-12F;
}

[[nodiscard]] Quat apply_world_angular_step(const Quat rotation,
                                            const Vec3 degrees_per_second,
                                            const float delta_seconds) {
    const float speed = degrees_per_second.length();
    if (speed <= 1.0e-6F) return rotation;
    const glm::vec3 axis = to_glm(degrees_per_second / speed);
    const glm::quat delta = glm::angleAxis(
        speed * delta_seconds * degrees_to_radians, axis);
    return from_glm(delta * to_glm(rotation)).normalized();
}

[[nodiscard]] std::string invalid_handle_message(const EntityHandle handle,
                                                 const std::uint64_t expected_world) {
    std::ostringstream message;
    message << "invalid entity handle (world=" << handle.world_id << ", index=" << handle.index
            << ", generation=" << handle.generation << "); expected live entity in world "
            << expected_world;
    return message.str();
}

} // namespace

bool EntityHandle::valid() const noexcept {
    return world_id != 0 && index != invalid_index && generation != 0;
}

void TextureMaterialSettings::validate() const {
    if (!std::isfinite(pixels_per_unit) || pixels_per_unit <= 0.0F ||
        pixels_per_unit > 4096.0F) {
        throw std::invalid_argument("pixels per unit must be finite and in (0, 4096]");
    }
    if (!std::isfinite(normal_strength) || normal_strength < 0.0F ||
        normal_strength > 8.0F) {
        throw std::invalid_argument("normal strength must be finite and in [0, 8]");
    }
    if (!finite(atlas_dimensions) || atlas_dimensions.x <= 0.0F ||
        atlas_dimensions.y <= 0.0F || atlas_dimensions.z <= 0.0F) {
        throw std::invalid_argument(
            "atlas dimensions must be finite and strictly positive");
    }
}

std::uint64_t EntityHandle::id() const noexcept {
    return (static_cast<std::uint64_t>(generation) << 32U) | index;
}

void LightComponent::validate() const {
    (void)color.rgba8();
    if (!std::isfinite(intensity) || intensity < 0.0F) {
        throw std::invalid_argument("light intensity must be finite and non-negative");
    }
    if (!std::isfinite(range) || range <= 0.0F) {
        throw std::invalid_argument("light range must be finite and positive");
    }
    if (!std::isfinite(inner_angle_degrees) || !std::isfinite(outer_angle_degrees) ||
        inner_angle_degrees < 0.0F || outer_angle_degrees <= 0.0F ||
        inner_angle_degrees > outer_angle_degrees || outer_angle_degrees >= 180.0F) {
        throw std::invalid_argument(
            "spot light angles must satisfy 0 <= inner <= outer < 180 degrees");
    }
    if (shadow_resolution != 0U &&
        (shadow_resolution < 128U || shadow_resolution > 8192U ||
         (shadow_resolution & (shadow_resolution - 1U)) != 0U)) {
        throw std::invalid_argument(
            "shadow resolution must be zero or a power of two in [128, 8192]");
    }
    if (!std::isfinite(shadow_bias) || shadow_bias < 0.0F || shadow_bias > 0.1F) {
        throw std::invalid_argument("shadow bias must be finite and in [0, 0.1]");
    }
}

void SkyboxConfig::validate() const {
    (void)top.rgba8();
    (void)horizon.rgba8();
    (void)bottom.rgba8();
    if (!std::isfinite(brightness) || brightness < 0.0F || brightness > 32.0F) {
        throw std::invalid_argument("skybox brightness must be finite and in [0, 32]");
    }
    if (!std::isfinite(rotation_degrees)) {
        throw std::invalid_argument("skybox rotation must be finite");
    }
    if (kind == SkyboxKind::Panorama) {
        if (!panorama) throw std::invalid_argument("panorama skybox requires an image");
        panorama->validate();
        if (panorama->width != panorama->height * 2U) {
            throw std::invalid_argument("panorama skybox image must have a 2:1 aspect ratio");
        }
    }
    if (kind == SkyboxKind::Cubemap) {
        std::uint32_t size = 0;
        for (const auto& face : cubemap) {
            if (!face) throw std::invalid_argument("cubemap skybox requires all six faces");
            face->validate();
            if (face->width != face->height) {
                throw std::invalid_argument("cubemap skybox faces must be square");
            }
            if (size == 0U) size = face->width;
            if (face->width != size) {
                throw std::invalid_argument("cubemap skybox faces must use one size");
            }
        }
    }
}

void UiElement::validate() const {
    (void)color.rgba8();
    (void)text_color.rgba8();
    if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(width) ||
        !std::isfinite(height) || width < 0.0F || height < 0.0F) {
        throw std::invalid_argument("UI position and size must be finite and non-negative");
    }
    if ((kind == UiElementKind::Panel || kind == UiElementKind::Sprite ||
         kind == UiElementKind::Button) &&
        (width <= 0.0F || height <= 0.0F)) {
        throw std::invalid_argument("panel, sprite, and button sizes must be positive");
    }
    if (!std::isfinite(font_size) || font_size < 4.0F || font_size > 256.0F) {
        throw std::invalid_argument("UI font size must be finite and in [4, 256]");
    }
    if (text.size() > 4096U) {
        throw std::invalid_argument("UI text must not exceed 4096 UTF-8 bytes");
    }
    if ((kind == UiElementKind::Text || kind == UiElementKind::Button) && text.empty()) {
        throw std::invalid_argument("text and button elements require non-empty text");
    }
    if (kind == UiElementKind::Sprite && !texture) {
        throw std::invalid_argument("sprite elements require a texture");
    }
}

void ColliderComponent::validate() const {
    material.validate();
    if (shape == PhysicsShape::Box &&
        (!finite(half_extents) || half_extents.x <= 0.0F || half_extents.y <= 0.0F ||
         half_extents.z <= 0.0F)) {
        throw std::invalid_argument("collider half extents must be finite and positive");
    }
    if (shape == PhysicsShape::Sphere &&
        (!std::isfinite(radius) || radius <= 0.0F)) {
        throw std::invalid_argument("collider radius must be finite and positive");
    }
    if (shape == PhysicsShape::Capsule &&
        (!std::isfinite(radius) || radius <= 0.0F || !std::isfinite(height) ||
         height <= 2.0F * radius)) {
        throw std::invalid_argument(
            "capsule radius must be positive and height greater than its diameter");
    }
    if (shape == PhysicsShape::ConvexHull &&
        (vertices.size() < 4U || vertices.size() > 256U ||
         !std::all_of(vertices.begin(), vertices.end(),
                      [](const Vec3 point) { return finite(point); }))) {
        throw std::invalid_argument("convex collider requires 4 to 256 finite points");
    }
    if (shape == PhysicsShape::TriangleMesh &&
        (vertices.size() < 3U || indices.size() < 3U || indices.size() % 3U != 0U ||
         !std::all_of(vertices.begin(), vertices.end(),
                      [](const Vec3 point) { return finite(point); }) ||
         std::any_of(indices.begin(), indices.end(), [&](const auto index) {
             return index >= vertices.size();
         }))) {
        throw std::invalid_argument(
            "mesh collider requires finite vertices and valid triangle indices");
    }
    if (static_cast<std::uint8_t>(layer) >
        static_cast<std::uint8_t>(CollisionLayer::Character)) {
        throw std::invalid_argument("unknown collider collision layer");
    }
}

void RigidBodyComponent::validate() const {
    if (motion_type == PhysicsMotionType::Static) {
        throw std::invalid_argument(
            "static colliders do not need a rigid body; use dynamic or kinematic");
    }
    if (!std::isfinite(mass) || mass <= 0.0F) {
        throw std::invalid_argument("rigid body mass must be finite and positive");
    }
}

void CharacterControllerComponent::validate() const {
    if (!std::isfinite(radius) || radius <= 0.0F || !std::isfinite(height) ||
        height <= radius * 2.0F) {
        throw std::invalid_argument(
            "character requires a positive radius and height greater than its diameter");
    }
    if (!std::isfinite(speed) || speed < 0.0F || !std::isfinite(acceleration) ||
        acceleration < 0.0F || !std::isfinite(air_acceleration) ||
        air_acceleration < 0.0F || !std::isfinite(ground_friction) ||
        ground_friction < 0.0F || !std::isfinite(stop_speed) || stop_speed < 0.0F ||
        !std::isfinite(air_speed_cap) || air_speed_cap < 0.0F ||
        !std::isfinite(horizontal_speed_limit) || horizontal_speed_limit < 0.0F ||
        !std::isfinite(jump_speed) || jump_speed < 0.0F) {
        throw std::invalid_argument(
            "character movement, friction, caps, and jump values must be finite and "
            "non-negative");
    }
    if (!std::isfinite(max_slope_degrees) || max_slope_degrees < 0.0F ||
        max_slope_degrees >= 90.0F || !std::isfinite(step_height) || step_height < 0.0F) {
        throw std::invalid_argument(
            "character slope must be in [0, 90) degrees and step height non-negative");
    }
    if (!std::isfinite(sprint_multiplier) || sprint_multiplier < 1.0F ||
        !std::isfinite(crouch_height) || crouch_height <= radius * 2.0F ||
        crouch_height > height || !std::isfinite(crouch_speed_multiplier) ||
        crouch_speed_multiplier < 0.0F || crouch_speed_multiplier > 1.0F) {
        throw std::invalid_argument(
            "character sprint multiplier must be at least 1, crouch height must be in "
            "(diameter, height], and crouch speed multiplier must be in [0, 1]");
    }
}

World::World() : id_(next_world_id.fetch_add(1, std::memory_order_relaxed)) {
    if (id_ == 0) {
        throw EngineError("RIX exhausted native world identifiers");
    }
}

EntityHandle World::create_entity(std::string name) {
    validate_name(name);

    std::uint32_t index = 0;
    if (free_indices_.empty()) {
        if (slots_.size() >= EntityHandle::invalid_index) {
            throw EngineError("RIX exhausted entity slots in this world");
        }
        index = static_cast<std::uint32_t>(slots_.size());
        slots_.emplace_back();
    } else {
        index = free_indices_.back();
        free_indices_.pop_back();
    }

    Slot& slot = slots_[index];
    slot.alive = true;
    slot.enabled = true;
    slot.visible = true;
    slot.name = std::move(name);
    slot.local_transform = {};
    slot.parent_index.reset();
    slot.child_indices.clear();
    slot.transform_dirty = true;
    slot.motion = {};
    slot.render_component.reset();
    slot.light_component.reset();
    ++entity_count_;
    return handle_for(index);
}

void World::destroy_entity(const EntityHandle handle) {
    Slot& slot = require_slot(handle);

    const std::vector<std::uint32_t> child_indices = slot.child_indices;
    for (const std::uint32_t child_index : child_indices) {
        const std::array<float, 16> child_world = world_matrix(child_index);
        slots_[child_index].parent_index.reset();
        set_local_from_matrix(child_index, child_world);
    }
    slot.child_indices.clear();
    detach_from_parent(handle.index);

    slot.alive = false;
    slot.enabled = false;
    slot.visible = false;
    slot.name.clear();
    slot.motion = {};
    slot.render_component.reset();
    slot.light_component.reset();
    advance_generation(slot);
    free_indices_.push_back(handle.index);
    --entity_count_;
}

void World::clear() noexcept {
    free_indices_.clear();
    free_indices_.reserve(slots_.size());
    for (std::size_t index = 0; index < slots_.size(); ++index) {
        Slot& slot = slots_[index];
        if (slot.alive) {
            advance_generation(slot);
        }
        slot.alive = false;
        slot.enabled = false;
        slot.visible = false;
        slot.name.clear();
        slot.local_transform = {};
        slot.parent_index.reset();
        slot.child_indices.clear();
        slot.transform_dirty = true;
        slot.motion = {};
        slot.render_component.reset();
        slot.light_component.reset();
        free_indices_.push_back(static_cast<std::uint32_t>(index));
    }
    entity_count_ = 0;
    texture_cache_.clear();
    model_cache_.clear();
}

bool World::is_alive(const EntityHandle handle) const noexcept {
    return handle.world_id == id_ && handle.valid() && handle.index < slots_.size() &&
           slots_[handle.index].alive && slots_[handle.index].generation == handle.generation;
}

std::size_t World::entity_count() const noexcept {
    return entity_count_;
}

std::uint64_t World::id() const noexcept {
    return id_;
}

std::vector<EntityHandle> World::entity_handles() const {
    std::vector<EntityHandle> result;
    result.reserve(entity_count_);
    for (std::size_t index = 0; index < slots_.size(); ++index) {
        if (slots_[index].alive) {
            result.push_back(handle_for(static_cast<std::uint32_t>(index)));
        }
    }
    return result;
}

const std::string& World::entity_name(const EntityHandle handle) const {
    return require_slot(handle).name;
}

void World::set_entity_name(const EntityHandle handle, std::string name) {
    validate_name(name);
    require_slot(handle).name = std::move(name);
}

bool World::entity_enabled(const EntityHandle handle) const {
    return require_slot(handle).enabled;
}

void World::set_entity_enabled(const EntityHandle handle, const bool enabled) {
    require_slot(handle).enabled = enabled;
}

bool World::entity_visible(const EntityHandle handle) const {
    return require_slot(handle).visible;
}

void World::set_entity_visible(const EntityHandle handle, const bool visible) {
    require_slot(handle).visible = visible;
}

Transform World::local_transform(const EntityHandle handle) const {
    return require_slot(handle).local_transform;
}

void World::set_local_transform(const EntityHandle handle, Transform transform) {
    validate_transform(transform);
    transform.rotation = transform.rotation.normalized();
    require_slot(handle).local_transform = transform;
    mark_transform_dirty(handle.index);
}

Transform World::world_transform(const EntityHandle handle) const {
    (void)require_slot(handle);
    return decompose_matrix(to_glm(world_matrix(handle.index)));
}

void World::set_world_transform(const EntityHandle handle, Transform transform) {
    validate_transform(transform);
    transform.rotation = transform.rotation.normalized();
    Slot& slot = require_slot(handle);
    if (!slot.parent_index.has_value()) {
        set_local_transform(handle, transform);
        return;
    }
    const glm::mat4 parent_world = to_glm(world_matrix(*slot.parent_index));
    const glm::mat4 local = glm::inverse(parent_world) * compose_matrix(transform);
    set_local_from_matrix(handle.index, from_glm(local));
}

EntityMotion& World::motion(const EntityHandle handle) {
    return require_slot(handle).motion;
}

const EntityMotion& World::motion(const EntityHandle handle) const {
    return require_slot(handle).motion;
}

std::optional<EntityHandle> World::entity_parent(const EntityHandle handle) const {
    const Slot& slot = require_slot(handle);
    if (!slot.parent_index.has_value()) {
        return std::nullopt;
    }
    return handle_for(*slot.parent_index);
}

std::vector<EntityHandle> World::entity_children(const EntityHandle handle) const {
    const Slot& slot = require_slot(handle);
    std::vector<EntityHandle> result;
    result.reserve(slot.child_indices.size());
    for (const std::uint32_t index : slot.child_indices) {
        result.push_back(handle_for(index));
    }
    return result;
}

void World::set_entity_parent(const EntityHandle child_handle,
                              const std::optional<EntityHandle> parent_handle,
                              const bool keep_world) {
    Slot& child = require_slot(child_handle);
    std::optional<std::uint32_t> parent_index;
    if (parent_handle.has_value()) {
        (void)require_slot(*parent_handle);
        if (*parent_handle == child_handle) {
            throw std::invalid_argument("an entity cannot be parented to itself");
        }
        parent_index = parent_handle->index;

        std::optional<std::uint32_t> ancestor = parent_index;
        while (ancestor.has_value()) {
            if (*ancestor == child_handle.index) {
                throw std::invalid_argument("entity parenting would create a cycle");
            }
            ancestor = slots_[*ancestor].parent_index;
        }
    }

    if (child.parent_index == parent_index) {
        return;
    }

    Transform replacement_local = child.local_transform;
    if (keep_world) {
        glm::mat4 local_matrix = to_glm(world_matrix(child_handle.index));
        if (parent_index.has_value()) {
            const glm::mat4 parent_world = to_glm(world_matrix(*parent_index));
            if (std::abs(glm::determinant(parent_world)) <= minimum_scale) {
                throw EngineError("cannot preserve world transform under a singular parent");
            }
            local_matrix = glm::inverse(parent_world) * local_matrix;
        }
        replacement_local = decompose_matrix(local_matrix);
        validate_transform(replacement_local);
    }

    detach_from_parent(child_handle.index);
    child.parent_index = parent_index;
    if (parent_index.has_value()) {
        slots_[*parent_index].child_indices.push_back(child_handle.index);
    }
    child.local_transform = replacement_local;
    mark_transform_dirty(child_handle.index);
}

void World::add_primitive_renderer(
    const EntityHandle handle,
    const RenderKind kind,
    const Color color,
    const std::optional<std::filesystem::path>& texture,
    const TextureMaterialSettings texture_settings,
    const std::optional<std::filesystem::path>& normal_map,
    const std::optional<std::filesystem::path>& roughness_map,
    const std::optional<std::filesystem::path>& metallic_map,
    const std::optional<std::filesystem::path>& emissive_map,
    const std::optional<std::filesystem::path>& ambient_occlusion_map,
    const CullMode cull_mode) {
    Slot& slot = require_slot(handle);
    if (slot.render_component.has_value()) {
        throw EngineError("entity already has its singleton render component");
    }
    Material material{color};
    material.cull_mode = cull_mode;
    material.normal_strength = texture_settings.normal_strength;
    material.validate();
    texture_settings.validate();
    RenderComponent component;
    component.kind = kind;
    component.mesh = primitive_mesh(kind);
    component.material = material;
    component.texture_settings = texture_settings;
    component.cull_mode_override = cull_mode;
    component.sampler.min_filter = texture_settings.filter;
    component.sampler.mag_filter = texture_settings.filter;
    component.sampler.mip_filter = texture_settings.filter;
    if (texture.has_value()) {
        component.texture = texture_cache_.load(
            *texture, TextureColorSpace::Srgb, texture_settings.hot_reload);
    }
    if (normal_map.has_value()) {
        component.normal_map = texture_cache_.load(
            *normal_map, TextureColorSpace::Linear, texture_settings.hot_reload);
    }
    if (roughness_map.has_value()) {
        component.roughness_map =
            texture_cache_.load(*roughness_map,
                                TextureColorSpace::Linear,
                                texture_settings.hot_reload);
    }
    if (metallic_map.has_value()) {
        component.metallic_map =
            texture_cache_.load(*metallic_map,
                                TextureColorSpace::Linear,
                                texture_settings.hot_reload);
    }
    if (emissive_map.has_value()) {
        component.emissive_map = texture_cache_.load(
            *emissive_map, TextureColorSpace::Srgb, texture_settings.hot_reload);
    }
    if (ambient_occlusion_map.has_value()) {
        component.ambient_occlusion_map =
            texture_cache_.load(*ambient_occlusion_map,
                                TextureColorSpace::Linear,
                                texture_settings.hot_reload);
    }
    slot.render_component = std::move(component);
}

void World::add_model_renderer(const EntityHandle handle,
                               const std::filesystem::path& path,
                               const Color color,
                               const std::optional<CullMode> cull_mode_override) {
    Slot& slot = require_slot(handle);
    if (slot.render_component.has_value()) {
        throw EngineError("entity already has its singleton render component");
    }
    Material material{color};
    material.cull_mode = cull_mode_override.value_or(CullMode::Back);
    material.validate();
    RenderComponent component;
    component.kind = RenderKind::Model;
    component.model = model_cache_.load(path);
    component.material = material;
    component.cull_mode_override = cull_mode_override;
    slot.render_component = std::move(component);
}

bool World::has_render_component(const EntityHandle handle) const {
    return require_slot(handle).render_component.has_value();
}

const RenderComponent& World::render_component(const EntityHandle handle) const {
    const Slot& slot = require_slot(handle);
    if (!slot.render_component.has_value()) {
        throw EngineError("entity does not have a render component");
    }
    return *slot.render_component;
}

std::size_t World::poll_texture_changes() const noexcept {
    return texture_cache_.poll_changes();
}

void World::set_render_color(const EntityHandle handle, const Color color) {
    Slot& slot = require_slot(handle);
    if (!slot.render_component.has_value()) {
        throw EngineError("entity does not have a render component");
    }
    RenderComponent& component = *slot.render_component;
    Material material = component.material;
    material.color = color;
    material.validate();
    component.material = material;
}

void World::set_render_lit(const EntityHandle handle, const bool lit) {
    Slot& slot = require_slot(handle);
    if (!slot.render_component.has_value()) {
        throw EngineError("entity does not have a render component");
    }
    slot.render_component->material.lit = lit;
}

void World::set_render_cull_mode(const EntityHandle handle, const CullMode cull_mode) {
    Slot& slot = require_slot(handle);
    if (!slot.render_component.has_value()) {
        throw EngineError("entity does not have a render component");
    }
    slot.render_component->material.cull_mode = cull_mode;
    slot.render_component->cull_mode_override = cull_mode;
}

void World::set_render_surface(const EntityHandle handle,
                               const float metallic,
                               const float roughness,
                               const float emission,
                               const bool casts_shadows,
                               const bool receives_shadows) {
    Slot& slot = require_slot(handle);
    if (!slot.render_component.has_value()) {
        throw EngineError("entity does not have a render component");
    }
    Material replacement = slot.render_component->material;
    replacement.metallic = metallic;
    replacement.roughness = roughness;
    replacement.emission = emission;
    replacement.casts_shadows = casts_shadows;
    replacement.receives_shadows = receives_shadows;
    replacement.validate();
    slot.render_component->material = replacement;
}

void World::set_render_texture(
    const EntityHandle handle,
    const std::optional<std::filesystem::path>& texture,
    const TextureMaterialSettings texture_settings,
    const std::optional<std::filesystem::path>& normal_map,
    const std::optional<std::filesystem::path>& roughness_map,
    const std::optional<std::filesystem::path>& metallic_map,
    const std::optional<std::filesystem::path>& emissive_map,
    const std::optional<std::filesystem::path>& ambient_occlusion_map) {
    Slot& slot = require_slot(handle);
    if (!slot.render_component.has_value()) {
        throw EngineError("entity does not have a render component");
    }
    texture_settings.validate();
    RenderComponent replacement = *slot.render_component;
    replacement.texture = texture.has_value()
                              ? texture_cache_.load(*texture,
                                                    TextureColorSpace::Srgb,
                                                    texture_settings.hot_reload)
                              : nullptr;
    replacement.normal_map = normal_map.has_value()
                                 ? texture_cache_.load(*normal_map,
                                                       TextureColorSpace::Linear,
                                                       texture_settings.hot_reload)
                                 : nullptr;
    replacement.roughness_map = roughness_map.has_value()
                                    ? texture_cache_.load(*roughness_map,
                                                          TextureColorSpace::Linear,
                                                          texture_settings.hot_reload)
                                    : nullptr;
    replacement.metallic_map = metallic_map.has_value()
                                   ? texture_cache_.load(*metallic_map,
                                                         TextureColorSpace::Linear,
                                                         texture_settings.hot_reload)
                                   : nullptr;
    replacement.emissive_map = emissive_map.has_value()
                                   ? texture_cache_.load(*emissive_map,
                                                         TextureColorSpace::Srgb,
                                                         texture_settings.hot_reload)
                                   : nullptr;
    replacement.ambient_occlusion_map =
        ambient_occlusion_map.has_value()
            ? texture_cache_.load(*ambient_occlusion_map,
                                  TextureColorSpace::Linear,
                                  texture_settings.hot_reload)
            : nullptr;
    replacement.texture_settings = texture_settings;
    replacement.material.normal_strength = texture_settings.normal_strength;
    replacement.material.validate();
    replacement.sampler.min_filter = texture_settings.filter;
    replacement.sampler.mag_filter = texture_settings.filter;
    replacement.sampler.mip_filter = texture_settings.filter;
    slot.render_component = std::move(replacement);
}

void World::set_render_image(const EntityHandle handle,
                             std::shared_ptr<const ImageData> texture,
                             const TextureMaterialSettings texture_settings) {
    Slot& slot = require_slot(handle);
    if (!slot.render_component.has_value()) {
        throw EngineError("entity does not have a render component");
    }
    if (!texture) {
        throw std::invalid_argument("dynamic render texture must not be empty");
    }
    texture->validate();
    texture_settings.validate();
    RenderComponent replacement = *slot.render_component;
    replacement.texture = std::move(texture);
    replacement.normal_map.reset();
    replacement.roughness_map.reset();
    replacement.metallic_map.reset();
    replacement.emissive_map.reset();
    replacement.ambient_occlusion_map.reset();
    replacement.texture_settings = texture_settings;
    replacement.sampler.min_filter = texture_settings.filter;
    replacement.sampler.mag_filter = texture_settings.filter;
    replacement.sampler.mip_filter = texture_settings.filter;
    slot.render_component = std::move(replacement);
}

void World::remove_render_component(const EntityHandle handle) {
    Slot& slot = require_slot(handle);
    if (!slot.render_component.has_value()) {
        throw EngineError("entity does not have a render component");
    }
    slot.render_component.reset();
}

void World::add_light_component(const EntityHandle handle,
                                const LightKind kind,
                                const Color color,
                                const float intensity,
                                const float range,
                                const float inner_angle_degrees,
                                const float outer_angle_degrees,
                                const bool casts_shadows,
                                const std::uint16_t shadow_resolution,
                                const float shadow_bias) {
    Slot& slot = require_slot(handle);
    if (slot.light_component.has_value()) {
        throw EngineError("entity already has its singleton light component");
    }
    LightComponent component{kind,
                             color,
                             intensity,
                             range,
                             inner_angle_degrees,
                             outer_angle_degrees,
                             casts_shadows,
                             shadow_resolution,
                             shadow_bias};
    component.validate();
    slot.light_component = component;
}

bool World::has_light_component(const EntityHandle handle) const {
    return require_slot(handle).light_component.has_value();
}

const LightComponent& World::light_component(const EntityHandle handle) const {
    const Slot& slot = require_slot(handle);
    if (!slot.light_component.has_value()) {
        throw EngineError("entity does not have a light component");
    }
    return *slot.light_component;
}

void World::set_light_color(const EntityHandle handle, const Color color) {
    Slot& slot = require_slot(handle);
    if (!slot.light_component.has_value()) {
        throw EngineError("entity does not have a light component");
    }
    LightComponent replacement = *slot.light_component;
    replacement.color = color;
    replacement.validate();
    slot.light_component = replacement;
}

void World::set_light_intensity(const EntityHandle handle, const float intensity) {
    Slot& slot = require_slot(handle);
    if (!slot.light_component.has_value()) {
        throw EngineError("entity does not have a light component");
    }
    LightComponent replacement = *slot.light_component;
    replacement.intensity = intensity;
    replacement.validate();
    slot.light_component = replacement;
}

void World::set_light_properties(const EntityHandle handle,
                                 const float range,
                                 const float inner_angle_degrees,
                                 const float outer_angle_degrees,
                                 const bool casts_shadows,
                                 const std::uint16_t shadow_resolution,
                                 const float shadow_bias) {
    Slot& slot = require_slot(handle);
    if (!slot.light_component.has_value()) {
        throw EngineError("entity does not have a light component");
    }
    LightComponent replacement = *slot.light_component;
    replacement.range = range;
    replacement.inner_angle_degrees = inner_angle_degrees;
    replacement.outer_angle_degrees = outer_angle_degrees;
    replacement.casts_shadows = casts_shadows;
    replacement.shadow_resolution = shadow_resolution;
    replacement.shadow_bias = shadow_bias;
    replacement.validate();
    slot.light_component = replacement;
}

void World::remove_light_component(const EntityHandle handle) {
    Slot& slot = require_slot(handle);
    if (!slot.light_component.has_value()) {
        throw EngineError("entity does not have a light component");
    }
    slot.light_component.reset();
}

World::Slot& World::require_slot(const EntityHandle handle) {
    if (!is_alive(handle)) {
        throw InvalidEntityError(invalid_handle_message(handle, id_));
    }
    return slots_[handle.index];
}

const World::Slot& World::require_slot(const EntityHandle handle) const {
    if (!is_alive(handle)) {
        throw InvalidEntityError(invalid_handle_message(handle, id_));
    }
    return slots_[handle.index];
}

EntityHandle World::handle_for(const std::uint32_t index) const noexcept {
    return EntityHandle{id_, index, slots_[index].generation};
}

const std::array<float, 16>& World::world_matrix(const std::uint32_t index) const {
    const Slot& slot = slots_[index];
    if (slot.transform_dirty) {
        glm::mat4 matrix = compose_matrix(slot.local_transform);
        if (slot.parent_index.has_value()) {
            matrix = to_glm(world_matrix(*slot.parent_index)) * matrix;
        }
        slot.cached_world_matrix = from_glm(matrix);
        slot.transform_dirty = false;
    }
    return slot.cached_world_matrix;
}

void World::mark_transform_dirty(const std::uint32_t index) noexcept {
    Slot& slot = slots_[index];
    if (slot.transform_dirty) {
        return;
    }
    slot.transform_dirty = true;
    for (const std::uint32_t child_index : slot.child_indices) {
        mark_transform_dirty(child_index);
    }
}

void World::detach_from_parent(const std::uint32_t index) noexcept {
    Slot& slot = slots_[index];
    if (!slot.parent_index.has_value()) {
        return;
    }
    std::vector<std::uint32_t>& siblings = slots_[*slot.parent_index].child_indices;
    siblings.erase(std::remove(siblings.begin(), siblings.end(), index), siblings.end());
    slot.parent_index.reset();
}

void World::set_local_from_matrix(const std::uint32_t index,
                                  const std::array<float, 16>& matrix) {
    Transform transform = decompose_matrix(to_glm(matrix));
    validate_transform(transform);
    slots_[index].local_transform = transform;
    mark_transform_dirty(index);
}

void World::validate_name(const std::string_view name) {
    if (name.empty()) {
        throw std::invalid_argument("entity name must not be empty");
    }
}

void World::validate_transform(const Transform& transform) {
    if (!finite(transform.position) || !finite(transform.rotation) || !finite(transform.scale)) {
        throw std::invalid_argument("transform values must be finite");
    }
    if (std::abs(transform.scale.x) <= minimum_scale ||
        std::abs(transform.scale.y) <= minimum_scale ||
        std::abs(transform.scale.z) <= minimum_scale) {
        throw std::invalid_argument("transform scale components must be nonzero");
    }
    if (transform.rotation.length_squared() <= minimum_scale) {
        throw std::invalid_argument("transform rotation quaternion must be nonzero");
    }
}

void World::advance_generation(Slot& slot) noexcept {
    ++slot.generation;
    if (slot.generation == 0) {
        slot.generation = 1;
    }
}

Scene::Scene(std::string name)
    : name_(std::move(name)),
      camera_(Camera::look_at({0.0F, 3.0F, 8.0F}, {0.0F, 0.0F, 0.0F})) {
    validate_name(name_);
}

const std::string& Scene::name() const noexcept {
    return name_;
}

void Scene::set_name(std::string name) {
    validate_name(name);
    name_ = std::move(name);
}

bool Scene::active() const noexcept {
    return active_;
}

void Scene::set_active(const bool active) noexcept {
    active_ = active;
}

EntityHandle Scene::create_entity(std::string name) {
    return world_.create_entity(std::move(name));
}

void Scene::destroy_entity(const EntityHandle handle) {
    (void)world_.entity_name(handle);
    remove_constraints_for(handle);
    const auto physics_component = physics_entities_.find(handle.id());
    if (physics_component != physics_entities_.end()) {
        physics_->destroy_body(physics_component->second.body);
        physics_entities_.erase(physics_component);
    }
    const auto character_component = character_entities_.find(handle.id());
    if (character_component != character_entities_.end()) {
        physics_->destroy_character(character_component->second.character);
        character_entities_.erase(character_component);
    }
    world_.destroy_entity(handle);
}

void Scene::clear() noexcept {
    constraints_.clear();
    physics_entities_.clear();
    character_entities_.clear();
    world_.clear();
    debug_lines_.clear();
    ui_elements_.clear();
    ui_texture_cache_.clear();
    if (physics_) {
        physics_->clear();
    }
}

bool Scene::is_alive(const EntityHandle handle) const noexcept {
    return world_.is_alive(handle);
}

std::size_t Scene::entity_count() const noexcept {
    return world_.entity_count();
}

std::vector<EntityHandle> Scene::entity_handles() const {
    return world_.entity_handles();
}

const std::string& Scene::entity_name(const EntityHandle handle) const {
    return world_.entity_name(handle);
}

void Scene::set_entity_name(const EntityHandle handle, std::string name) {
    world_.set_entity_name(handle, std::move(name));
}

bool Scene::entity_enabled(const EntityHandle handle) const {
    return world_.entity_enabled(handle);
}

void Scene::set_entity_enabled(const EntityHandle handle, const bool enabled) {
    const bool was_enabled = world_.entity_enabled(handle);
    if (was_enabled == enabled) return;
    EntityMotion& motion = world_.motion(handle);
    if (!enabled) {
        motion.paused_world_transform = world_.world_transform(handle);
        motion.paused_velocity = entity_velocity(handle);
        motion.paused_angular_velocity = entity_angular_velocity(handle);
        motion.paused = true;
        const auto physics_component = physics_entities_.find(handle.id());
        if (physics_component != physics_entities_.end() &&
            physics_component->second.rigid_body.has_value()) {
            physics_->set_body_linear_velocity(physics_component->second.body, {});
            physics_->set_body_angular_velocity(physics_component->second.body, {});
        }
        const auto character = character_entities_.find(handle.id());
        if (character != character_entities_.end()) {
            physics_->set_character_paused(character->second.character, true);
        }
    }
    world_.set_entity_enabled(handle, enabled);
    if (enabled && motion.paused) {
        const auto physics_component = physics_entities_.find(handle.id());
        if (physics_component != physics_entities_.end() &&
            physics_component->second.rigid_body.has_value()) {
            physics_->set_body_transform(physics_component->second.body,
                                         motion.paused_world_transform.position,
                                         motion.paused_world_transform.rotation);
            physics_->set_body_linear_velocity(physics_component->second.body,
                                                motion.paused_velocity);
            physics_->set_body_angular_velocity(
                physics_component->second.body,
                motion.paused_angular_velocity * degrees_to_radians);
        }
        const auto character = character_entities_.find(handle.id());
        if (character != character_entities_.end()) {
            physics_->set_character_paused(character->second.character, false);
            physics_->set_character_linear_velocity(character->second.character,
                                                    motion.paused_velocity);
        }
        motion.velocity = motion.paused_velocity;
        motion.angular_velocity = motion.paused_angular_velocity;
        motion.paused = false;
    }
}

bool Scene::entity_visible(const EntityHandle handle) const {
    return world_.entity_visible(handle);
}

void Scene::set_entity_visible(const EntityHandle handle, const bool visible) {
    world_.set_entity_visible(handle, visible);
}

Transform Scene::local_transform(const EntityHandle handle) const {
    return world_.local_transform(handle);
}

void Scene::set_local_transform(const EntityHandle handle, const Transform transform) {
    (void)world_.entity_name(handle);
    const auto physics_component = physics_entities_.find(handle.id());
    if (physics_component != physics_entities_.end() &&
        physics_component->second.rigid_body.has_value() &&
        physics_component->second.rigid_body->motion_type == PhysicsMotionType::Dynamic) {
        throw PhysicsError(
            "dynamic rigid body transforms are physics-owned; use Rigidbody.teleport()");
    }
    if (character_entities_.contains(handle.id())) {
        throw PhysicsError(
            "character transforms are physics-owned; use CharacterController.teleport()");
    }
    world_.set_local_transform(handle, transform);
    if (physics_component != physics_entities_.end()) {
        const Transform updated = world_.world_transform(handle);
        physics_->set_body_transform(
            physics_component->second.body, updated.position, updated.rotation);
    }
}

Transform Scene::world_transform(const EntityHandle handle) const {
    return world_.world_transform(handle);
}

Vec3 Scene::entity_velocity(const EntityHandle handle) const {
    const EntityMotion& motion = world_.motion(handle);
    if (motion.paused) return motion.paused_velocity;
    const auto physics_component = physics_entities_.find(handle.id());
    if (physics_component != physics_entities_.end() &&
        physics_component->second.rigid_body.has_value()) {
        return physics_->body_linear_velocity(physics_component->second.body);
    }
    const auto character = character_entities_.find(handle.id());
    if (character != character_entities_.end()) {
        return physics_->character_state(character->second.character).linear_velocity;
    }
    return motion.velocity;
}

void Scene::set_entity_velocity(const EntityHandle handle, const Vec3 velocity) {
    if (!finite(velocity)) {
        throw std::invalid_argument("entity velocity must be finite");
    }
    EntityMotion& motion = world_.motion(handle);
    const auto physics_component = physics_entities_.find(handle.id());
    if (physics_component != physics_entities_.end()) {
        if (!physics_component->second.rigid_body.has_value()) {
            if (nonzero(velocity)) {
                throw PhysicsError(
                    "moving collider-only entities require a kinematic Rigidbody");
            }
        } else if (!motion.paused) {
            physics_->set_body_linear_velocity(physics_component->second.body, velocity);
        }
    }
    const auto character = character_entities_.find(handle.id());
    if (character != character_entities_.end() && !motion.paused) {
        physics_->set_character_linear_velocity(character->second.character, velocity);
    }
    motion.velocity = velocity;
    if (motion.paused) motion.paused_velocity = velocity;
}

Vec3 Scene::entity_acceleration(const EntityHandle handle) const {
    return world_.motion(handle).acceleration;
}

void Scene::set_entity_acceleration(const EntityHandle handle,
                                    const Vec3 acceleration) {
    if (!finite(acceleration)) {
        throw std::invalid_argument("entity acceleration must be finite");
    }
    const auto physics_component = physics_entities_.find(handle.id());
    if (physics_component != physics_entities_.end() &&
        !physics_component->second.rigid_body.has_value() && nonzero(acceleration)) {
        throw PhysicsError(
            "moving collider-only entities require a kinematic Rigidbody");
    }
    world_.motion(handle).acceleration = acceleration;
}

Vec3 Scene::entity_angular_velocity(const EntityHandle handle) const {
    const EntityMotion& motion = world_.motion(handle);
    if (motion.paused) return motion.paused_angular_velocity;
    const auto physics_component = physics_entities_.find(handle.id());
    if (physics_component != physics_entities_.end() &&
        physics_component->second.rigid_body.has_value()) {
        return physics_->body_angular_velocity(physics_component->second.body) *
               radians_to_degrees;
    }
    return motion.angular_velocity;
}

void Scene::set_entity_angular_velocity(const EntityHandle handle,
                                        const Vec3 degrees_per_second) {
    if (!finite(degrees_per_second)) {
        throw std::invalid_argument("entity angular velocity must be finite");
    }
    const auto character = character_entities_.find(handle.id());
    if (character != character_entities_.end() &&
        (std::abs(degrees_per_second.x) > 1.0e-6F ||
         std::abs(degrees_per_second.z) > 1.0e-6F)) {
        throw PhysicsError(
            "characters remain upright; angular motion supports the Y axis only");
    }
    EntityMotion& motion = world_.motion(handle);
    const auto physics_component = physics_entities_.find(handle.id());
    if (physics_component != physics_entities_.end()) {
        if (!physics_component->second.rigid_body.has_value()) {
            if (nonzero(degrees_per_second)) {
                throw PhysicsError(
                    "moving collider-only entities require a kinematic Rigidbody");
            }
        } else if (!motion.paused) {
            physics_->set_body_angular_velocity(
                physics_component->second.body,
                degrees_per_second * degrees_to_radians);
        }
    }
    motion.angular_velocity = degrees_per_second;
    if (motion.paused) motion.paused_angular_velocity = degrees_per_second;
}

Vec3 Scene::entity_angular_acceleration(const EntityHandle handle) const {
    return world_.motion(handle).angular_acceleration;
}

void Scene::set_entity_angular_acceleration(
    const EntityHandle handle,
    const Vec3 degrees_per_second_squared) {
    if (!finite(degrees_per_second_squared)) {
        throw std::invalid_argument("entity angular acceleration must be finite");
    }
    if (character_entities_.contains(handle.id()) &&
        (std::abs(degrees_per_second_squared.x) > 1.0e-6F ||
         std::abs(degrees_per_second_squared.z) > 1.0e-6F)) {
        throw PhysicsError(
            "characters remain upright; angular motion supports the Y axis only");
    }
    const auto physics_component = physics_entities_.find(handle.id());
    if (physics_component != physics_entities_.end() &&
        !physics_component->second.rigid_body.has_value() &&
        nonzero(degrees_per_second_squared)) {
        throw PhysicsError(
            "moving collider-only entities require a kinematic Rigidbody");
    }
    world_.motion(handle).angular_acceleration = degrees_per_second_squared;
}

float Scene::entity_character_yaw_offset(const EntityHandle handle) const {
    return world_.motion(handle).character_yaw_offset_degrees;
}

void Scene::reset_entity_motion(const EntityHandle handle) {
    set_entity_velocity(handle, {});
    set_entity_acceleration(handle, {});
    set_entity_angular_velocity(handle, {});
    set_entity_angular_acceleration(handle, {});
    world_.motion(handle).character_yaw_offset_degrees = 0.0F;
}

std::optional<EntityHandle> Scene::entity_parent(const EntityHandle handle) const {
    return world_.entity_parent(handle);
}

std::vector<EntityHandle> Scene::entity_children(const EntityHandle handle) const {
    return world_.entity_children(handle);
}

void Scene::set_entity_parent(const EntityHandle child,
                              const std::optional<EntityHandle> parent,
                              const bool keep_world) {
    (void)world_.entity_name(child);
    if (parent.has_value() &&
        (physics_entities_.contains(child.id()) || character_entities_.contains(child.id()))) {
        throw PhysicsError("physics entities cannot be parented in this release");
    }
    world_.set_entity_parent(child, parent, keep_world);
}

void Scene::add_primitive_renderer(
    const EntityHandle handle,
    const RenderKind kind,
    const Color color,
    const std::optional<std::filesystem::path>& texture,
    const TextureMaterialSettings texture_settings,
    const std::optional<std::filesystem::path>& normal_map,
    const std::optional<std::filesystem::path>& roughness_map,
    const std::optional<std::filesystem::path>& metallic_map,
    const std::optional<std::filesystem::path>& emissive_map,
    const std::optional<std::filesystem::path>& ambient_occlusion_map,
    const CullMode cull_mode) {
    world_.add_primitive_renderer(handle,
                                  kind,
                                  color,
                                  texture,
                                  texture_settings,
                                  normal_map,
                                  roughness_map,
                                  metallic_map,
                                  emissive_map,
                                  ambient_occlusion_map,
                                  cull_mode);
}

void Scene::add_model_renderer(const EntityHandle handle,
                               const std::filesystem::path& path,
                               const Color color,
                               const std::optional<CullMode> cull_mode_override) {
    world_.add_model_renderer(handle, path, color, cull_mode_override);
}

bool Scene::has_render_component(const EntityHandle handle) const {
    return world_.has_render_component(handle);
}

const RenderComponent& Scene::render_component(const EntityHandle handle) const {
    return world_.render_component(handle);
}

std::size_t Scene::poll_texture_changes() const noexcept {
    return world_.poll_texture_changes() + sky_texture_cache_.poll_changes();
}

const std::optional<SkyboxConfig>& Scene::skybox() const noexcept {
    return skybox_;
}

void Scene::set_procedural_skybox(const Color top,
                                  const Color horizon,
                                  const Color bottom,
                                  const float brightness,
                                  const float rotation_degrees) {
    SkyboxConfig replacement;
    replacement.kind = SkyboxKind::Procedural;
    replacement.top = top;
    replacement.horizon = horizon;
    replacement.bottom = bottom;
    replacement.brightness = brightness;
    replacement.rotation_degrees = rotation_degrees;
    replacement.validate();
    sky_texture_cache_.clear();
    skybox_ = std::move(replacement);
}

void Scene::set_panorama_skybox(const std::filesystem::path& path,
                                const float brightness,
                                const float rotation_degrees) {
    auto image = load_image(path, TextureColorSpace::Srgb);
    SkyboxConfig replacement;
    replacement.kind = SkyboxKind::Panorama;
    replacement.panorama = std::move(image);
    replacement.brightness = brightness;
    replacement.rotation_degrees = rotation_degrees;
    replacement.validate();
    sky_texture_cache_.clear();
    replacement.panorama = sky_texture_cache_.load(path, TextureColorSpace::Srgb, true);
    skybox_ = std::move(replacement);
}

void Scene::set_cubemap_skybox(const std::array<std::filesystem::path, 6>& paths,
                               const float brightness,
                               const float rotation_degrees) {
    SkyboxConfig replacement;
    replacement.kind = SkyboxKind::Cubemap;
    replacement.brightness = brightness;
    replacement.rotation_degrees = rotation_degrees;
    for (std::size_t index = 0; index < paths.size(); ++index) {
        replacement.cubemap[index] =
            load_image(paths[index], TextureColorSpace::Srgb);
    }
    replacement.validate();
    sky_texture_cache_.clear();
    for (std::size_t index = 0; index < paths.size(); ++index) {
        replacement.cubemap[index] =
            sky_texture_cache_.load(paths[index], TextureColorSpace::Srgb, true);
    }
    skybox_ = std::move(replacement);
}

void Scene::clear_skybox() noexcept {
    skybox_.reset();
    sky_texture_cache_.clear();
}

void Scene::set_render_color(const EntityHandle handle, const Color color) {
    world_.set_render_color(handle, color);
}

void Scene::set_render_lit(const EntityHandle handle, const bool lit) {
    world_.set_render_lit(handle, lit);
}

void Scene::set_render_cull_mode(const EntityHandle handle, const CullMode cull_mode) {
    world_.set_render_cull_mode(handle, cull_mode);
}

void Scene::set_render_surface(const EntityHandle handle,
                               const float metallic,
                               const float roughness,
                               const float emission,
                               const bool casts_shadows,
                               const bool receives_shadows) {
    world_.set_render_surface(handle,
                              metallic,
                              roughness,
                              emission,
                              casts_shadows,
                              receives_shadows);
}

void Scene::set_render_texture(
    const EntityHandle handle,
    const std::optional<std::filesystem::path>& texture,
    const TextureMaterialSettings texture_settings,
    const std::optional<std::filesystem::path>& normal_map,
    const std::optional<std::filesystem::path>& roughness_map,
    const std::optional<std::filesystem::path>& metallic_map,
    const std::optional<std::filesystem::path>& emissive_map,
    const std::optional<std::filesystem::path>& ambient_occlusion_map) {
    world_.set_render_texture(handle,
                              texture,
                              texture_settings,
                              normal_map,
                              roughness_map,
                              metallic_map,
                              emissive_map,
                              ambient_occlusion_map);
}

void Scene::set_render_image(const EntityHandle handle,
                             std::shared_ptr<const ImageData> texture,
                             const TextureMaterialSettings texture_settings) {
    world_.set_render_image(handle, std::move(texture), texture_settings);
}

void Scene::remove_render_component(const EntityHandle handle) {
    world_.remove_render_component(handle);
}

void Scene::add_light_component(const EntityHandle handle,
                                const LightKind kind,
                                const Color color,
                                const float intensity,
                                const float range,
                                const float inner_angle_degrees,
                                const float outer_angle_degrees,
                                const bool casts_shadows,
                                const std::uint16_t shadow_resolution,
                                const float shadow_bias) {
    world_.add_light_component(handle,
                               kind,
                               color,
                               intensity,
                               range,
                               inner_angle_degrees,
                               outer_angle_degrees,
                               casts_shadows,
                               shadow_resolution,
                               shadow_bias);
}

bool Scene::has_light_component(const EntityHandle handle) const {
    return world_.has_light_component(handle);
}

const LightComponent& Scene::light_component(const EntityHandle handle) const {
    return world_.light_component(handle);
}

void Scene::set_light_color(const EntityHandle handle, const Color color) {
    world_.set_light_color(handle, color);
}

void Scene::set_light_intensity(const EntityHandle handle, const float intensity) {
    world_.set_light_intensity(handle, intensity);
}

void Scene::set_light_properties(const EntityHandle handle,
                                 const float range,
                                 const float inner_angle_degrees,
                                 const float outer_angle_degrees,
                                 const bool casts_shadows,
                                 const std::uint16_t shadow_resolution,
                                 const float shadow_bias) {
    world_.set_light_properties(handle,
                                range,
                                inner_angle_degrees,
                                outer_angle_degrees,
                                casts_shadows,
                                shadow_resolution,
                                shadow_bias);
}

void Scene::remove_light_component(const EntityHandle handle) {
    world_.remove_light_component(handle);
}

void Scene::add_collider_component(const EntityHandle handle,
                                   ColliderComponent component) {
    (void)world_.entity_name(handle);
    component.validate();
    if (world_.entity_parent(handle).has_value()) {
        throw PhysicsError("physics entities cannot be parented in this release");
    }
    if (physics_entities_.contains(handle.id())) {
        throw std::invalid_argument("entity already has a collider component");
    }
    if (character_entities_.contains(handle.id())) {
        throw std::invalid_argument(
            "character controller entities cannot also have collider components");
    }
    const EntityMotion& motion = world_.motion(handle);
    if (nonzero(motion.velocity) || nonzero(motion.acceleration) ||
        nonzero(motion.angular_velocity) || nonzero(motion.angular_acceleration)) {
        throw PhysicsError(
            "moving collider-only entities require a kinematic Rigidbody");
    }

    PhysicsEntity physics_component{std::move(component), std::nullopt, {}};
    physics_component.body = create_physics_body(handle, physics_component);
    try {
        physics_entities_.emplace(handle.id(), std::move(physics_component));
    } catch (...) {
        physics_->destroy_body(physics_component.body);
        throw;
    }
}

bool Scene::has_collider_component(const EntityHandle handle) const {
    (void)world_.entity_name(handle);
    return physics_entities_.contains(handle.id());
}

const ColliderComponent& Scene::collider_component(const EntityHandle handle) const {
    return require_physics_entity(handle).collider;
}

void Scene::remove_collider_component(const EntityHandle handle) {
    PhysicsEntity& component = require_physics_entity(handle);
    remove_constraints_for(handle);
    physics_->destroy_body(component.body);
    physics_entities_.erase(handle.id());
}

void Scene::add_rigid_body_component(const EntityHandle handle,
                                     RigidBodyComponent component) {
    component.validate();
    PhysicsEntity& physics_component = require_physics_entity(handle);
    if (physics_component.rigid_body.has_value()) {
        throw std::invalid_argument("entity already has a rigid body component");
    }
    physics_component.rigid_body = component;
    try {
        replace_physics_body(handle, physics_component);
        const EntityMotion& motion = world_.motion(handle);
        if (!motion.paused) {
            physics_->set_body_linear_velocity(physics_component.body, motion.velocity);
            physics_->set_body_angular_velocity(
                physics_component.body,
                motion.angular_velocity * degrees_to_radians);
        }
    } catch (...) {
        physics_component.rigid_body.reset();
        throw;
    }
}

bool Scene::has_rigid_body_component(const EntityHandle handle) const {
    (void)world_.entity_name(handle);
    const auto component = physics_entities_.find(handle.id());
    return component != physics_entities_.end() && component->second.rigid_body.has_value();
}

const RigidBodyComponent& Scene::rigid_body_component(const EntityHandle handle) const {
    const PhysicsEntity& component = require_physics_entity(handle);
    if (!component.rigid_body.has_value()) {
        throw std::invalid_argument("entity does not have a rigid body component");
    }
    return *component.rigid_body;
}

void Scene::remove_rigid_body_component(const EntityHandle handle) {
    PhysicsEntity& component = require_physics_entity(handle);
    if (!component.rigid_body.has_value()) {
        throw std::invalid_argument("entity does not have a rigid body component");
    }
    EntityMotion& motion = world_.motion(handle);
    motion.velocity = physics_->body_linear_velocity(component.body);
    motion.angular_velocity =
        physics_->body_angular_velocity(component.body) * radians_to_degrees;
    const RigidBodyComponent previous = *component.rigid_body;
    remove_constraints_for(handle);
    component.rigid_body.reset();
    try {
        replace_physics_body(handle, component);
    } catch (...) {
        component.rigid_body = previous;
        throw;
    }
}

Vec3 Scene::rigid_body_linear_velocity(const EntityHandle handle) const {
    const PhysicsEntity& component = require_physics_entity(handle);
    (void)rigid_body_component(handle);
    return physics_->body_linear_velocity(component.body);
}

void Scene::set_rigid_body_linear_velocity(const EntityHandle handle,
                                           const Vec3 velocity) {
    PhysicsEntity& component = require_physics_entity(handle);
    (void)rigid_body_component(handle);
    physics_->set_body_linear_velocity(component.body, velocity);
    world_.motion(handle).velocity = velocity;
}

Vec3 Scene::rigid_body_angular_velocity(const EntityHandle handle) const {
    const PhysicsEntity& component = require_physics_entity(handle);
    (void)rigid_body_component(handle);
    return physics_->body_angular_velocity(component.body) * radians_to_degrees;
}

void Scene::set_rigid_body_angular_velocity(const EntityHandle handle,
                                            const Vec3 degrees_per_second) {
    PhysicsEntity& component = require_physics_entity(handle);
    (void)rigid_body_component(handle);
    physics_->set_body_angular_velocity(component.body,
                                        degrees_per_second * degrees_to_radians);
    world_.motion(handle).angular_velocity = degrees_per_second;
}

void Scene::add_rigid_body_force(const EntityHandle handle, const Vec3 force) {
    PhysicsEntity& component = require_physics_entity(handle);
    (void)rigid_body_component(handle);
    physics_->add_force(component.body, force);
}

void Scene::add_rigid_body_impulse(const EntityHandle handle, const Vec3 impulse) {
    PhysicsEntity& component = require_physics_entity(handle);
    (void)rigid_body_component(handle);
    physics_->add_impulse(component.body, impulse);
}

void Scene::teleport_rigid_body(const EntityHandle handle,
                                const Vec3 position,
                                const Quat rotation) {
    PhysicsEntity& component = require_physics_entity(handle);
    (void)rigid_body_component(handle);
    Transform transform = world_.local_transform(handle);
    transform.position = position;
    transform.rotation = rotation;
    world_.set_local_transform(handle, transform);
    physics_->set_body_transform(component.body, position, rotation);
}

void Scene::add_character_controller_component(
    const EntityHandle handle,
    CharacterControllerComponent component) {
    (void)world_.entity_name(handle);
    component.validate();
    if (world_.entity_parent(handle).has_value()) {
        throw PhysicsError("physics entities cannot be parented in this release");
    }
    if (physics_entities_.contains(handle.id())) {
        throw std::invalid_argument(
            "character controller entities cannot also have collider components");
    }
    if (character_entities_.contains(handle.id())) {
        throw std::invalid_argument("entity already has a character controller component");
    }
    const EntityMotion& motion = world_.motion(handle);
    if (std::abs(motion.angular_velocity.x) > 1.0e-6F ||
        std::abs(motion.angular_velocity.z) > 1.0e-6F ||
        std::abs(motion.angular_acceleration.x) > 1.0e-6F ||
        std::abs(motion.angular_acceleration.z) > 1.0e-6F) {
        throw PhysicsError(
            "characters remain upright; angular motion supports the Y axis only");
    }
    const Transform transform = world_.world_transform(handle);
    CharacterMotorSettings settings{};
    settings.mode = component.mode;
    settings.position = transform.position;
    settings.radius = component.radius;
    settings.height = component.height;
    settings.speed = component.speed;
    settings.acceleration = component.acceleration;
    settings.air_acceleration = component.air_acceleration;
    settings.ground_friction = component.ground_friction;
    settings.stop_speed = component.stop_speed;
    settings.air_speed_cap = component.air_speed_cap;
    settings.horizontal_speed_limit = component.horizontal_speed_limit;
    settings.jump_speed = component.jump_speed;
    settings.max_slope_degrees = component.max_slope_degrees;
    settings.step_height = component.step_height;
    settings.sprint_multiplier = component.sprint_multiplier;
    settings.crouch_height = component.crouch_height;
    settings.crouch_speed_multiplier = component.crouch_speed_multiplier;
    settings.user_data = handle.id();
    const PhysicsCharacterHandle character = physics().create_character(settings);
    try {
        EntityMotion& mutable_motion = world_.motion(handle);
        physics_->set_character_linear_velocity(character, mutable_motion.velocity);
        physics_->set_character_external_motion(
            character,
            mutable_motion.acceleration,
            mutable_motion.character_yaw_offset_degrees);
        character_entities_.emplace(
            handle.id(), CharacterEntity{std::move(component), character});
    } catch (...) {
        physics_->destroy_character(character);
        throw;
    }
}

bool Scene::has_character_controller_component(const EntityHandle handle) const {
    (void)world_.entity_name(handle);
    return character_entities_.contains(handle.id());
}

const CharacterControllerComponent& Scene::character_controller_component(
    const EntityHandle handle) const {
    return require_character_entity(handle).component;
}

void Scene::remove_character_controller_component(const EntityHandle handle) {
    CharacterEntity& component = require_character_entity(handle);
    world_.motion(handle).velocity =
        physics_->character_state(component.character).linear_velocity;
    physics_->destroy_character(component.character);
    character_entities_.erase(handle.id());
}

void Scene::set_character_input(const EntityHandle handle,
                                const Vec3 movement,
                                const float heading_degrees,
                                const bool jump,
                                const bool sprint,
                                const bool crouch) {
    CharacterEntity& component = require_character_entity(handle);
    physics_->set_character_input(
        component.character, {movement, heading_degrees, jump, sprint, crouch});
}

void Scene::set_character_sequenced_input(const EntityHandle handle,
                                          const std::uint64_t sequence,
                                          const Vec3 movement,
                                          const float heading_degrees,
                                          const bool jump,
                                          const bool sprint,
                                          const bool crouch) {
    CharacterEntity& component = require_character_entity(handle);
    physics_->set_character_sequenced_input(
        component.character,
        sequence,
        {movement, heading_degrees, jump, sprint, crouch});
}

std::uint64_t Scene::character_input_sequence(const EntityHandle handle) const {
    const CharacterEntity& component = require_character_entity(handle);
    return physics_->character_input_sequence(component.character);
}

CharacterMotorState Scene::character_state(const EntityHandle handle) const {
    const CharacterEntity& component = require_character_entity(handle);
    return physics_->character_state(component.character);
}

void Scene::correct_character(const EntityHandle handle,
                              const Vec3 position,
                              const Quat rotation,
                              const Vec3 linear_velocity) {
    CharacterEntity& component = require_character_entity(handle);
    physics_->correct_character(
        component.character, position, rotation, linear_velocity);
    world_.motion(handle).velocity = linear_velocity;
    const CharacterMotorState state = physics_->character_state(component.character);
    Transform transform = world_.local_transform(handle);
    transform.position = state.position;
    transform.rotation = state.rotation;
    world_.set_local_transform(handle, transform);
}

void Scene::replay_character_input(const EntityHandle handle,
                                   const Vec3 movement,
                                   const float heading_degrees,
                                   const bool jump,
                                   const bool sprint,
                                   const bool crouch,
                                   const float delta_seconds) {
    CharacterEntity& component = require_character_entity(handle);
    physics_->replay_character_input(
        component.character,
        {movement, heading_degrees, jump, sprint, crouch},
        delta_seconds);
    const CharacterMotorState state = physics_->character_state(component.character);
    world_.motion(handle).velocity = state.linear_velocity;
    Transform transform = world_.local_transform(handle);
    transform.position = state.position;
    transform.rotation = state.rotation;
    world_.set_local_transform(handle, transform);
}

void Scene::set_character_linear_velocity(const EntityHandle handle,
                                          const Vec3 velocity) {
    CharacterEntity& component = require_character_entity(handle);
    physics_->set_character_linear_velocity(component.character, velocity);
    world_.motion(handle).velocity = velocity;
}

void Scene::teleport_character(const EntityHandle handle,
                               const Vec3 position,
                               const float heading_degrees) {
    CharacterEntity& component = require_character_entity(handle);
    const Vec3 velocity =
        physics_->character_state(component.character).linear_velocity;
    physics_->teleport_character(component.character, position, heading_degrees);
    physics_->set_character_linear_velocity(component.character, velocity);
    const CharacterMotorState state = physics_->character_state(component.character);
    Transform transform = world_.local_transform(handle);
    transform.position = state.position;
    transform.rotation = state.rotation;
    world_.set_local_transform(handle, transform);
}

PhysicsConstraintHandle Scene::add_fixed_constraint(const EntityHandle first,
                                                    const EntityHandle second) {
    const PhysicsEntity& first_component = require_physics_entity(first);
    const PhysicsEntity& second_component = require_physics_entity(second);
    const PhysicsConstraintHandle constraint = physics_->create_constraint(
        {.type = PhysicsConstraintType::Fixed,
         .first = first_component.body,
         .second = second_component.body});
    try {
        constraints_.emplace(
            constraint.id(), SceneConstraint{constraint, first, second});
    } catch (...) {
        physics_->destroy_constraint(constraint);
        throw;
    }
    return constraint;
}

PhysicsConstraintHandle Scene::add_distance_constraint(
    const EntityHandle first,
    const EntityHandle second,
    const Vec3 first_anchor,
    const Vec3 second_anchor,
    const float minimum_distance,
    const float maximum_distance) {
    const PhysicsEntity& first_component = require_physics_entity(first);
    const PhysicsEntity& second_component = require_physics_entity(second);
    const PhysicsConstraintHandle constraint = physics_->create_constraint(
        {.type = PhysicsConstraintType::Distance,
         .first = first_component.body,
         .second = second_component.body,
         .first_anchor = first_anchor,
         .second_anchor = second_anchor,
         .minimum_distance = minimum_distance,
         .maximum_distance = maximum_distance});
    try {
        constraints_.emplace(
            constraint.id(), SceneConstraint{constraint, first, second});
    } catch (...) {
        physics_->destroy_constraint(constraint);
        throw;
    }
    return constraint;
}

void Scene::remove_constraint(const PhysicsConstraintHandle handle) {
    const auto constraint = constraints_.find(handle.id());
    if (constraint == constraints_.end() || constraint->second.constraint != handle ||
        !physics_ || !physics_->is_alive(handle)) {
        throw PhysicsError("invalid or stale scene constraint handle");
    }
    physics_->destroy_constraint(handle);
    constraints_.erase(constraint);
}

bool Scene::has_constraint(const PhysicsConstraintHandle handle) const noexcept {
    const auto constraint = constraints_.find(handle.id());
    return constraint != constraints_.end() && constraint->second.constraint == handle &&
           physics_ && physics_->is_alive(handle);
}

std::vector<ScenePhysicsQueryHit> Scene::raycast_all(
    const Vec3 origin,
    const Vec3 direction,
    const float max_distance,
    const std::uint8_t layer_mask,
    const bool include_triggers,
    const std::optional<EntityHandle> excluded) const {
    if (!finite(origin) || !finite(direction) || direction.length_squared() <= 1.0e-12F ||
        !std::isfinite(max_distance) || max_distance <= 0.0F) {
        throw std::invalid_argument(
            "ray origin/direction must be finite and max distance positive");
    }
    if (excluded.has_value()) (void)world_.entity_name(*excluded);
    if (!physics_) return {};
    const PhysicsQueryFilter filter{
        layer_mask,
        include_triggers,
        excluded.has_value() ? excluded->id() : 0,
    };
    std::vector<ScenePhysicsQueryHit> result;
    for (const PhysicsQueryHit& hit :
         physics_->raycast_all(origin, direction, max_distance, filter)) {
        const EntityHandle entity = handle_from_id(hit.user_data);
        if (world_.is_alive(entity)) {
            result.push_back({entity, hit.point, hit.normal, hit.distance, hit.fraction});
        }
    }
    return result;
}

std::vector<ScenePhysicsQueryHit> Scene::overlap_sphere(
    const Vec3 center,
    const float radius,
    const std::uint8_t layer_mask,
    const bool include_triggers,
    const std::optional<EntityHandle> excluded) const {
    if (!finite(center) || !std::isfinite(radius) || radius <= 0.0F) {
        throw std::invalid_argument("overlap sphere center must be finite and radius positive");
    }
    if (excluded.has_value()) (void)world_.entity_name(*excluded);
    if (!physics_) return {};
    const PhysicsQueryFilter filter{
        layer_mask,
        include_triggers,
        excluded.has_value() ? excluded->id() : 0,
    };
    std::vector<ScenePhysicsQueryHit> result;
    for (const PhysicsQueryHit& hit : physics_->overlap_sphere(center, radius, filter)) {
        const EntityHandle entity = handle_from_id(hit.user_data);
        if (world_.is_alive(entity)) {
            result.push_back({entity, hit.point, hit.normal, hit.distance, hit.fraction});
        }
    }
    return result;
}

std::vector<ScenePhysicsQueryHit> Scene::overlap_box(
    const Vec3 center,
    const Vec3 half_extents,
    const Quat rotation,
    const std::uint8_t layer_mask,
    const bool include_triggers,
    const std::optional<EntityHandle> excluded) const {
    if (!finite(center) || !finite(half_extents) || !finite(rotation) ||
        half_extents.x <= 0.0F || half_extents.y <= 0.0F || half_extents.z <= 0.0F) {
        throw std::invalid_argument(
            "overlap box transform must be finite and half extents positive");
    }
    if (excluded.has_value()) (void)world_.entity_name(*excluded);
    if (!physics_) return {};
    const PhysicsQueryFilter filter{
        layer_mask,
        include_triggers,
        excluded.has_value() ? excluded->id() : 0,
    };
    std::vector<ScenePhysicsQueryHit> result;
    for (const PhysicsQueryHit& hit :
         physics_->overlap_box(center, half_extents, rotation, filter)) {
        const EntityHandle entity = handle_from_id(hit.user_data);
        if (world_.is_alive(entity)) {
            result.push_back({entity, hit.point, hit.normal, hit.distance, hit.fraction});
        }
    }
    return result;
}

std::vector<ScenePhysicsQueryHit> Scene::sphere_cast_all(
    const Vec3 origin,
    const float radius,
    const Vec3 direction,
    const float max_distance,
    const std::uint8_t layer_mask,
    const bool include_triggers,
    const std::optional<EntityHandle> excluded) const {
    if (!finite(origin) || !std::isfinite(radius) || radius <= 0.0F ||
        !finite(direction) || direction.length_squared() <= 1.0e-12F ||
        !std::isfinite(max_distance) || max_distance <= 0.0F) {
        throw std::invalid_argument(
            "sphere cast requires finite values and positive radius/distance");
    }
    if (excluded.has_value()) (void)world_.entity_name(*excluded);
    if (!physics_) return {};
    const PhysicsQueryFilter filter{layer_mask,
                                    include_triggers,
                                    excluded.has_value() ? excluded->id() : 0};
    std::vector<ScenePhysicsQueryHit> result;
    for (const PhysicsQueryHit& hit :
         physics_->sphere_cast_all(origin, radius, direction, max_distance, filter)) {
        const EntityHandle entity = handle_from_id(hit.user_data);
        if (world_.is_alive(entity)) {
            result.push_back({entity, hit.point, hit.normal, hit.distance, hit.fraction});
        }
    }
    return result;
}

std::vector<ScenePhysicsQueryHit> Scene::capsule_cast_all(
    const Vec3 origin,
    const float radius,
    const float height,
    const Quat rotation,
    const Vec3 direction,
    const float max_distance,
    const std::uint8_t layer_mask,
    const bool include_triggers,
    const std::optional<EntityHandle> excluded) const {
    if (!finite(origin) || !finite(rotation) || !std::isfinite(radius) || radius <= 0.0F ||
        !std::isfinite(height) || height <= radius * 2.0F || !finite(direction) ||
        direction.length_squared() <= 1.0e-12F || !std::isfinite(max_distance) ||
        max_distance <= 0.0F) {
        throw std::invalid_argument(
            "capsule cast requires finite values, positive radius/distance, and height > diameter");
    }
    if (excluded.has_value()) (void)world_.entity_name(*excluded);
    if (!physics_) return {};
    const PhysicsQueryFilter filter{layer_mask,
                                    include_triggers,
                                    excluded.has_value() ? excluded->id() : 0};
    std::vector<ScenePhysicsQueryHit> result;
    for (const PhysicsQueryHit& hit : physics_->capsule_cast_all(
             origin, radius, height, rotation, direction, max_distance, filter)) {
        const EntityHandle entity = handle_from_id(hit.user_data);
        if (world_.is_alive(entity)) {
            result.push_back({entity, hit.point, hit.normal, hit.distance, hit.fraction});
        }
    }
    return result;
}

std::vector<ScenePhysicsContactEvent> Scene::drain_physics_events() {
    if (!physics_) return {};
    std::vector<ScenePhysicsContactEvent> result;
    for (const PhysicsContactEvent& event : physics_->drain_contact_events()) {
        const EntityHandle first = handle_from_id(event.first_user_data);
        const EntityHandle second = handle_from_id(event.second_user_data);
        if (world_.is_alive(first) && world_.is_alive(second)) {
            result.push_back(
                {event.phase, first, second, event.point, event.normal, event.trigger});
        }
    }
    return result;
}

const Camera& Scene::camera() const noexcept {
    return camera_;
}

void Scene::set_camera(Camera camera) {
    camera.validate();
    camera_ = camera;
}

void Scene::add_debug_line(DebugLine line) {
    line.validate();
    debug_lines_.push_back(line);
}

void Scene::clear_debug_lines() noexcept {
    debug_lines_.clear();
}

const std::vector<DebugLine>& Scene::debug_lines() const noexcept {
    return debug_lines_;
}

std::uint64_t Scene::add_ui_element(
    UiElement element,
    const std::optional<std::filesystem::path>& texture) {
    if (texture.has_value()) {
        element.texture = ui_texture_cache_.load(*texture, TextureColorSpace::Srgb);
    }
    element.id = next_ui_id_++;
    if (next_ui_id_ == 0) {
        next_ui_id_ = 1;
    }
    element.validate();
    ui_elements_.push_back(std::move(element));
    return ui_elements_.back().id;
}

const UiElement& Scene::ui_element(const std::uint64_t id) const {
    const auto found = std::find_if(ui_elements_.begin(), ui_elements_.end(),
                                    [id](const UiElement& element) {
                                        return element.id == id;
                                    });
    if (found == ui_elements_.end()) {
        throw EngineError("UI element does not exist");
    }
    return *found;
}

void Scene::update_ui_element(const std::uint64_t id, UiElement element) {
    auto found = std::find_if(ui_elements_.begin(), ui_elements_.end(),
                              [id](const UiElement& candidate) {
                                  return candidate.id == id;
                              });
    if (found == ui_elements_.end()) {
        throw EngineError("UI element does not exist");
    }
    element.id = id;
    element.kind = found->kind;
    element.texture = found->texture;
    element.validate();
    *found = std::move(element);
}

void Scene::set_ui_image(const std::uint64_t id,
                         std::shared_ptr<const ImageData> texture) {
    auto found = std::find_if(ui_elements_.begin(), ui_elements_.end(),
                              [id](const UiElement& candidate) {
                                  return candidate.id == id;
                              });
    if (found == ui_elements_.end()) {
        throw EngineError("UI element does not exist");
    }
    if (!texture) {
        throw std::invalid_argument("dynamic UI texture must not be empty");
    }
    texture->validate();
    found->texture = std::move(texture);
}

void Scene::remove_ui_element(const std::uint64_t id) {
    const auto found = std::find_if(ui_elements_.begin(), ui_elements_.end(),
                                    [id](const UiElement& element) {
                                        return element.id == id;
                                    });
    if (found == ui_elements_.end()) {
        throw EngineError("UI element does not exist");
    }
    ui_elements_.erase(found);
}

void Scene::clear_ui() noexcept {
    ui_elements_.clear();
    ui_texture_cache_.clear();
}

const std::vector<UiElement>& Scene::ui_elements() const noexcept {
    return ui_elements_;
}

Vec3 Scene::physics_gravity() const noexcept {
    return physics_ ? physics_->gravity() : Vec3{0.0F, -9.81F, 0.0F};
}

void Scene::set_physics_gravity(const Vec3 gravity) {
    physics().set_gravity(gravity);
}

void Scene::step_physics(const float delta_seconds) {
    if (!std::isfinite(delta_seconds) || delta_seconds <= 0.0F) {
        throw std::invalid_argument("motion delta must be finite and positive");
    }
    for (const EntityHandle handle : world_.entity_handles()) {
        EntityMotion& motion = world_.motion(handle);
        if (!world_.entity_enabled(handle) || motion.paused) continue;
        const auto physics_component = physics_entities_.find(handle.id());
        const auto character = character_entities_.find(handle.id());
        if (character != character_entities_.end()) {
            motion.angular_velocity = motion.angular_velocity +
                                      motion.angular_acceleration * delta_seconds;
            motion.character_yaw_offset_degrees +=
                motion.angular_velocity.y * delta_seconds;
            physics_->set_character_external_motion(
                character->second.character,
                motion.acceleration,
                motion.character_yaw_offset_degrees);
            continue;
        }
        if (physics_component != physics_entities_.end()) {
            if (physics_component->second.rigid_body.has_value()) {
                motion.velocity =
                    physics_->body_linear_velocity(physics_component->second.body) +
                    motion.acceleration * delta_seconds;
                motion.angular_velocity =
                    physics_->body_angular_velocity(physics_component->second.body) *
                        radians_to_degrees +
                    motion.angular_acceleration * delta_seconds;
                physics_->set_body_linear_velocity(physics_component->second.body,
                                                   motion.velocity);
                physics_->set_body_angular_velocity(
                    physics_component->second.body,
                    motion.angular_velocity * degrees_to_radians);
            }
            continue;
        }
        motion.velocity = motion.velocity + motion.acceleration * delta_seconds;
        motion.angular_velocity = motion.angular_velocity +
                                  motion.angular_acceleration * delta_seconds;
        if (!nonzero(motion.velocity) && !nonzero(motion.angular_velocity)) continue;
        Transform transform = world_.world_transform(handle);
        transform.position = transform.position + motion.velocity * delta_seconds;
        transform.rotation = apply_world_angular_step(
            transform.rotation, motion.angular_velocity, delta_seconds);
        world_.set_world_transform(handle, transform);
    }

    if (physics_) {
        for (const auto& [entity_id, component] : physics_entities_) {
            const EntityHandle handle{
                world_.id(),
                static_cast<std::uint32_t>(entity_id & 0xffff'ffffULL),
                static_cast<std::uint32_t>(entity_id >> 32U),
            };
            const EntityMotion& motion = world_.motion(handle);
            if (!motion.paused || !component.rigid_body.has_value()) continue;
            physics_->set_body_transform(component.body,
                                         motion.paused_world_transform.position,
                                         motion.paused_world_transform.rotation);
            physics_->set_body_linear_velocity(component.body, {});
            physics_->set_body_angular_velocity(component.body, {});
        }
        physics_->step(delta_seconds);
        for (const auto& [entity_id, component] : physics_entities_) {
            if (!component.rigid_body.has_value()) {
                continue;
            }
            const EntityHandle handle{
                world_.id(),
                static_cast<std::uint32_t>(entity_id & 0xffff'ffffULL),
                static_cast<std::uint32_t>(entity_id >> 32U),
            };
            EntityMotion& motion = world_.motion(handle);
            Transform transform = world_.local_transform(handle);
            if (motion.paused) {
                physics_->set_body_transform(component.body,
                                             motion.paused_world_transform.position,
                                             motion.paused_world_transform.rotation);
                physics_->set_body_linear_velocity(component.body, {});
                physics_->set_body_angular_velocity(component.body, {});
                transform.position = motion.paused_world_transform.position;
                transform.rotation = motion.paused_world_transform.rotation;
            } else {
                transform.position = physics_->body_position(component.body);
                transform.rotation = physics_->body_rotation(component.body);
                motion.velocity = physics_->body_linear_velocity(component.body);
                motion.angular_velocity =
                    physics_->body_angular_velocity(component.body) *
                    radians_to_degrees;
            }
            world_.set_local_transform(handle, transform);
        }
        for (const auto& [entity_id, component] : character_entities_) {
            const EntityHandle handle{
                world_.id(),
                static_cast<std::uint32_t>(entity_id & 0xffff'ffffULL),
                static_cast<std::uint32_t>(entity_id >> 32U),
            };
            EntityMotion& motion = world_.motion(handle);
            if (motion.paused) {
                physics_->set_character_paused(component.character, true);
                Transform transform = world_.local_transform(handle);
                transform.position = motion.paused_world_transform.position;
                transform.rotation = motion.paused_world_transform.rotation;
                world_.set_local_transform(handle, transform);
                continue;
            }
            const CharacterMotorState state = physics_->character_state(component.character);
            motion.velocity = state.linear_velocity;
            Transform transform = world_.local_transform(handle);
            transform.position = state.position;
            transform.rotation = state.rotation;
            world_.set_local_transform(handle, transform);
        }
    }
}

std::uint64_t Scene::physics_step_count() const noexcept {
    return physics_ ? physics_->step_count() : 0;
}

PhysicsWorld& Scene::physics() {
    if (!physics_) {
        physics_ = std::make_unique<PhysicsWorld>();
    }
    return *physics_;
}

const PhysicsWorld* Scene::physics_if_initialized() const noexcept {
    return physics_.get();
}

Scene::PhysicsEntity& Scene::require_physics_entity(const EntityHandle handle) {
    (void)world_.entity_name(handle);
    const auto component = physics_entities_.find(handle.id());
    if (component == physics_entities_.end()) {
        throw std::invalid_argument("entity does not have a collider component");
    }
    return component->second;
}

const Scene::PhysicsEntity& Scene::require_physics_entity(const EntityHandle handle) const {
    (void)world_.entity_name(handle);
    const auto component = physics_entities_.find(handle.id());
    if (component == physics_entities_.end()) {
        throw std::invalid_argument("entity does not have a collider component");
    }
    return component->second;
}

Scene::CharacterEntity& Scene::require_character_entity(const EntityHandle handle) {
    (void)world_.entity_name(handle);
    const auto component = character_entities_.find(handle.id());
    if (component == character_entities_.end()) {
        throw std::invalid_argument("entity does not have a character controller component");
    }
    return component->second;
}

const Scene::CharacterEntity& Scene::require_character_entity(
    const EntityHandle handle) const {
    (void)world_.entity_name(handle);
    const auto component = character_entities_.find(handle.id());
    if (component == character_entities_.end()) {
        throw std::invalid_argument("entity does not have a character controller component");
    }
    return component->second;
}

PhysicsBodyHandle Scene::create_physics_body(const EntityHandle handle,
                                             const PhysicsEntity& component) {
    const Transform transform = world_.world_transform(handle);
    PhysicsBodySettings settings{};
    settings.shape = component.collider.shape;
    settings.position = transform.position;
    settings.rotation = transform.rotation;
    settings.half_extents = component.collider.half_extents;
    settings.radius = component.collider.radius;
    settings.height = component.collider.height;
    settings.vertices = component.collider.vertices;
    settings.indices = component.collider.indices;
    if (settings.shape == PhysicsShape::ConvexHull ||
        settings.shape == PhysicsShape::TriangleMesh) {
        for (Vec3& vertex : settings.vertices) {
            vertex.x *= transform.scale.x;
            vertex.y *= transform.scale.y;
            vertex.z *= transform.scale.z;
        }
    }
    settings.material = component.collider.material;
    settings.user_data = handle.id();
    settings.motion_type = component.rigid_body.has_value()
                               ? component.rigid_body->motion_type
                               : PhysicsMotionType::Static;
    settings.layer = component.collider.trigger
                         ? CollisionLayer::Sensor
                         : (component.rigid_body.has_value() ? component.collider.layer
                                                             : CollisionLayer::Static);
    if (component.rigid_body.has_value()) {
        settings.mass = component.rigid_body->mass;
        settings.gravity_factor = component.rigid_body->use_gravity ? 1.0F : 0.0F;
        settings.continuous = component.rigid_body->continuous;
    }
    return physics().create_body(settings);
}

void Scene::replace_physics_body(const EntityHandle handle,
                                 PhysicsEntity& component) {
    remove_constraints_for(handle);
    const PhysicsBodyHandle replacement = create_physics_body(handle, component);
    physics_->destroy_body(component.body);
    component.body = replacement;
}

void Scene::remove_constraints_for(const EntityHandle handle) noexcept {
    for (auto constraint = constraints_.begin(); constraint != constraints_.end();) {
        if (constraint->second.first != handle && constraint->second.second != handle) {
            ++constraint;
            continue;
        }
        if (physics_ && physics_->is_alive(constraint->second.constraint)) {
            physics_->destroy_constraint(constraint->second.constraint);
        }
        constraint = constraints_.erase(constraint);
    }
}

EntityHandle Scene::handle_from_id(const std::uint64_t id) const noexcept {
    return {world_.id(),
            static_cast<std::uint32_t>(id & 0xffff'ffffULL),
            static_cast<std::uint32_t>(id >> 32U)};
}

World& Scene::world() noexcept {
    return world_;
}

const World& Scene::world() const noexcept {
    return world_;
}

void Scene::validate_name(const std::string_view name) {
    if (name.empty()) {
        throw std::invalid_argument("scene name must not be empty");
    }
}

} // namespace easy3d
