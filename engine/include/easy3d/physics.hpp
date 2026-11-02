#pragma once

#include "easy3d/core.hpp"
#include "easy3d/math.hpp"

#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <vector>

namespace easy3d {

class PhysicsError : public EngineError {
public:
    using EngineError::EngineError;
};

enum class CollisionLayer : std::uint8_t {
    Static = 0,
    Dynamic = 1,
    Sensor = 2,
    Character = 3,
};

enum class PhysicsMotionType : std::uint8_t {
    Static,
    Kinematic,
    Dynamic,
};

enum class PhysicsShape : std::uint8_t {
    Box,
    Sphere,
    Capsule,
    ConvexHull,
    TriangleMesh,
};

struct PhysicsBodyHandle final {
    static constexpr std::uint32_t invalid_index = std::numeric_limits<std::uint32_t>::max();

    std::uint64_t world_id{0};
    std::uint32_t index{invalid_index};
    std::uint32_t generation{0};

    [[nodiscard]] bool valid() const noexcept;
    [[nodiscard]] std::uint64_t id() const noexcept;

    friend bool operator==(const PhysicsBodyHandle&, const PhysicsBodyHandle&) = default;
};

struct PhysicsCharacterHandle final {
    static constexpr std::uint32_t invalid_index = std::numeric_limits<std::uint32_t>::max();

    std::uint64_t world_id{0};
    std::uint32_t index{invalid_index};
    std::uint32_t generation{0};

    [[nodiscard]] bool valid() const noexcept;
    [[nodiscard]] std::uint64_t id() const noexcept;

    friend bool operator==(const PhysicsCharacterHandle&,
                           const PhysicsCharacterHandle&) = default;
};

struct PhysicsConstraintHandle final {
    static constexpr std::uint32_t invalid_index = std::numeric_limits<std::uint32_t>::max();

    std::uint64_t world_id{0};
    std::uint32_t index{invalid_index};
    std::uint32_t generation{0};

    [[nodiscard]] bool valid() const noexcept;
    [[nodiscard]] std::uint64_t id() const noexcept;

    friend bool operator==(const PhysicsConstraintHandle&,
                           const PhysicsConstraintHandle&) = default;
};

struct PhysicsWorldConfig final {
    std::uint32_t max_bodies{16'384};
    std::uint32_t max_body_pairs{65'536};
    std::uint32_t max_contact_constraints{16'384};
    std::size_t temporary_allocator_bytes{10U * 1024U * 1024U};
};

struct PhysicsMaterial final {
    float friction{0.2F};
    float restitution{0.0F};

    void validate() const;
};

struct PhysicsBodySettings final {
    PhysicsShape shape{PhysicsShape::Box};
    PhysicsMotionType motion_type{PhysicsMotionType::Dynamic};
    CollisionLayer layer{CollisionLayer::Dynamic};
    Vec3 position{};
    Quat rotation{};
    Vec3 half_extents{0.5F, 0.5F, 0.5F};
    float radius{0.5F};
    float height{1.0F};
    std::vector<Vec3> vertices;
    std::vector<std::uint32_t> indices;
    PhysicsMaterial material{};
    float mass{1.0F};
    float gravity_factor{1.0F};
    Vec3 linear_velocity{};
    bool continuous{false};
    std::uint64_t user_data{0};
};

enum class PhysicsConstraintType : std::uint8_t {
    Fixed,
    Distance,
};

struct PhysicsConstraintSettings final {
    PhysicsConstraintType type{PhysicsConstraintType::Fixed};
    PhysicsBodyHandle first;
    PhysicsBodyHandle second;
    Vec3 first_anchor{};
    Vec3 second_anchor{};
    float minimum_distance{-1.0F};
    float maximum_distance{-1.0F};
    bool auto_detect_fixed_point{true};
};

enum class CharacterMotorMode : std::uint8_t {
    FirstPerson,
    ThirdPerson,
};

struct CharacterMotorSettings final {
    CharacterMotorMode mode{CharacterMotorMode::FirstPerson};
    Vec3 position{};
    float radius{0.4F};
    float height{1.8F};
    float speed{5.0F};
    float acceleration{30.0F};
    float air_control{0.25F};
    float jump_speed{5.0F};
    float max_slope_degrees{50.0F};
    float step_height{0.4F};
    std::uint64_t user_data{0};
};

struct CharacterMotorInput final {
    Vec3 movement{};
    float heading_degrees{0.0F};
    bool jump{false};
};

struct CharacterMotorState final {
    Vec3 position{};
    Quat rotation{};
    Vec3 linear_velocity{};
    Vec3 ground_normal{};
    bool grounded{false};
};

struct PhysicsQueryFilter final {
    std::uint8_t layer_mask{0x0fU};
    bool include_sensors{true};
    std::uint64_t excluded_user_data{0};
};

struct PhysicsQueryHit final {
    std::uint64_t user_data{0};
    Vec3 point{};
    Vec3 normal{};
    float distance{0.0F};
    float fraction{0.0F};
};

enum class PhysicsContactPhase : std::uint8_t {
    Enter,
    Stay,
    Exit,
};

struct PhysicsContactEvent final {
    PhysicsContactPhase phase{PhysicsContactPhase::Enter};
    std::uint64_t first_user_data{0};
    std::uint64_t second_user_data{0};
    Vec3 point{};
    Vec3 normal{};
    bool trigger{false};
};

class PhysicsWorld final {
public:
    explicit PhysicsWorld(PhysicsWorldConfig config = {});

    PhysicsWorld(const PhysicsWorld&) = delete;
    PhysicsWorld& operator=(const PhysicsWorld&) = delete;
    PhysicsWorld(PhysicsWorld&&) = delete;
    PhysicsWorld& operator=(PhysicsWorld&&) = delete;
    ~PhysicsWorld();

    [[nodiscard]] const PhysicsWorldConfig& config() const noexcept;
    [[nodiscard]] std::uint64_t id() const noexcept;
    [[nodiscard]] Vec3 gravity() const noexcept;
    void set_gravity(Vec3 gravity);

    [[nodiscard]] PhysicsBodyHandle create_body(const PhysicsBodySettings& settings);
    void destroy_body(PhysicsBodyHandle handle);
    void clear() noexcept;
    [[nodiscard]] bool is_alive(PhysicsBodyHandle handle) const noexcept;
    [[nodiscard]] std::size_t body_count() const noexcept;

    [[nodiscard]] PhysicsCharacterHandle create_character(
        const CharacterMotorSettings& settings);
    void destroy_character(PhysicsCharacterHandle handle);
    [[nodiscard]] bool is_alive(PhysicsCharacterHandle handle) const noexcept;
    [[nodiscard]] std::size_t character_count() const noexcept;
    void set_character_input(PhysicsCharacterHandle handle, CharacterMotorInput input);
    void set_character_sequenced_input(PhysicsCharacterHandle handle,
                                        std::uint64_t sequence,
                                        CharacterMotorInput input);
    [[nodiscard]] std::uint64_t character_input_sequence(
        PhysicsCharacterHandle handle) const;
    [[nodiscard]] CharacterMotorState character_state(PhysicsCharacterHandle handle) const;
    void correct_character(PhysicsCharacterHandle handle,
                           Vec3 position,
                           Quat rotation,
                           Vec3 linear_velocity);
    void replay_character_input(PhysicsCharacterHandle handle,
                                CharacterMotorInput input,
                                float delta_seconds);
    void teleport_character(PhysicsCharacterHandle handle, Vec3 position, float heading_degrees);

    [[nodiscard]] PhysicsConstraintHandle create_constraint(
        const PhysicsConstraintSettings& settings);
    void destroy_constraint(PhysicsConstraintHandle handle);
    [[nodiscard]] bool is_alive(PhysicsConstraintHandle handle) const noexcept;
    [[nodiscard]] std::size_t constraint_count() const noexcept;

    [[nodiscard]] Vec3 body_position(PhysicsBodyHandle handle) const;
    [[nodiscard]] Quat body_rotation(PhysicsBodyHandle handle) const;
    [[nodiscard]] Vec3 body_linear_velocity(PhysicsBodyHandle handle) const;
    void set_body_linear_velocity(PhysicsBodyHandle handle, Vec3 velocity);
    void set_body_transform(PhysicsBodyHandle handle, Vec3 position, Quat rotation);
    void add_force(PhysicsBodyHandle handle, Vec3 force);
    void add_impulse(PhysicsBodyHandle handle, Vec3 impulse);

    [[nodiscard]] std::vector<PhysicsQueryHit> raycast_all(
        Vec3 origin,
        Vec3 direction,
        float max_distance,
        PhysicsQueryFilter filter = {}) const;
    [[nodiscard]] std::vector<PhysicsQueryHit> overlap_sphere(
        Vec3 center,
        float radius,
        PhysicsQueryFilter filter = {}) const;
    [[nodiscard]] std::vector<PhysicsQueryHit> overlap_box(
        Vec3 center,
        Vec3 half_extents,
        Quat rotation = {},
        PhysicsQueryFilter filter = {}) const;
    [[nodiscard]] std::vector<PhysicsQueryHit> sphere_cast_all(
        Vec3 origin,
        float radius,
        Vec3 direction,
        float max_distance,
        PhysicsQueryFilter filter = {}) const;
    [[nodiscard]] std::vector<PhysicsQueryHit> capsule_cast_all(
        Vec3 origin,
        float radius,
        float height,
        Quat rotation,
        Vec3 direction,
        float max_distance,
        PhysicsQueryFilter filter = {}) const;
    [[nodiscard]] std::vector<PhysicsContactEvent> drain_contact_events();

    void step(float delta_seconds, std::uint32_t collision_steps = 1);
    [[nodiscard]] std::uint64_t step_count() const noexcept;

    [[nodiscard]] static bool layers_collide(CollisionLayer first,
                                             CollisionLayer second) noexcept;

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace easy3d
