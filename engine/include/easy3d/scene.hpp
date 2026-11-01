#pragma once

#include "easy3d/core.hpp"
#include "easy3d/assets.hpp"
#include "easy3d/math.hpp"
#include "easy3d/physics.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
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

enum class RenderKind {
    Cube,
    Plane,
    Sphere,
    Model,
};

struct RenderComponent final {
    RenderKind kind{RenderKind::Cube};
    std::shared_ptr<const MeshData> mesh;
    std::shared_ptr<const ModelData> model;
    std::shared_ptr<const ImageData> texture;
    Material material{};
    TextureSampler sampler{};
};

enum class LightKind {
    Ambient,
    Directional,
};

struct LightComponent final {
    LightKind kind{LightKind::Directional};
    Color color{};
    float intensity{1.0F};

    void validate() const;
};

struct ColliderComponent final {
    PhysicsShape shape{PhysicsShape::Box};
    Vec3 half_extents{0.5F, 0.5F, 0.5F};
    float radius{0.5F};
    bool trigger{false};
    CollisionLayer layer{CollisionLayer::Dynamic};
    PhysicsMaterial material{};

    void validate() const;
};

struct RigidBodyComponent final {
    PhysicsMotionType motion_type{PhysicsMotionType::Dynamic};
    float mass{1.0F};
    bool use_gravity{true};

    void validate() const;
};

struct ScenePhysicsQueryHit final {
    EntityHandle entity;
    Vec3 point{};
    Vec3 normal{};
    float distance{0.0F};
    float fraction{0.0F};
};

struct ScenePhysicsContactEvent final {
    PhysicsContactPhase phase{PhysicsContactPhase::Enter};
    EntityHandle first;
    EntityHandle second;
    Vec3 point{};
    Vec3 normal{};
    bool trigger{false};
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
    void add_primitive_renderer(EntityHandle handle,
                                RenderKind kind,
                                Color color = {},
                                const std::optional<std::filesystem::path>& texture = std::nullopt);
    void add_model_renderer(EntityHandle handle,
                            const std::filesystem::path& path,
                            Color color = {});
    [[nodiscard]] bool has_render_component(EntityHandle handle) const;
    [[nodiscard]] const RenderComponent& render_component(EntityHandle handle) const;
    void set_render_color(EntityHandle handle, Color color);
    void set_render_lit(EntityHandle handle, bool lit);
    void remove_render_component(EntityHandle handle);
    void add_light_component(EntityHandle handle,
                             LightKind kind,
                             Color color = {},
                             float intensity = 1.0F);
    [[nodiscard]] bool has_light_component(EntityHandle handle) const;
    [[nodiscard]] const LightComponent& light_component(EntityHandle handle) const;
    void set_light_color(EntityHandle handle, Color color);
    void set_light_intensity(EntityHandle handle, float intensity);
    void remove_light_component(EntityHandle handle);

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
        std::optional<RenderComponent> render_component;
        std::optional<LightComponent> light_component;
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
    TextureCache texture_cache_;
    ModelCache model_cache_;
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
    void add_primitive_renderer(EntityHandle handle,
                                RenderKind kind,
                                Color color = {},
                                const std::optional<std::filesystem::path>& texture = std::nullopt);
    void add_model_renderer(EntityHandle handle,
                            const std::filesystem::path& path,
                            Color color = {});
    [[nodiscard]] bool has_render_component(EntityHandle handle) const;
    [[nodiscard]] const RenderComponent& render_component(EntityHandle handle) const;
    void set_render_color(EntityHandle handle, Color color);
    void set_render_lit(EntityHandle handle, bool lit);
    void remove_render_component(EntityHandle handle);
    void add_light_component(EntityHandle handle,
                             LightKind kind,
                             Color color = {},
                             float intensity = 1.0F);
    [[nodiscard]] bool has_light_component(EntityHandle handle) const;
    [[nodiscard]] const LightComponent& light_component(EntityHandle handle) const;
    void set_light_color(EntityHandle handle, Color color);
    void set_light_intensity(EntityHandle handle, float intensity);
    void remove_light_component(EntityHandle handle);

    void add_collider_component(EntityHandle handle, ColliderComponent component);
    [[nodiscard]] bool has_collider_component(EntityHandle handle) const;
    [[nodiscard]] const ColliderComponent& collider_component(EntityHandle handle) const;
    void remove_collider_component(EntityHandle handle);
    void add_rigid_body_component(EntityHandle handle, RigidBodyComponent component);
    [[nodiscard]] bool has_rigid_body_component(EntityHandle handle) const;
    [[nodiscard]] const RigidBodyComponent& rigid_body_component(EntityHandle handle) const;
    void remove_rigid_body_component(EntityHandle handle);
    [[nodiscard]] Vec3 rigid_body_linear_velocity(EntityHandle handle) const;
    void set_rigid_body_linear_velocity(EntityHandle handle, Vec3 velocity);
    void add_rigid_body_force(EntityHandle handle, Vec3 force);
    void add_rigid_body_impulse(EntityHandle handle, Vec3 impulse);
    void teleport_rigid_body(EntityHandle handle, Vec3 position, Quat rotation);
    [[nodiscard]] std::vector<ScenePhysicsQueryHit> raycast_all(
        Vec3 origin,
        Vec3 direction,
        float max_distance,
        std::uint8_t layer_mask = 0x0fU,
        bool include_triggers = true,
        std::optional<EntityHandle> excluded = std::nullopt) const;
    [[nodiscard]] std::vector<ScenePhysicsQueryHit> overlap_sphere(
        Vec3 center,
        float radius,
        std::uint8_t layer_mask = 0x0fU,
        bool include_triggers = true,
        std::optional<EntityHandle> excluded = std::nullopt) const;
    [[nodiscard]] std::vector<ScenePhysicsQueryHit> overlap_box(
        Vec3 center,
        Vec3 half_extents,
        Quat rotation = {},
        std::uint8_t layer_mask = 0x0fU,
        bool include_triggers = true,
        std::optional<EntityHandle> excluded = std::nullopt) const;
    [[nodiscard]] std::vector<ScenePhysicsQueryHit> sphere_cast_all(
        Vec3 origin,
        float radius,
        Vec3 direction,
        float max_distance,
        std::uint8_t layer_mask = 0x0fU,
        bool include_triggers = true,
        std::optional<EntityHandle> excluded = std::nullopt) const;
    [[nodiscard]] std::vector<ScenePhysicsQueryHit> capsule_cast_all(
        Vec3 origin,
        float radius,
        float height,
        Quat rotation,
        Vec3 direction,
        float max_distance,
        std::uint8_t layer_mask = 0x0fU,
        bool include_triggers = true,
        std::optional<EntityHandle> excluded = std::nullopt) const;
    [[nodiscard]] std::vector<ScenePhysicsContactEvent> drain_physics_events();

    [[nodiscard]] const Camera& camera() const noexcept;
    void set_camera(Camera camera);
    void add_debug_line(DebugLine line);
    void clear_debug_lines() noexcept;
    [[nodiscard]] const std::vector<DebugLine>& debug_lines() const noexcept;

    [[nodiscard]] Vec3 physics_gravity() const noexcept;
    void set_physics_gravity(Vec3 gravity);
    void step_physics(float delta_seconds);
    [[nodiscard]] std::uint64_t physics_step_count() const noexcept;
    [[nodiscard]] PhysicsWorld& physics();
    [[nodiscard]] const PhysicsWorld* physics_if_initialized() const noexcept;

    [[nodiscard]] World& world() noexcept;
    [[nodiscard]] const World& world() const noexcept;

private:
    struct PhysicsEntity final {
        ColliderComponent collider;
        std::optional<RigidBodyComponent> rigid_body;
        PhysicsBodyHandle body;
    };

    [[nodiscard]] PhysicsEntity& require_physics_entity(EntityHandle handle);
    [[nodiscard]] const PhysicsEntity& require_physics_entity(EntityHandle handle) const;
    [[nodiscard]] PhysicsBodyHandle create_physics_body(EntityHandle handle,
                                                        const PhysicsEntity& component);
    void replace_physics_body(EntityHandle handle, PhysicsEntity& component);
    [[nodiscard]] EntityHandle handle_from_id(std::uint64_t id) const noexcept;
    static void validate_name(std::string_view name);

    std::string name_;
    bool active_{false};
    World world_;
    Camera camera_;
    std::vector<DebugLine> debug_lines_;
    std::unique_ptr<PhysicsWorld> physics_;
    std::unordered_map<std::uint64_t, PhysicsEntity> physics_entities_;
};

} // namespace easy3d
