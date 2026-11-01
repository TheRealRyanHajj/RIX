#include "easy3d/scene.hpp"

#include <atomic>
#include <limits>
#include <sstream>
#include <utility>

namespace easy3d {
namespace {

std::atomic_uint64_t next_world_id{1};

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
    ++entity_count_;
    return handle_for(index);
}

void World::destroy_entity(const EntityHandle handle) {
    Slot& slot = require_slot(handle);
    slot.alive = false;
    slot.enabled = false;
    slot.visible = false;
    slot.name.clear();
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

void World::validate_name(const std::string_view name) {
    if (name.empty()) {
        throw std::invalid_argument("entity name must not be empty");
    }
}

void World::advance_generation(Slot& slot) noexcept {
    ++slot.generation;
    if (slot.generation == 0) {
        slot.generation = 1;
    }
}

Scene::Scene(std::string name) : name_(std::move(name)) {
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
