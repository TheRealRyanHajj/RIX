#pragma once

#include "easy3d/core.hpp"

#include <cstddef>
#include <cstdint>
#include <limits>
#include <string>
#include <string_view>
#include <vector>

namespace easy3d {

struct EntityHandle final {
    static constexpr std::uint32_t invalid_index = std::numeric_limits<std::uint32_t>::max();

    std::uint64_t world_id{0};
    std::uint32_t index{invalid_index};
    std::uint32_t generation{0};

    [[nodiscard]] bool valid() const noexcept;
    [[nodiscard]] std::uint64_t id() const noexcept;

    friend bool operator==(const EntityHandle&, const EntityHandle&) = default;
};

class InvalidEntityError : public EngineError {
public:
    using EngineError::EngineError;
};

class World final {
public:
    World();

    World(const World&) = delete;
    World& operator=(const World&) = delete;
    World(World&&) = delete;
    World& operator=(World&&) = delete;
    ~World() = default;

    [[nodiscard]] EntityHandle create_entity(std::string name = "Entity");
    void destroy_entity(EntityHandle handle);
    void clear() noexcept;

    [[nodiscard]] bool is_alive(EntityHandle handle) const noexcept;
    [[nodiscard]] std::size_t entity_count() const noexcept;
    [[nodiscard]] std::uint64_t id() const noexcept;
    [[nodiscard]] std::vector<EntityHandle> entity_handles() const;

    [[nodiscard]] const std::string& entity_name(EntityHandle handle) const;
    void set_entity_name(EntityHandle handle, std::string name);
    [[nodiscard]] bool entity_enabled(EntityHandle handle) const;
    void set_entity_enabled(EntityHandle handle, bool enabled);
    [[nodiscard]] bool entity_visible(EntityHandle handle) const;
    void set_entity_visible(EntityHandle handle, bool visible);

private:
    struct Slot final {
        std::uint32_t generation{1};
        bool alive{false};
        bool enabled{true};
        bool visible{true};
        std::string name;
    };

    [[nodiscard]] Slot& require_slot(EntityHandle handle);
    [[nodiscard]] const Slot& require_slot(EntityHandle handle) const;
    [[nodiscard]] EntityHandle handle_for(std::uint32_t index) const noexcept;
    static void validate_name(std::string_view name);
    static void advance_generation(Slot& slot) noexcept;

    std::uint64_t id_;
    std::size_t entity_count_{0};
    std::vector<Slot> slots_;
    std::vector<std::uint32_t> free_indices_;
};

class Scene final {
public:
    explicit Scene(std::string name = "Scene");

    Scene(const Scene&) = delete;
    Scene& operator=(const Scene&) = delete;
    Scene(Scene&&) = delete;
    Scene& operator=(Scene&&) = delete;
    ~Scene() = default;

    [[nodiscard]] const std::string& name() const noexcept;
    void set_name(std::string name);
    [[nodiscard]] bool active() const noexcept;
    void set_active(bool active) noexcept;

    [[nodiscard]] EntityHandle create_entity(std::string name = "Entity");
    void destroy_entity(EntityHandle handle);
    void clear() noexcept;
    [[nodiscard]] bool is_alive(EntityHandle handle) const noexcept;
    [[nodiscard]] std::size_t entity_count() const noexcept;
    [[nodiscard]] std::vector<EntityHandle> entity_handles() const;

    [[nodiscard]] const std::string& entity_name(EntityHandle handle) const;
    void set_entity_name(EntityHandle handle, std::string name);
    [[nodiscard]] bool entity_enabled(EntityHandle handle) const;
    void set_entity_enabled(EntityHandle handle, bool enabled);
    [[nodiscard]] bool entity_visible(EntityHandle handle) const;
    void set_entity_visible(EntityHandle handle, bool visible);

    [[nodiscard]] World& world() noexcept;
    [[nodiscard]] const World& world() const noexcept;

private:
    static void validate_name(std::string_view name);

    std::string name_;
    bool active_{false};
    World world_;
};

} // namespace easy3d
