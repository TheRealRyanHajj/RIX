#pragma once

#include "easy3d/core.hpp"
#include "easy3d/math.hpp"

#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>

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

struct PhysicsWorldConfig final {
    std::uint32_t max_bodies{16'384};
    std::uint32_t max_body_pairs{65'536};
    std::uint32_t max_contact_constraints{16'384};
    std::size_t temporary_allocator_bytes{10U * 1024U * 1024U};
};

struct PhysicsBodySettings final {
    PhysicsShape shape{PhysicsShape::Box};
    PhysicsMotionType motion_type{PhysicsMotionType::Dynamic};
    CollisionLayer layer{CollisionLayer::Dynamic};
    Vec3 position{};
    Quat rotation{};
    Vec3 half_extents{0.5F, 0.5F, 0.5F};
    float radius{0.5F};
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

    [[nodiscard]] Vec3 body_position(PhysicsBodyHandle handle) const;
    [[nodiscard]] Quat body_rotation(PhysicsBodyHandle handle) const;
    [[nodiscard]] Vec3 body_linear_velocity(PhysicsBodyHandle handle) const;

    void step(float delta_seconds, std::uint32_t collision_steps = 1);
    [[nodiscard]] std::uint64_t step_count() const noexcept;

    [[nodiscard]] static bool layers_collide(CollisionLayer first,
                                             CollisionLayer second) noexcept;

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace easy3d
