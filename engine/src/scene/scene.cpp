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

std::uint64_t EntityHandle::id() const noexcept {
    return (static_cast<std::uint64_t>(generation) << 32U) | index;
}

void LightComponent::validate() const {
    (void)color.rgba8();
    if (!std::isfinite(intensity) || intensity < 0.0F) {
        throw std::invalid_argument("light intensity must be finite and non-negative");
    }
}

World::World() : id_(next_world_id.fetch_add(1, std::memory_order_relaxed)) {
    if (id_ == 0) {
        throw EngineError("Easy3D exhausted native world identifiers");
    }
}

EntityHandle World::create_entity(std::string name) {
    validate_name(name);

    std::uint32_t index = 0;
    if (free_indices_.empty()) {
        if (slots_.size() >= EntityHandle::invalid_index) {
            throw EngineError("Easy3D exhausted entity slots in this world");
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
        slot.render_component.reset();
        slot.light_component.reset();
        free_indices_.push_back(static_cast<std::uint32_t>(index));
    }
    entity_count_ = 0;
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
    const std::optional<std::filesystem::path>& texture) {
    Slot& slot = require_slot(handle);
    if (slot.render_component.has_value()) {
        throw EngineError("entity already has its singleton render component");
    }
    Material material{color};
    material.validate();
    RenderComponent component;
    component.kind = kind;
    component.mesh = primitive_mesh(kind);
    component.material = material;
    if (texture.has_value()) {
        component.texture = texture_cache_.load(*texture);
    }
    slot.render_component = std::move(component);
}

void World::add_model_renderer(const EntityHandle handle,
                               const std::filesystem::path& path,
                               const Color color) {
    Slot& slot = require_slot(handle);
    if (slot.render_component.has_value()) {
        throw EngineError("entity already has its singleton render component");
    }
    Material material{color};
    material.validate();
    RenderComponent component;
    component.kind = RenderKind::Model;
    component.model = model_cache_.load(path);
    component.material = material;
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
                                const float intensity) {
    Slot& slot = require_slot(handle);
    if (slot.light_component.has_value()) {
        throw EngineError("entity already has its singleton light component");
    }
    LightComponent component{kind, color, intensity};
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
    world_.destroy_entity(handle);
}

void Scene::clear() noexcept {
    world_.clear();
    debug_lines_.clear();
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
    world_.set_entity_enabled(handle, enabled);
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
    world_.set_local_transform(handle, transform);
}

Transform Scene::world_transform(const EntityHandle handle) const {
    return world_.world_transform(handle);
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
    world_.set_entity_parent(child, parent, keep_world);
}

void Scene::add_primitive_renderer(
    const EntityHandle handle,
    const RenderKind kind,
    const Color color,
    const std::optional<std::filesystem::path>& texture) {
    world_.add_primitive_renderer(handle, kind, color, texture);
}

void Scene::add_model_renderer(const EntityHandle handle,
                               const std::filesystem::path& path,
                               const Color color) {
    world_.add_model_renderer(handle, path, color);
}

bool Scene::has_render_component(const EntityHandle handle) const {
    return world_.has_render_component(handle);
}

const RenderComponent& Scene::render_component(const EntityHandle handle) const {
    return world_.render_component(handle);
}

void Scene::set_render_color(const EntityHandle handle, const Color color) {
    world_.set_render_color(handle, color);
}

void Scene::set_render_lit(const EntityHandle handle, const bool lit) {
    world_.set_render_lit(handle, lit);
}

void Scene::remove_render_component(const EntityHandle handle) {
    world_.remove_render_component(handle);
}

void Scene::add_light_component(const EntityHandle handle,
                                const LightKind kind,
                                const Color color,
                                const float intensity) {
    world_.add_light_component(handle, kind, color, intensity);
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

void Scene::remove_light_component(const EntityHandle handle) {
    world_.remove_light_component(handle);
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

Vec3 Scene::physics_gravity() const noexcept {
    return physics_ ? physics_->gravity() : Vec3{0.0F, -9.81F, 0.0F};
}

void Scene::set_physics_gravity(const Vec3 gravity) {
    physics().set_gravity(gravity);
}

void Scene::step_physics(const float delta_seconds) {
    if (physics_) {
        physics_->step(delta_seconds);
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
