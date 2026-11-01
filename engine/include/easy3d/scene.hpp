#pragma once

#include "easy3d/core.hpp"
#include "easy3d/math.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
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

    [[nodiscard]] Transform local_transform(EntityHandle handle) const;
    void set_local_transform(EntityHandle handle, Transform transform);
    [[nodiscard]] Transform world_transform(EntityHandle handle) const;
    [[nodiscard]] std::optional<EntityHandle> entity_parent(EntityHandle handle) const;
    [[nodiscard]] std::vector<EntityHandle> entity_children(EntityHandle handle) const;
    void set_entity_parent(EntityHandle child,
                           std::optional<EntityHandle> parent,
                           bool keep_world = false);

private:
    struct Slot final {
        std::uint32_t generation{1};
        bool alive{false};
        bool enabled{true};
        bool visible{true};
        std::string name;
        Transform local_transform{};
        std::optional<std::uint32_t> parent_index;
        std::vector<std::uint32_t> child_indices;
        mutable std::array<float, 16> cached_world_matrix{
            1.0F, 0.0F, 0.0F, 0.0F,
            0.0F, 1.0F, 0.0F, 0.0F,
            0.0F, 0.0F, 1.0F, 0.0F,
            0.0F, 0.0F, 0.0F, 1.0F};
        mutable bool transform_dirty{true};
    };

    [[nodiscard]] Slot& require_slot(EntityHandle handle);
    [[nodiscard]] const Slot& require_slot(EntityHandle handle) const;
    [[nodiscard]] EntityHandle handle_for(std::uint32_t index) const noexcept;
    [[nodiscard]] const std::array<float, 16>& world_matrix(std::uint32_t index) const;
    void mark_transform_dirty(std::uint32_t index) noexcept;
    void detach_from_parent(std::uint32_t index) noexcept;
    void set_local_from_matrix(std::uint32_t index, const std::array<float, 16>& matrix);
    static void validate_name(std::string_view name);
    static void validate_transform(const Transform& transform);
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
    [[nodiscard]] Transform local_transform(EntityHandle handle) const;
    void set_local_transform(EntityHandle handle, Transform transform);
    [[nodiscard]] Transform world_transform(EntityHandle handle) const;
    [[nodiscard]] std::optional<EntityHandle> entity_parent(EntityHandle handle) const;
    [[nodiscard]] std::vector<EntityHandle> entity_children(EntityHandle handle) const;
    void set_entity_parent(EntityHandle child,
                           std::optional<EntityHandle> parent,
                           bool keep_world = false);

    [[nodiscard]] World& world() noexcept;
    [[nodiscard]] const World& world() const noexcept;

private:
    static void validate_name(std::string_view name);

    std::string name_;
    bool active_{false};
    World world_;
};

} // namespace easy3d
