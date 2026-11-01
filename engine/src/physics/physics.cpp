#include "easy3d/physics.hpp"

#include <Jolt/Jolt.h>

#include <Jolt/Core/Factory.h>
#include <Jolt/Core/JobSystemSingleThreaded.h>
#include <Jolt/Core/TempAllocator.h>
#include <Jolt/Physics/Body/BodyCreationSettings.h>
#include <Jolt/Physics/Collision/BroadPhase/BroadPhaseLayer.h>
#include <Jolt/Physics/Collision/Shape/BoxShape.h>
#include <Jolt/Physics/Collision/Shape/SphereShape.h>
#include <Jolt/Physics/PhysicsSystem.h>
#include <Jolt/RegisterTypes.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <sstream>
#include <utility>
#include <vector>

namespace easy3d {
namespace {

constexpr JPH::ObjectLayer static_layer = 0;
constexpr JPH::ObjectLayer dynamic_layer = 1;
constexpr JPH::ObjectLayer sensor_layer = 2;
constexpr JPH::ObjectLayer character_layer = 3;
constexpr JPH::ObjectLayer layer_count = 4;

constexpr JPH::BroadPhaseLayer non_moving_broadphase{0};
constexpr JPH::BroadPhaseLayer moving_broadphase{1};
constexpr JPH::uint broadphase_layer_count = 2;
std::atomic_uint64_t next_physics_world_id{1};

[[nodiscard]] bool finite(const Vec3 value) noexcept {
    return std::isfinite(value.x) && std::isfinite(value.y) && std::isfinite(value.z);
}

[[nodiscard]] bool finite(const Quat value) noexcept {
    return std::isfinite(value.w) && std::isfinite(value.x) && std::isfinite(value.y) &&
           std::isfinite(value.z);
}

[[nodiscard]] JPH::ObjectLayer to_jolt(const CollisionLayer layer) noexcept {
    return static_cast<JPH::ObjectLayer>(layer);
}

[[nodiscard]] CollisionLayer from_jolt(const JPH::ObjectLayer layer) noexcept {
    return static_cast<CollisionLayer>(layer);
}

[[nodiscard]] JPH::Vec3 to_jolt(const Vec3 value) noexcept {
    return {value.x, value.y, value.z};
}

[[nodiscard]] JPH::RVec3 to_jolt_position(const Vec3 value) noexcept {
    return {value.x, value.y, value.z};
}

[[nodiscard]] JPH::Quat to_jolt(const Quat value) noexcept {
    return {value.x, value.y, value.z, value.w};
}

[[nodiscard]] Vec3 from_jolt_vec(const JPH::Vec3Arg value) noexcept {
    return {value.GetX(), value.GetY(), value.GetZ()};
}

[[nodiscard]] Vec3 from_jolt_position(const JPH::RVec3Arg value) noexcept {
    return {static_cast<float>(value.GetX()),
            static_cast<float>(value.GetY()),
            static_cast<float>(value.GetZ())};
}

[[nodiscard]] Quat from_jolt(const JPH::QuatArg value) noexcept {
    return {value.GetW(), value.GetX(), value.GetY(), value.GetZ()};
}

[[nodiscard]] JPH::EMotionType to_jolt(const PhysicsMotionType type) noexcept {
    switch (type) {
    case PhysicsMotionType::Static:
        return JPH::EMotionType::Static;
    case PhysicsMotionType::Kinematic:
        return JPH::EMotionType::Kinematic;
    case PhysicsMotionType::Dynamic:
        return JPH::EMotionType::Dynamic;
    }
    return JPH::EMotionType::Static;
}

class JoltRuntime final {
public:
    JoltRuntime() {
        JPH::RegisterDefaultAllocator();
        JPH::Factory::sInstance = new JPH::Factory();
        JPH::RegisterTypes();
    }

    JoltRuntime(const JoltRuntime&) = delete;
    JoltRuntime& operator=(const JoltRuntime&) = delete;

    ~JoltRuntime() {
        JPH::UnregisterTypes();
        delete JPH::Factory::sInstance;
        JPH::Factory::sInstance = nullptr;
    }
};

[[nodiscard]] JoltRuntime& jolt_runtime() {
    static JoltRuntime runtime;
    return runtime;
}

class BroadPhaseLayers final : public JPH::BroadPhaseLayerInterface {
public:
    [[nodiscard]] JPH::uint GetNumBroadPhaseLayers() const override {
        return broadphase_layer_count;
    }

    [[nodiscard]] JPH::BroadPhaseLayer GetBroadPhaseLayer(
        const JPH::ObjectLayer layer) const override {
        return layer == static_layer ? non_moving_broadphase : moving_broadphase;
    }
};

class ObjectVsBroadPhaseFilter final : public JPH::ObjectVsBroadPhaseLayerFilter {
public:
    [[nodiscard]] bool ShouldCollide(const JPH::ObjectLayer layer,
                                     const JPH::BroadPhaseLayer broadphase) const override {
        if (layer == static_layer) {
            return broadphase == moving_broadphase;
        }
        return broadphase == non_moving_broadphase || broadphase == moving_broadphase;
    }
};

class ObjectLayerPairFilter final : public JPH::ObjectLayerPairFilter {
public:
    [[nodiscard]] bool ShouldCollide(const JPH::ObjectLayer first,
                                     const JPH::ObjectLayer second) const override {
        if (first >= layer_count || second >= layer_count) {
            return false;
        }
        return PhysicsWorld::layers_collide(from_jolt(first), from_jolt(second));
    }
};

[[nodiscard]] std::string invalid_handle_message(const PhysicsBodyHandle handle) {
    std::ostringstream message;
    message << "invalid physics body handle (index=" << handle.index
            << ", generation=" << handle.generation << ", world=" << handle.world_id << ')';
    return message.str();
}

void validate_config(const PhysicsWorldConfig& config) {
    if (config.max_bodies == 0 || config.max_body_pairs == 0 ||
        config.max_contact_constraints == 0 || config.temporary_allocator_bytes == 0) {
        throw std::invalid_argument("physics world capacities must be positive");
    }
    if (config.temporary_allocator_bytes > std::numeric_limits<JPH::uint>::max()) {
        throw std::invalid_argument("physics temporary allocator exceeds Jolt's size limit");
    }
}

void validate_settings(const PhysicsBodySettings& settings) {
    if (!finite(settings.position) || !finite(settings.rotation)) {
        throw std::invalid_argument("physics body transform must be finite");
    }
    if (settings.motion_type == PhysicsMotionType::Static &&
        settings.layer != CollisionLayer::Static &&
        settings.layer != CollisionLayer::Sensor) {
        throw std::invalid_argument("static bodies require the static or sensor layer");
    }
    if (settings.motion_type != PhysicsMotionType::Static &&
        settings.layer == CollisionLayer::Static) {
        throw std::invalid_argument("moving bodies cannot use the static layer");
    }
    if (settings.shape == PhysicsShape::Box &&
        (!finite(settings.half_extents) || settings.half_extents.x <= 0.0F ||
         settings.half_extents.y <= 0.0F || settings.half_extents.z <= 0.0F)) {
        throw std::invalid_argument("box half extents must be finite and positive");
    }
    if (settings.shape == PhysicsShape::Sphere &&
        (!std::isfinite(settings.radius) || settings.radius <= 0.0F)) {
        throw std::invalid_argument("sphere radius must be finite and positive");
    }
    settings.material.validate();
    if (!std::isfinite(settings.mass) || settings.mass <= 0.0F) {
        throw std::invalid_argument("physics body mass must be finite and positive");
    }
    if (!std::isfinite(settings.gravity_factor) || settings.gravity_factor < 0.0F) {
        throw std::invalid_argument("physics gravity factor must be finite and non-negative");
    }
    if (!finite(settings.linear_velocity)) {
        throw std::invalid_argument("physics linear velocity must be finite");
    }
}

} // namespace

bool PhysicsBodyHandle::valid() const noexcept {
    return world_id != 0 && index != invalid_index && generation != 0;
}

std::uint64_t PhysicsBodyHandle::id() const noexcept {
    return (static_cast<std::uint64_t>(generation) << 32U) | index;
}

void PhysicsMaterial::validate() const {
    if (!std::isfinite(friction) || friction < 0.0F) {
        throw std::invalid_argument("physics friction must be finite and non-negative");
    }
    if (!std::isfinite(restitution) || restitution < 0.0F || restitution > 1.0F) {
        throw std::invalid_argument("physics restitution must be finite and between 0 and 1");
    }
}

class PhysicsWorld::Impl final {
public:
    struct Slot final {
        JPH::BodyID body_id;
        std::uint32_t generation{1};
        bool alive{false};
        PhysicsMotionType motion_type{PhysicsMotionType::Static};
    };

    explicit Impl(PhysicsWorldConfig world_config)
        : runtime(jolt_runtime()),
          world_id(next_physics_world_id.fetch_add(1, std::memory_order_relaxed)),
          config(std::move(world_config)),
          temporary_allocator(static_cast<JPH::uint>(config.temporary_allocator_bytes)),
          job_system(JPH::cMaxPhysicsJobs) {
        if (world_id == 0) {
            throw PhysicsError("Easy3D exhausted native physics world identifiers");
        }
        physics_system.Init(config.max_bodies,
                            0,
                            config.max_body_pairs,
                            config.max_contact_constraints,
                            broadphase_layers,
                            object_vs_broadphase_filter,
                            object_layer_pair_filter);
        slots.reserve(config.max_bodies);
        free_indices.reserve(config.max_bodies);
    }

    ~Impl() { clear(); }

    [[nodiscard]] Slot& require_slot(const PhysicsBodyHandle handle) {
        if (!is_alive(handle)) {
            throw PhysicsError(invalid_handle_message(handle));
        }
        return slots[handle.index];
    }

    [[nodiscard]] const Slot& require_slot(const PhysicsBodyHandle handle) const {
        if (!is_alive(handle)) {
            throw PhysicsError(invalid_handle_message(handle));
        }
        return slots[handle.index];
    }

    [[nodiscard]] bool is_alive(const PhysicsBodyHandle handle) const noexcept {
        return handle.world_id == world_id && handle.valid() && handle.index < slots.size() &&
               slots[handle.index].alive &&
               slots[handle.index].generation == handle.generation;
    }

    void clear() noexcept {
        JPH::BodyInterface& bodies = physics_system.GetBodyInterface();
        free_indices.clear();
        free_indices.reserve(slots.size());
        for (std::size_t index = 0; index < slots.size(); ++index) {
            Slot& slot = slots[index];
            if (slot.alive) {
                bodies.RemoveBody(slot.body_id);
                bodies.DestroyBody(slot.body_id);
                ++slot.generation;
                if (slot.generation == 0) {
                    slot.generation = 1;
                }
            }
            slot.alive = false;
            free_indices.push_back(static_cast<std::uint32_t>(index));
        }
        body_count = 0;
    }

    JoltRuntime& runtime;
    std::uint64_t world_id;
    PhysicsWorldConfig config;
    BroadPhaseLayers broadphase_layers;
    ObjectVsBroadPhaseFilter object_vs_broadphase_filter;
    ObjectLayerPairFilter object_layer_pair_filter;
    JPH::TempAllocatorImpl temporary_allocator;
    JPH::JobSystemSingleThreaded job_system;
    JPH::PhysicsSystem physics_system;
    std::vector<Slot> slots;
    std::vector<std::uint32_t> free_indices;
    std::size_t body_count{0};
    std::uint64_t steps{0};
};

PhysicsWorld::PhysicsWorld(PhysicsWorldConfig config) {
    validate_config(config);
    impl_ = std::make_unique<Impl>(std::move(config));
}

PhysicsWorld::~PhysicsWorld() = default;

const PhysicsWorldConfig& PhysicsWorld::config() const noexcept {
    return impl_->config;
}

std::uint64_t PhysicsWorld::id() const noexcept {
    return impl_->world_id;
}

Vec3 PhysicsWorld::gravity() const noexcept {
    return from_jolt_vec(impl_->physics_system.GetGravity());
}

void PhysicsWorld::set_gravity(const Vec3 gravity_value) {
    if (!finite(gravity_value)) {
        throw std::invalid_argument("physics gravity must be finite");
    }
    impl_->physics_system.SetGravity(to_jolt(gravity_value));
}

PhysicsBodyHandle PhysicsWorld::create_body(const PhysicsBodySettings& settings) {
    validate_settings(settings);
    if (impl_->body_count >= impl_->config.max_bodies) {
        throw PhysicsError("physics world body capacity exhausted");
    }

    JPH::ShapeRefC shape;
    if (settings.shape == PhysicsShape::Box) {
        JPH::BoxShapeSettings shape_settings(to_jolt(settings.half_extents));
        shape_settings.SetEmbedded();
        JPH::ShapeSettings::ShapeResult result = shape_settings.Create();
        if (result.HasError()) {
            const auto& error = result.GetError();
            throw std::invalid_argument("Jolt rejected box shape: " +
                                        std::string(error.data(), error.size()));
        }
        shape = result.Get();
    } else {
        JPH::SphereShapeSettings shape_settings(settings.radius);
        shape_settings.SetEmbedded();
        JPH::ShapeSettings::ShapeResult result = shape_settings.Create();
        if (result.HasError()) {
            const auto& error = result.GetError();
            throw std::invalid_argument("Jolt rejected sphere shape: " +
                                        std::string(error.data(), error.size()));
        }
        shape = result.Get();
    }

    const Quat normalized_rotation = settings.rotation.normalized();
    JPH::BodyCreationSettings body_settings(shape,
                                            to_jolt_position(settings.position),
                                            to_jolt(normalized_rotation),
                                            to_jolt(settings.motion_type),
                                            to_jolt(settings.layer));
    body_settings.mIsSensor = settings.layer == CollisionLayer::Sensor;
    body_settings.mFriction = settings.material.friction;
    body_settings.mRestitution = settings.material.restitution;
    body_settings.mGravityFactor = settings.gravity_factor;
    body_settings.mLinearVelocity = to_jolt(settings.linear_velocity);
    if (settings.motion_type == PhysicsMotionType::Dynamic) {
        body_settings.mOverrideMassProperties = JPH::EOverrideMassProperties::CalculateInertia;
        body_settings.mMassPropertiesOverride.mMass = settings.mass;
    }
    const JPH::EActivation activation = settings.motion_type == PhysicsMotionType::Static
                                            ? JPH::EActivation::DontActivate
                                            : JPH::EActivation::Activate;
    JPH::BodyInterface& bodies = impl_->physics_system.GetBodyInterface();
    const JPH::BodyID body_id = bodies.CreateAndAddBody(body_settings, activation);
    if (body_id.IsInvalid()) {
        throw PhysicsError("Jolt could not create a physics body");
    }

    std::uint32_t index = 0;
    if (impl_->free_indices.empty()) {
        index = static_cast<std::uint32_t>(impl_->slots.size());
        impl_->slots.emplace_back();
    } else {
        index = impl_->free_indices.back();
        impl_->free_indices.pop_back();
    }
    Impl::Slot& slot = impl_->slots[index];
    slot.body_id = body_id;
    slot.alive = true;
    slot.motion_type = settings.motion_type;
    ++impl_->body_count;
    return PhysicsBodyHandle{impl_->world_id, index, slot.generation};
}

void PhysicsWorld::destroy_body(const PhysicsBodyHandle handle) {
    Impl::Slot& slot = impl_->require_slot(handle);
    JPH::BodyInterface& bodies = impl_->physics_system.GetBodyInterface();
    bodies.RemoveBody(slot.body_id);
    bodies.DestroyBody(slot.body_id);
    slot.alive = false;
    ++slot.generation;
    if (slot.generation == 0) {
        slot.generation = 1;
    }
    impl_->free_indices.push_back(handle.index);
    --impl_->body_count;
}

void PhysicsWorld::clear() noexcept {
    impl_->clear();
}

bool PhysicsWorld::is_alive(const PhysicsBodyHandle handle) const noexcept {
    return impl_->is_alive(handle);
}

std::size_t PhysicsWorld::body_count() const noexcept {
    return impl_->body_count;
}

Vec3 PhysicsWorld::body_position(const PhysicsBodyHandle handle) const {
    const Impl::Slot& slot = impl_->require_slot(handle);
    return from_jolt_position(impl_->physics_system.GetBodyInterface().GetPosition(slot.body_id));
}

Quat PhysicsWorld::body_rotation(const PhysicsBodyHandle handle) const {
    const Impl::Slot& slot = impl_->require_slot(handle);
    return from_jolt(impl_->physics_system.GetBodyInterface().GetRotation(slot.body_id));
}

Vec3 PhysicsWorld::body_linear_velocity(const PhysicsBodyHandle handle) const {
    const Impl::Slot& slot = impl_->require_slot(handle);
    return from_jolt_vec(impl_->physics_system.GetBodyInterface().GetLinearVelocity(slot.body_id));
}

void PhysicsWorld::set_body_linear_velocity(const PhysicsBodyHandle handle,
                                            const Vec3 velocity) {
    const Impl::Slot& slot = impl_->require_slot(handle);
    if (slot.motion_type == PhysicsMotionType::Static) {
        throw PhysicsError("static physics bodies do not have linear velocity");
    }
    if (!finite(velocity)) {
        throw std::invalid_argument("physics linear velocity must be finite");
    }
    impl_->physics_system.GetBodyInterface().SetLinearVelocity(slot.body_id, to_jolt(velocity));
}

void PhysicsWorld::set_body_transform(const PhysicsBodyHandle handle,
                                      const Vec3 position,
                                      const Quat rotation) {
    const Impl::Slot& slot = impl_->require_slot(handle);
    if (!finite(position) || !finite(rotation)) {
        throw std::invalid_argument("physics body transform must be finite");
    }
    impl_->physics_system.GetBodyInterface().SetPositionAndRotation(
        slot.body_id,
        to_jolt_position(position),
        to_jolt(rotation.normalized()),
        slot.motion_type == PhysicsMotionType::Static ? JPH::EActivation::DontActivate
                                                       : JPH::EActivation::Activate);
}

void PhysicsWorld::add_force(const PhysicsBodyHandle handle, const Vec3 force) {
    const Impl::Slot& slot = impl_->require_slot(handle);
    if (slot.motion_type != PhysicsMotionType::Dynamic) {
        throw PhysicsError("forces require a dynamic physics body");
    }
    if (!finite(force)) {
        throw std::invalid_argument("physics force must be finite");
    }
    impl_->physics_system.GetBodyInterface().AddForce(slot.body_id, to_jolt(force));
}

void PhysicsWorld::add_impulse(const PhysicsBodyHandle handle, const Vec3 impulse) {
    const Impl::Slot& slot = impl_->require_slot(handle);
    if (slot.motion_type != PhysicsMotionType::Dynamic) {
        throw PhysicsError("impulses require a dynamic physics body");
    }
    if (!finite(impulse)) {
        throw std::invalid_argument("physics impulse must be finite");
    }
    impl_->physics_system.GetBodyInterface().AddImpulse(slot.body_id, to_jolt(impulse));
}

void PhysicsWorld::step(const float delta_seconds, const std::uint32_t collision_steps) {
    if (!std::isfinite(delta_seconds) || delta_seconds <= 0.0F) {
        throw std::invalid_argument("physics delta must be finite and positive");
    }
    if (collision_steps == 0 || collision_steps > 64) {
        throw std::invalid_argument("physics collision steps must be between 1 and 64");
    }
    const JPH::EPhysicsUpdateError error = impl_->physics_system.Update(
        delta_seconds,
        static_cast<int>(collision_steps),
        &impl_->temporary_allocator,
        &impl_->job_system);
    if (error != JPH::EPhysicsUpdateError::None) {
        std::ostringstream message;
        message << "Jolt physics update reported capacity error bits 0x" << std::hex
                << static_cast<std::uint32_t>(error);
        throw PhysicsError(message.str());
    }
    ++impl_->steps;
}

std::uint64_t PhysicsWorld::step_count() const noexcept {
    return impl_->steps;
}

bool PhysicsWorld::layers_collide(const CollisionLayer first,
                                  const CollisionLayer second) noexcept {
    if (static_cast<std::uint8_t>(first) >= layer_count ||
        static_cast<std::uint8_t>(second) >= layer_count) {
        return false;
    }
    if (first == CollisionLayer::Static && second == CollisionLayer::Static) {
        return false;
    }
    if (first == CollisionLayer::Sensor && second == CollisionLayer::Sensor) {
        return false;
    }
    return true;
}

} // namespace easy3d
