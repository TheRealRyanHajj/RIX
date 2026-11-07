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

struct TextureMaterialSettings final {
    float pixels_per_unit{16.0F};
    TextureFilter filter{TextureFilter::Nearest};
    TextureMode mode{TextureMode::Auto};
    // Atlas rectangles describe a fixed image layout. Keep the dimensions
    // used to create that layout so later transform changes cannot move face
    // rectangles into unrelated parts of the image.
    Vec3 atlas_dimensions{1.0F, 1.0F, 1.0F};
    float normal_strength{1.0F};
    bool hot_reload{true};

    void validate() const;
};

struct RenderComponent final {
    RenderKind kind{RenderKind::Cube};
    std::shared_ptr<const MeshData> mesh;
    std::shared_ptr<const ModelData> model;
    std::shared_ptr<const ImageData> texture;
    std::shared_ptr<const ImageData> normal_map;
    std::shared_ptr<const ImageData> roughness_map;
    std::shared_ptr<const ImageData> metallic_map;
    std::shared_ptr<const ImageData> emissive_map;
    std::shared_ptr<const ImageData> ambient_occlusion_map;
    Material material{};
    TextureSampler sampler{};
    TextureMaterialSettings texture_settings{};
    // Imported models leave this empty so each material can honor glTF's
    // doubleSided flag. An explicit user mutation overrides every part.
    std::optional<CullMode> cull_mode_override;
};

enum class LightKind {
    Ambient,
    Directional,
    Point,
    Spot,
};

struct LightComponent final {
    LightKind kind{LightKind::Directional};
    Color color{};
    float intensity{1.0F};
    float range{10.0F};
    float inner_angle_degrees{30.0F};
    float outer_angle_degrees{45.0F};
    bool casts_shadows{false};
    std::uint16_t shadow_resolution{0};
    float shadow_bias{0.002F};

    void validate() const;
};

enum class SkyboxKind {
    Procedural,
    Panorama,
    Cubemap,
};

struct SkyboxConfig final {
    SkyboxKind kind{SkyboxKind::Procedural};
    Color top{0.18F, 0.45F, 0.82F, 1.0F};
    Color horizon{0.72F, 0.84F, 0.96F, 1.0F};
    Color bottom{0.08F, 0.10F, 0.16F, 1.0F};
    float brightness{1.0F};
    float rotation_degrees{0.0F};
    std::shared_ptr<const ImageData> panorama;
    // +X, -X, +Y, -Y, +Z, -Z.
    std::array<std::shared_ptr<const ImageData>, 6> cubemap{};

    void validate() const;
};

enum class UiElementKind {
    Panel,
    Sprite,
    Text,
    Button,
};

enum class UiAnchor {
    TopLeft,
    Top,
    TopRight,
    Left,
    Center,
    Right,
    BottomLeft,
    Bottom,
    BottomRight,
};

struct UiElement final {
    std::uint64_t id{0};
    UiElementKind kind{UiElementKind::Panel};
    UiAnchor anchor{UiAnchor::TopLeft};
    float x{0.0F};
    float y{0.0F};
    float width{0.0F};
    float height{0.0F};
    Color color{};
    std::shared_ptr<const ImageData> texture;
    std::string text;
    Color text_color{};
    float font_size{24.0F};
    std::int32_t z_index{0};
    bool visible{true};
    bool enabled{true};

    void validate() const;
};

struct ColliderComponent final {
    PhysicsShape shape{PhysicsShape::Box};
    Vec3 half_extents{0.5F, 0.5F, 0.5F};
    float radius{0.5F};
    float height{1.0F};
    std::vector<Vec3> vertices;
    std::vector<std::uint32_t> indices;
    bool trigger{false};
    CollisionLayer layer{CollisionLayer::Dynamic};
    PhysicsMaterial material{};

    void validate() const;
};

struct RigidBodyComponent final {
    PhysicsMotionType motion_type{PhysicsMotionType::Dynamic};
    float mass{1.0F};
    bool use_gravity{true};
    bool continuous{false};

    void validate() const;
};

struct CharacterControllerComponent final {
    CharacterMotorMode mode{CharacterMotorMode::FirstPerson};
    float radius{0.4F};
    float height{1.8F};
    float speed{5.0F};
    float acceleration{30.0F};
    float air_acceleration{8.0F};
    float ground_friction{6.0F};
    float stop_speed{1.0F};
    float air_speed_cap{1.5F};
    float horizontal_speed_limit{0.0F};
    float jump_speed{5.0F};
    float max_slope_degrees{50.0F};
    float step_height{0.4F};
    float sprint_multiplier{1.6F};
    float crouch_height{1.2F};
    float crouch_speed_multiplier{0.5F};

    void validate() const;
};

struct EntityMotion final {
    Vec3 velocity{};
    Vec3 acceleration{};
    // Public angular units are degrees per second and degrees per second squared.
    Vec3 angular_velocity{};
    Vec3 angular_acceleration{};
    float character_yaw_offset_degrees{0.0F};
    bool paused{false};
    Vec3 paused_velocity{};
    Vec3 paused_angular_velocity{};
    Transform paused_world_transform{};
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
    void set_world_transform(EntityHandle handle, Transform transform);
    [[nodiscard]] EntityMotion& motion(EntityHandle handle);
    [[nodiscard]] const EntityMotion& motion(EntityHandle handle) const;
    [[nodiscard]] std::optional<EntityHandle> entity_parent(EntityHandle handle) const;
    [[nodiscard]] std::vector<EntityHandle> entity_children(EntityHandle handle) const;
    void set_entity_parent(EntityHandle child,
                           std::optional<EntityHandle> parent,
                           bool keep_world = false);
    void add_primitive_renderer(EntityHandle handle,
                                RenderKind kind,
                                Color color = {},
                                const std::optional<std::filesystem::path>& texture = std::nullopt,
                                TextureMaterialSettings texture_settings = {},
                                const std::optional<std::filesystem::path>& normal_map = std::nullopt,
                                const std::optional<std::filesystem::path>& roughness_map = std::nullopt,
                                const std::optional<std::filesystem::path>& metallic_map = std::nullopt,
                                const std::optional<std::filesystem::path>& emissive_map = std::nullopt,
                                const std::optional<std::filesystem::path>& ambient_occlusion_map = std::nullopt,
                                CullMode cull_mode = CullMode::Back);
    void add_model_renderer(EntityHandle handle,
                            const std::filesystem::path& path,
                            Color color = {},
                            std::optional<CullMode> cull_mode_override = std::nullopt);
    [[nodiscard]] bool has_render_component(EntityHandle handle) const;
    [[nodiscard]] const RenderComponent& render_component(EntityHandle handle) const;
    [[nodiscard]] std::size_t poll_texture_changes() const noexcept;
    void set_render_color(EntityHandle handle, Color color);
    void set_render_lit(EntityHandle handle, bool lit);
    void set_render_cull_mode(EntityHandle handle, CullMode cull_mode);
    void set_render_surface(EntityHandle handle,
                            float metallic,
                            float roughness,
                            float emission,
                            bool casts_shadows,
                            bool receives_shadows);
    void set_render_texture(EntityHandle handle,
                            const std::optional<std::filesystem::path>& texture,
                            TextureMaterialSettings texture_settings,
                            const std::optional<std::filesystem::path>& normal_map,
                            const std::optional<std::filesystem::path>& roughness_map,
                            const std::optional<std::filesystem::path>& metallic_map,
                            const std::optional<std::filesystem::path>& emissive_map,
                            const std::optional<std::filesystem::path>& ambient_occlusion_map);
    void set_render_image(EntityHandle handle,
                          std::shared_ptr<const ImageData> texture,
                          TextureMaterialSettings texture_settings = {});
    void remove_render_component(EntityHandle handle);
    void add_light_component(EntityHandle handle,
                             LightKind kind,
                             Color color = {},
                             float intensity = 1.0F,
                             float range = 10.0F,
                             float inner_angle_degrees = 30.0F,
                             float outer_angle_degrees = 45.0F,
                             bool casts_shadows = false,
                             std::uint16_t shadow_resolution = 0,
                             float shadow_bias = 0.002F);
    [[nodiscard]] bool has_light_component(EntityHandle handle) const;
    [[nodiscard]] const LightComponent& light_component(EntityHandle handle) const;
    void set_light_color(EntityHandle handle, Color color);
    void set_light_intensity(EntityHandle handle, float intensity);
    void set_light_properties(EntityHandle handle,
                              float range,
                              float inner_angle_degrees,
                              float outer_angle_degrees,
                              bool casts_shadows,
                              std::uint16_t shadow_resolution,
                              float shadow_bias);
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
        EntityMotion motion{};
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
    mutable TextureCache texture_cache_;
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
    [[nodiscard]] Vec3 entity_velocity(EntityHandle handle) const;
    void set_entity_velocity(EntityHandle handle, Vec3 velocity);
    [[nodiscard]] Vec3 entity_acceleration(EntityHandle handle) const;
    void set_entity_acceleration(EntityHandle handle, Vec3 acceleration);
    [[nodiscard]] Vec3 entity_angular_velocity(EntityHandle handle) const;
    void set_entity_angular_velocity(EntityHandle handle, Vec3 degrees_per_second);
    [[nodiscard]] Vec3 entity_angular_acceleration(EntityHandle handle) const;
    void set_entity_angular_acceleration(EntityHandle handle,
                                         Vec3 degrees_per_second_squared);
    [[nodiscard]] float entity_character_yaw_offset(EntityHandle handle) const;
    void reset_entity_motion(EntityHandle handle);
    [[nodiscard]] std::optional<EntityHandle> entity_parent(EntityHandle handle) const;
    [[nodiscard]] std::vector<EntityHandle> entity_children(EntityHandle handle) const;
    void set_entity_parent(EntityHandle child,
                           std::optional<EntityHandle> parent,
                           bool keep_world = false);
    void add_primitive_renderer(EntityHandle handle,
                                RenderKind kind,
                                Color color = {},
                                const std::optional<std::filesystem::path>& texture = std::nullopt,
                                TextureMaterialSettings texture_settings = {},
                                const std::optional<std::filesystem::path>& normal_map = std::nullopt,
                                const std::optional<std::filesystem::path>& roughness_map = std::nullopt,
                                const std::optional<std::filesystem::path>& metallic_map = std::nullopt,
                                const std::optional<std::filesystem::path>& emissive_map = std::nullopt,
                                const std::optional<std::filesystem::path>& ambient_occlusion_map = std::nullopt,
                                CullMode cull_mode = CullMode::Back);
    void add_model_renderer(EntityHandle handle,
                            const std::filesystem::path& path,
                            Color color = {},
                            std::optional<CullMode> cull_mode_override = std::nullopt);
    [[nodiscard]] bool has_render_component(EntityHandle handle) const;
    [[nodiscard]] const RenderComponent& render_component(EntityHandle handle) const;
    [[nodiscard]] std::size_t poll_texture_changes() const noexcept;
    [[nodiscard]] const std::optional<SkyboxConfig>& skybox() const noexcept;
    void set_procedural_skybox(Color top,
                               Color horizon,
                               Color bottom,
                               float brightness = 1.0F,
                               float rotation_degrees = 0.0F);
    void set_panorama_skybox(const std::filesystem::path& path,
                             float brightness = 1.0F,
                             float rotation_degrees = 0.0F);
    void set_cubemap_skybox(const std::array<std::filesystem::path, 6>& paths,
                            float brightness = 1.0F,
                            float rotation_degrees = 0.0F);
    void clear_skybox() noexcept;
    void set_render_color(EntityHandle handle, Color color);
    void set_render_lit(EntityHandle handle, bool lit);
    void set_render_cull_mode(EntityHandle handle, CullMode cull_mode);
    void set_render_surface(EntityHandle handle,
                            float metallic,
                            float roughness,
                            float emission,
                            bool casts_shadows,
                            bool receives_shadows);
    void set_render_texture(EntityHandle handle,
                            const std::optional<std::filesystem::path>& texture,
                            TextureMaterialSettings texture_settings,
                            const std::optional<std::filesystem::path>& normal_map,
                            const std::optional<std::filesystem::path>& roughness_map,
                            const std::optional<std::filesystem::path>& metallic_map,
                            const std::optional<std::filesystem::path>& emissive_map,
                            const std::optional<std::filesystem::path>& ambient_occlusion_map);
    void set_render_image(EntityHandle handle,
                          std::shared_ptr<const ImageData> texture,
                          TextureMaterialSettings texture_settings = {});
    void remove_render_component(EntityHandle handle);
    void add_light_component(EntityHandle handle,
                             LightKind kind,
                             Color color = {},
                             float intensity = 1.0F,
                             float range = 10.0F,
                             float inner_angle_degrees = 30.0F,
                             float outer_angle_degrees = 45.0F,
                             bool casts_shadows = false,
                             std::uint16_t shadow_resolution = 0,
                             float shadow_bias = 0.002F);
    [[nodiscard]] bool has_light_component(EntityHandle handle) const;
    [[nodiscard]] const LightComponent& light_component(EntityHandle handle) const;
    void set_light_color(EntityHandle handle, Color color);
    void set_light_intensity(EntityHandle handle, float intensity);
    void set_light_properties(EntityHandle handle,
                              float range,
                              float inner_angle_degrees,
                              float outer_angle_degrees,
                              bool casts_shadows,
                              std::uint16_t shadow_resolution,
                              float shadow_bias);
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
    [[nodiscard]] Vec3 rigid_body_angular_velocity(EntityHandle handle) const;
    void set_rigid_body_angular_velocity(EntityHandle handle,
                                         Vec3 degrees_per_second);
    void add_rigid_body_force(EntityHandle handle, Vec3 force);
    void add_rigid_body_impulse(EntityHandle handle, Vec3 impulse);
    void teleport_rigid_body(EntityHandle handle, Vec3 position, Quat rotation);
    void add_character_controller_component(EntityHandle handle,
                                            CharacterControllerComponent component);
    [[nodiscard]] bool has_character_controller_component(EntityHandle handle) const;
    [[nodiscard]] const CharacterControllerComponent& character_controller_component(
        EntityHandle handle) const;
    void remove_character_controller_component(EntityHandle handle);
    void set_character_input(EntityHandle handle,
                             Vec3 movement,
                             float heading_degrees,
                             bool jump,
                             bool sprint,
                             bool crouch);
    void set_character_sequenced_input(EntityHandle handle,
                                       std::uint64_t sequence,
                                       Vec3 movement,
                                       float heading_degrees,
                                       bool jump,
                                       bool sprint,
                                       bool crouch);
    [[nodiscard]] std::uint64_t character_input_sequence(EntityHandle handle) const;
    [[nodiscard]] CharacterMotorState character_state(EntityHandle handle) const;
    void correct_character(EntityHandle handle,
                           Vec3 position,
                           Quat rotation,
                           Vec3 linear_velocity);
    void replay_character_input(EntityHandle handle,
                                Vec3 movement,
                                float heading_degrees,
                                bool jump,
                                bool sprint,
                                bool crouch,
                                float delta_seconds);
    void set_character_linear_velocity(EntityHandle handle, Vec3 velocity);
    void teleport_character(EntityHandle handle, Vec3 position, float heading_degrees);
    [[nodiscard]] PhysicsConstraintHandle add_fixed_constraint(EntityHandle first,
                                                               EntityHandle second);
    [[nodiscard]] PhysicsConstraintHandle add_distance_constraint(
        EntityHandle first,
        EntityHandle second,
        Vec3 first_anchor,
        Vec3 second_anchor,
        float minimum_distance = -1.0F,
        float maximum_distance = -1.0F);
    void remove_constraint(PhysicsConstraintHandle handle);
    [[nodiscard]] bool has_constraint(PhysicsConstraintHandle handle) const noexcept;
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
    [[nodiscard]] std::uint64_t add_ui_element(
        UiElement element,
        const std::optional<std::filesystem::path>& texture = std::nullopt);
    [[nodiscard]] const UiElement& ui_element(std::uint64_t id) const;
    void update_ui_element(std::uint64_t id, UiElement element);
    void set_ui_image(std::uint64_t id, std::shared_ptr<const ImageData> texture);
    void remove_ui_element(std::uint64_t id);
    void clear_ui() noexcept;
    [[nodiscard]] const std::vector<UiElement>& ui_elements() const noexcept;

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

    struct CharacterEntity final {
        CharacterControllerComponent component;
        PhysicsCharacterHandle character;
    };

    struct SceneConstraint final {
        PhysicsConstraintHandle constraint;
        EntityHandle first;
        EntityHandle second;
    };

    [[nodiscard]] PhysicsEntity& require_physics_entity(EntityHandle handle);
    [[nodiscard]] const PhysicsEntity& require_physics_entity(EntityHandle handle) const;
    [[nodiscard]] PhysicsBodyHandle create_physics_body(EntityHandle handle,
                                                        const PhysicsEntity& component);
    [[nodiscard]] CharacterEntity& require_character_entity(EntityHandle handle);
    [[nodiscard]] const CharacterEntity& require_character_entity(EntityHandle handle) const;
    void replace_physics_body(EntityHandle handle, PhysicsEntity& component);
    void remove_constraints_for(EntityHandle handle) noexcept;
    [[nodiscard]] EntityHandle handle_from_id(std::uint64_t id) const noexcept;
    static void validate_name(std::string_view name);

    std::string name_;
    bool active_{false};
    World world_;
    Camera camera_;
    std::vector<DebugLine> debug_lines_;
    std::vector<UiElement> ui_elements_;
    std::uint64_t next_ui_id_{1};
    TextureCache ui_texture_cache_;
    TextureCache sky_texture_cache_;
    std::optional<SkyboxConfig> skybox_{SkyboxConfig{}};
    std::unique_ptr<PhysicsWorld> physics_;
    std::unordered_map<std::uint64_t, PhysicsEntity> physics_entities_;
    std::unordered_map<std::uint64_t, CharacterEntity> character_entities_;
    std::unordered_map<std::uint64_t, SceneConstraint> constraints_;
};

} // namespace easy3d
