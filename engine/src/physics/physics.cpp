#include "easy3d/physics.hpp"

#include <Jolt/Jolt.h>

#include <Jolt/Core/Factory.h>
#include <Jolt/Core/JobSystemSingleThreaded.h>
#include <Jolt/Core/TempAllocator.h>
#include <Jolt/Physics/Body/BodyCreationSettings.h>
#include <Jolt/Physics/Body/Body.h>
#include <Jolt/Physics/Collision/CastResult.h>
#include <Jolt/Physics/Collision/CollideShape.h>
#include <Jolt/Physics/Collision/CollisionCollectorImpl.h>
#include <Jolt/Physics/Collision/ContactListener.h>
#include <Jolt/Physics/Collision/NarrowPhaseQuery.h>
#include <Jolt/Physics/Collision/RayCast.h>
#include <Jolt/Physics/Collision/BroadPhase/BroadPhaseLayer.h>
#include <Jolt/Physics/Collision/Shape/BoxShape.h>
#include <Jolt/Physics/Collision/Shape/CapsuleShape.h>
#include <Jolt/Physics/Collision/Shape/ConvexHullShape.h>
#include <Jolt/Physics/Collision/Shape/MeshShape.h>
#include <Jolt/Physics/Collision/Shape/Shape.h>
#include <Jolt/Physics/Collision/Shape/SphereShape.h>
#include <Jolt/Physics/Collision/Shape/RotatedTranslatedShape.h>
#include <Jolt/Physics/Collision/ShapeCast.h>
#include <Jolt/Physics/Character/CharacterVirtual.h>
#include <Jolt/Physics/Constraints/DistanceConstraint.h>
#include <Jolt/Physics/Constraints/FixedConstraint.h>
#include <Jolt/Physics/Body/BodyLockMulti.h>
#include <Jolt/Physics/PhysicsSystem.h>
#include <Jolt/RegisterTypes.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <limits>
#include <mutex>
#include <sstream>
#include <unordered_map>
#include <unordered_set>
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

[[nodiscard]] std::string invalid_handle_message(const PhysicsCharacterHandle handle) {
    std::ostringstream message;
    message << "invalid physics character handle (index=" << handle.index
            << ", generation=" << handle.generation << ", world=" << handle.world_id << ')';
    return message.str();
}

[[nodiscard]] std::string invalid_handle_message(const PhysicsConstraintHandle handle) {
    std::ostringstream message;
    message << "invalid physics constraint handle (index=" << handle.index
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
    if (settings.shape == PhysicsShape::Capsule &&
        (!std::isfinite(settings.radius) || settings.radius <= 0.0F ||
         !std::isfinite(settings.height) || settings.height <= 2.0F * settings.radius)) {
        throw std::invalid_argument(
            "capsule radius must be positive and total height greater than its diameter");
    }
    if (settings.shape == PhysicsShape::ConvexHull) {
        if (settings.vertices.size() < 4U || settings.vertices.size() > 256U ||
            !std::all_of(settings.vertices.begin(), settings.vertices.end(),
                         [](const Vec3 point) { return finite(point); })) {
            throw std::invalid_argument(
                "convex hull requires between 4 and 256 finite points");
        }
    }
    if (settings.shape == PhysicsShape::TriangleMesh) {
        if (settings.motion_type != PhysicsMotionType::Static) {
            throw std::invalid_argument("triangle mesh colliders must be static");
        }
        if (settings.vertices.size() < 3U || settings.indices.size() < 3U ||
            settings.indices.size() % 3U != 0U ||
            !std::all_of(settings.vertices.begin(), settings.vertices.end(),
                         [](const Vec3 point) { return finite(point); }) ||
            std::any_of(settings.indices.begin(), settings.indices.end(), [&](const auto index) {
                return index >= settings.vertices.size();
            })) {
            throw std::invalid_argument(
                "triangle mesh requires finite vertices and valid triangle indices");
        }
    }
    settings.material.validate();
    if (!std::isfinite(settings.mass) || settings.mass <= 0.0F) {
        throw std::invalid_argument("physics body mass must be finite and positive");
    }
    if (!std::isfinite(settings.gravity_factor) || settings.gravity_factor < 0.0F) {
        throw std::invalid_argument("physics gravity factor must be finite and non-negative");
    }
    if (!finite(settings.linear_velocity) || settings.linear_velocity.length() > 500.0F) {
        throw std::invalid_argument(
            "physics linear velocity must be finite and no greater than 500 m/s");
    }
    if (settings.continuous && settings.motion_type != PhysicsMotionType::Dynamic) {
        throw std::invalid_argument("continuous collision detection requires a dynamic body");
    }
}

void validate_settings(const CharacterMotorSettings& settings) {
    if (!finite(settings.position) || !std::isfinite(settings.radius) ||
        !std::isfinite(settings.height) || settings.radius <= 0.0F ||
        settings.height <= settings.radius * 2.0F) {
        throw std::invalid_argument(
            "character requires a finite position, positive radius, and height > diameter");
    }
    if (!std::isfinite(settings.speed) || settings.speed < 0.0F ||
        !std::isfinite(settings.acceleration) || settings.acceleration < 0.0F ||
        !std::isfinite(settings.air_acceleration) || settings.air_acceleration < 0.0F ||
        !std::isfinite(settings.ground_friction) || settings.ground_friction < 0.0F ||
        !std::isfinite(settings.stop_speed) || settings.stop_speed < 0.0F ||
        !std::isfinite(settings.air_speed_cap) || settings.air_speed_cap < 0.0F ||
        !std::isfinite(settings.horizontal_speed_limit) ||
        settings.horizontal_speed_limit < 0.0F || !std::isfinite(settings.jump_speed) ||
        settings.jump_speed < 0.0F) {
        throw std::invalid_argument(
            "character movement, friction, caps, and jump values must be finite and "
            "non-negative");
    }
    if (!std::isfinite(settings.max_slope_degrees) || settings.max_slope_degrees < 0.0F ||
        settings.max_slope_degrees >= 90.0F || !std::isfinite(settings.step_height) ||
        settings.step_height < 0.0F) {
        throw std::invalid_argument(
            "character slope must be in [0, 90) degrees and step height non-negative");
    }
    if (!std::isfinite(settings.sprint_multiplier) || settings.sprint_multiplier < 1.0F ||
        !std::isfinite(settings.crouch_height) ||
        settings.crouch_height <= settings.radius * 2.0F ||
        settings.crouch_height > settings.height ||
        !std::isfinite(settings.crouch_speed_multiplier) ||
        settings.crouch_speed_multiplier < 0.0F ||
        settings.crouch_speed_multiplier > 1.0F) {
        throw std::invalid_argument(
            "character sprint multiplier must be at least 1, crouch height must be in "
            "(diameter, height], and crouch speed multiplier must be in [0, 1]");
    }
}

[[nodiscard]] std::uint64_t body_pair_key(const JPH::BodyID first,
                                          const JPH::BodyID second) noexcept {
    const std::uint32_t first_value = first.GetIndexAndSequenceNumber();
    const std::uint32_t second_value = second.GetIndexAndSequenceNumber();
    const std::uint32_t lower = std::min(first_value, second_value);
    const std::uint32_t upper = std::max(first_value, second_value);
    return (static_cast<std::uint64_t>(lower) << 32U) | upper;
}

class ContactRecorder final : public JPH::ContactListener {
public:
    explicit ContactRecorder(const std::size_t max_pending_events)
        : max_pending_events_(max_pending_events) {
        pending_.reserve(max_pending_events_);
        active_.reserve(std::max<std::size_t>(1U, max_pending_events_ / 4U));
        active_bodies_.reserve(std::max<std::size_t>(1U, max_pending_events_ / 4U));
        touched_.reserve(std::max<std::size_t>(1U, max_pending_events_ / 4U));
    }

    void OnContactAdded(const JPH::Body& first,
                        const JPH::Body& second,
                        const JPH::ContactManifold& manifold,
                        JPH::ContactSettings&) override {
        record(PhysicsContactPhase::Enter, first, second, manifold);
    }

    void OnContactPersisted(const JPH::Body& first,
                            const JPH::Body& second,
                            const JPH::ContactManifold& manifold,
                            JPH::ContactSettings&) override {
        record(PhysicsContactPhase::Stay, first, second, manifold);
    }

    void OnContactRemoved(const JPH::SubShapeIDPair&) override {}

    void finalize_removals(const JPH::BodyInterface& bodies) {
        const std::lock_guard lock(mutex_);
        for (auto cached = active_.begin(); cached != active_.end();) {
            const std::uint64_t key = cached->first;
            if (touched_.contains(key)) {
                ++cached;
                continue;
            }
            const auto body_pair = active_bodies_.find(key);
            if (body_pair == active_bodies_.end()) {
                cached = active_.erase(cached);
                continue;
            }

            bool all_bodies_added = true;
            bool has_moving_body = false;
            bool moving_body_active = false;
            for (const JPH::BodyID body : {body_pair->second.first,
                                           body_pair->second.second}) {
                if (!bodies.IsAdded(body)) {
                    all_bodies_added = false;
                    continue;
                }
                if (bodies.GetMotionType(body) != JPH::EMotionType::Static) {
                    has_moving_body = true;
                    moving_body_active = moving_body_active || bodies.IsActive(body);
                }
            }
            if (all_bodies_added && has_moving_body && !moving_body_active) {
                ++cached;
                continue;
            }
            PhysicsContactEvent event = cached->second;
            event.phase = PhysicsContactPhase::Exit;
            append(event);
            active_bodies_.erase(body_pair);
            cached = active_.erase(cached);
        }
        touched_.clear();
    }

    [[nodiscard]] std::vector<PhysicsContactEvent> drain() {
        const std::lock_guard lock(mutex_);
        if (overflowed_) {
            pending_.clear();
            overflowed_ = false;
            throw PhysicsError("physics contact event queue capacity exhausted");
        }
        std::vector<PhysicsContactEvent> result;
        result.swap(pending_);
        return result;
    }

    void clear() noexcept {
        const std::lock_guard lock(mutex_);
        pending_.clear();
        active_.clear();
        active_bodies_.clear();
        touched_.clear();
        overflowed_ = false;
    }

private:
    void record(const PhysicsContactPhase phase,
                const JPH::Body& first,
                const JPH::Body& second,
                const JPH::ContactManifold& manifold) {
        PhysicsContactEvent event{};
        event.phase = phase;
        event.first_user_data = first.GetUserData();
        event.second_user_data = second.GetUserData();
        event.normal = from_jolt_vec(manifold.mWorldSpaceNormal);
        event.trigger = first.IsSensor() || second.IsSensor();
        if (!manifold.mRelativeContactPointsOn1.empty()) {
            event.point = from_jolt_position(manifold.GetWorldSpaceContactPointOn1(0));
        } else {
            event.point = from_jolt_position(manifold.mBaseOffset);
        }

        const std::lock_guard lock(mutex_);
        const std::uint64_t key = body_pair_key(first.GetID(), second.GetID());
        if (event.phase == PhysicsContactPhase::Enter && active_.contains(key)) {
            event.phase = PhysicsContactPhase::Stay;
        }
        append(event);
        try {
            active_.insert_or_assign(key, event);
            active_bodies_.insert_or_assign(key, BodyPair{first.GetID(), second.GetID()});
            touched_.insert(key);
        } catch (...) {
            overflowed_ = true;
        }
    }

    void append(const PhysicsContactEvent& event) noexcept {
        if (pending_.size() < max_pending_events_) {
            try {
                pending_.push_back(event);
            } catch (...) {
                overflowed_ = true;
            }
        } else {
            overflowed_ = true;
        }
    }

    std::mutex mutex_;
    struct BodyPair final {
        JPH::BodyID first;
        JPH::BodyID second;
    };
    std::size_t max_pending_events_;
    bool overflowed_{false};
    std::vector<PhysicsContactEvent> pending_;
    std::unordered_map<std::uint64_t, PhysicsContactEvent> active_;
    std::unordered_map<std::uint64_t, BodyPair> active_bodies_;
    std::unordered_set<std::uint64_t> touched_;
};

[[nodiscard]] bool query_accepts(const JPH::BodyInterface& bodies,
                                 const JPH::BodyID body,
                                 const PhysicsQueryFilter filter) {
    const JPH::ObjectLayer layer = bodies.GetObjectLayer(body);
    if (layer >= 8U || (filter.layer_mask & (1U << layer)) == 0U) {
        return false;
    }
    if (!filter.include_sensors && bodies.IsSensor(body)) {
        return false;
    }
    const std::uint64_t user_data = bodies.GetUserData(body);
    return filter.excluded_user_data == 0 || user_data != filter.excluded_user_data;
}

[[nodiscard]] std::vector<PhysicsQueryHit> cast_shape_all(
    JPH::PhysicsSystem& physics_system,
    const JPH::Shape& shape,
    const Vec3 origin,
    const Quat rotation,
    const Vec3 direction,
    const float max_distance,
    const PhysicsQueryFilter filter) {
    const Vec3 cast_delta = direction.normalized() * max_distance;
    const JPH::RShapeCast cast = JPH::RShapeCast::sFromWorldTransform(
        &shape,
        JPH::Vec3::sOne(),
        JPH::RMat44::sRotationTranslation(to_jolt(rotation.normalized()),
                                         to_jolt_position(origin)),
        to_jolt(cast_delta));
    JPH::ShapeCastSettings settings;
    JPH::AllHitCollisionCollector<JPH::CastShapeCollector> collector;
    physics_system.GetNarrowPhaseQuery().CastShape(
        cast, settings, JPH::RVec3::sZero(), collector);

    const JPH::BodyInterface& bodies = physics_system.GetBodyInterface();
    std::unordered_set<std::uint64_t> seen;
    std::vector<PhysicsQueryHit> result;
    result.reserve(collector.mHits.size());
    for (const JPH::ShapeCastResult& hit : collector.mHits) {
        if (!query_accepts(bodies, hit.mBodyID2, filter)) continue;
        const std::uint64_t user_data = bodies.GetUserData(hit.mBodyID2);
        if (!seen.insert(user_data).second) continue;
        result.push_back({user_data,
                          from_jolt_vec(hit.mContactPointOn2),
                          from_jolt_vec(
                              (-hit.mPenetrationAxis).NormalizedOr(JPH::Vec3::sZero())),
                          max_distance * std::max(hit.mFraction, 0.0F),
                          hit.mFraction});
    }
    std::sort(result.begin(), result.end(), [](const auto& left, const auto& right) {
        if (left.fraction != right.fraction) return left.fraction < right.fraction;
        return left.user_data < right.user_data;
    });
    return result;
}

} // namespace

bool PhysicsBodyHandle::valid() const noexcept {
    return world_id != 0 && index != invalid_index && generation != 0;
}

bool PhysicsCharacterHandle::valid() const noexcept {
    return world_id != 0 && index != invalid_index && generation != 0;
}

std::uint64_t PhysicsCharacterHandle::id() const noexcept {
    return (static_cast<std::uint64_t>(generation) << 32U) | index;
}

bool PhysicsConstraintHandle::valid() const noexcept {
    return world_id != 0 && index != invalid_index && generation != 0;
}

std::uint64_t PhysicsConstraintHandle::id() const noexcept {
    return (static_cast<std::uint64_t>(generation) << 32U) | index;
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

    struct CharacterSlot final {
        JPH::Ref<JPH::CharacterVirtual> character;
        JPH::RefConst<JPH::Shape> standing_shape;
        JPH::RefConst<JPH::Shape> crouching_shape;
        JPH::RefConst<JPH::Shape> standing_inner_shape;
        JPH::RefConst<JPH::Shape> crouching_inner_shape;
        CharacterMotorSettings settings;
        CharacterMotorInput input;
        Vec3 external_acceleration{};
        float yaw_offset_degrees{0.0F};
        std::uint64_t last_input_sequence{0};
        std::uint32_t generation{1};
        bool alive{false};
        bool crouched{false};
        bool sprinting{false};
        bool paused{false};
    };

    struct ConstraintSlot final {
        JPH::Ref<JPH::Constraint> constraint;
        JPH::BodyID first_body;
        JPH::BodyID second_body;
        std::uint32_t generation{1};
        bool alive{false};
    };

    explicit Impl(PhysicsWorldConfig world_config)
        : runtime(jolt_runtime()),
          world_id(next_physics_world_id.fetch_add(1, std::memory_order_relaxed)),
          config(std::move(world_config)),
          temporary_allocator(static_cast<JPH::uint>(config.temporary_allocator_bytes)),
          job_system(JPH::cMaxPhysicsJobs),
          contact_recorder(std::max<std::size_t>(
              1'024U, static_cast<std::size_t>(config.max_contact_constraints) * 4U)) {
        if (world_id == 0) {
            throw PhysicsError("RIX exhausted native physics world identifiers");
        }
        physics_system.Init(config.max_bodies,
                            0,
                            config.max_body_pairs,
                            config.max_contact_constraints,
                            broadphase_layers,
                            object_vs_broadphase_filter,
                            object_layer_pair_filter);
        physics_system.SetContactListener(&contact_recorder);
        slots.reserve(config.max_bodies);
        free_indices.reserve(config.max_bodies);
        character_slots.reserve(32);
        free_character_indices.reserve(32);
        constraint_slots.reserve(32);
        free_constraint_indices.reserve(32);
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

    [[nodiscard]] CharacterSlot& require_slot(const PhysicsCharacterHandle handle) {
        if (!is_alive(handle)) {
            throw PhysicsError(invalid_handle_message(handle));
        }
        return character_slots[handle.index];
    }

    [[nodiscard]] const CharacterSlot& require_slot(
        const PhysicsCharacterHandle handle) const {
        if (!is_alive(handle)) {
            throw PhysicsError(invalid_handle_message(handle));
        }
        return character_slots[handle.index];
    }

    [[nodiscard]] bool is_alive(const PhysicsCharacterHandle handle) const noexcept {
        return handle.world_id == world_id && handle.valid() &&
               handle.index < character_slots.size() && character_slots[handle.index].alive &&
               character_slots[handle.index].generation == handle.generation;
    }

    [[nodiscard]] ConstraintSlot& require_slot(const PhysicsConstraintHandle handle) {
        if (!is_alive(handle)) throw PhysicsError(invalid_handle_message(handle));
        return constraint_slots[handle.index];
    }

    [[nodiscard]] bool is_alive(const PhysicsConstraintHandle handle) const noexcept {
        return handle.world_id == world_id && handle.valid() &&
               handle.index < constraint_slots.size() && constraint_slots[handle.index].alive &&
               constraint_slots[handle.index].generation == handle.generation;
    }

    void destroy_constraint_slot(const std::uint32_t index) noexcept {
        ConstraintSlot& slot = constraint_slots[index];
        if (!slot.alive) return;
        physics_system.RemoveConstraint(slot.constraint);
        slot.constraint = nullptr;
        slot.alive = false;
        ++slot.generation;
        if (slot.generation == 0) slot.generation = 1;
        free_constraint_indices.push_back(index);
        --constraint_count;
    }

    void destroy_constraints_for_body(const JPH::BodyID body) noexcept {
        for (std::uint32_t index = 0;
             index < static_cast<std::uint32_t>(constraint_slots.size());
             ++index) {
            const ConstraintSlot& slot = constraint_slots[index];
            if (slot.alive && (slot.first_body == body || slot.second_body == body)) {
                destroy_constraint_slot(index);
            }
        }
    }

    void update_character(CharacterSlot& slot, const float delta_seconds) {
        JPH::CharacterVirtual& character = *slot.character;
        if (slot.paused) {
            character.SetLinearVelocity(JPH::Vec3::sZero());
            return;
        }

        const bool wants_crouch = slot.input.crouch;
        if (wants_crouch != slot.crouched) {
            const JPH::Shape* shape = wants_crouch ? slot.crouching_shape.GetPtr()
                                                   : slot.standing_shape.GetPtr();
            const JPH::Shape* inner_shape = wants_crouch
                                                ? slot.crouching_inner_shape.GetPtr()
                                                : slot.standing_inner_shape.GetPtr();
            const float maximum_penetration =
                wants_crouch
                    ? std::numeric_limits<float>::max()
                    : 1.5F * physics_system.GetPhysicsSettings().mPenetrationSlop;
            if (character.SetShape(
                    shape,
                    maximum_penetration,
                    physics_system.GetDefaultBroadPhaseLayerFilter(character_layer),
                    physics_system.GetDefaultLayerFilter(character_layer),
                    {},
                    {},
                    temporary_allocator)) {
                character.SetInnerBodyShape(inner_shape);
                slot.crouched = wants_crouch;
            }
        }
        character.UpdateGroundVelocity();

        const float heading = JPH::DegreesToRadians(
            slot.input.heading_degrees + slot.yaw_offset_degrees);
        const JPH::Quat heading_rotation =
            JPH::Quat::sRotation(JPH::Vec3::sAxisY(), heading);
        JPH::Vec3 local_movement(slot.input.movement.x, 0.0F, -slot.input.movement.z);
        const float input_length = local_movement.Length();
        const float input_strength = std::min(input_length, 1.0F);
        if (input_length > 1.0e-6F) {
            local_movement /= input_length;
        } else {
            local_movement = JPH::Vec3::sZero();
        }
        const JPH::Vec3 desired_direction = heading_rotation * local_movement;
        slot.sprinting = slot.input.sprint && !slot.crouched &&
                         !desired_direction.IsNearZero();
        const float speed_multiplier = slot.crouched
                                           ? slot.settings.crouch_speed_multiplier
                                           : (slot.sprinting
                                                  ? slot.settings.sprint_multiplier
                                                  : 1.0F);
        const float wish_speed = slot.settings.speed * speed_multiplier * input_strength;

        const bool on_walkable_ground = character.GetGroundState() ==
                                        JPH::CharacterVirtual::EGroundState::OnGround;
        const JPH::Vec3 current = character.GetLinearVelocity();
        const JPH::Vec3 ground_velocity = character.GetGroundVelocity();
        const bool moving_towards_ground = current.GetY() - ground_velocity.GetY() < 0.1F;
        const bool grounded_for_movement = on_walkable_ground && moving_towards_ground;
        const bool should_jump = grounded_for_movement && slot.input.jump;

        JPH::Vec3 horizontal(current.GetX(), 0.0F, current.GetZ());
        const JPH::Vec3 ground_horizontal(
            ground_velocity.GetX(), 0.0F, ground_velocity.GetZ());
        if (grounded_for_movement) horizontal -= ground_horizontal;

        // Source-style ground friction is deliberately skipped on the exact
        // takeoff frame. A correctly timed jump therefore carries momentum,
        // while landing without jumping immediately begins slowing the player.
        if (grounded_for_movement && !should_jump) {
            const float horizontal_speed = horizontal.Length();
            if (horizontal_speed > 1.0e-6F) {
                const float control_speed =
                    std::max(horizontal_speed, slot.settings.stop_speed);
                const float dropped_speed =
                    control_speed * slot.settings.ground_friction * delta_seconds;
                const float new_speed = std::max(0.0F, horizontal_speed - dropped_speed);
                horizontal *= new_speed / horizontal_speed;
            }
        }

        // Acceleration only fills the component of velocity along wish direction.
        // In air, the projected component is capped but orthogonal momentum is
        // retained, which permits strafing curves without forward-only speed gain.
        if (!desired_direction.IsNearZero() && wish_speed > 0.0F) {
            const bool use_ground_acceleration = grounded_for_movement && !should_jump;
            const float target_speed = use_ground_acceleration
                                           ? wish_speed
                                           : std::min(wish_speed, slot.settings.air_speed_cap);
            const float acceleration = use_ground_acceleration
                                           ? slot.settings.acceleration
                                           : slot.settings.air_acceleration;
            const float additional_speed =
                target_speed - horizontal.Dot(desired_direction);
            if (additional_speed > 0.0F) {
                const float acceleration_speed =
                    acceleration * wish_speed * delta_seconds;
                horizontal += desired_direction *
                              std::min(additional_speed, acceleration_speed);
            }
        }

        if (slot.settings.horizontal_speed_limit > 0.0F &&
            horizontal.LengthSq() > slot.settings.horizontal_speed_limit *
                                        slot.settings.horizontal_speed_limit) {
            horizontal = horizontal.Normalized() * slot.settings.horizontal_speed_limit;
        }

        JPH::Vec3 velocity = horizontal + current.GetY() * JPH::Vec3::sAxisY();
        if (grounded_for_movement) {
            velocity = horizontal + ground_velocity;
        }
        if (should_jump) {
            velocity = horizontal + ground_velocity +
                       slot.settings.jump_speed * JPH::Vec3::sAxisY();
        }
        const JPH::Vec3 world_gravity = physics_system.GetGravity();
        velocity += world_gravity * delta_seconds;
        velocity += to_jolt(slot.external_acceleration) * delta_seconds;
        character.SetLinearVelocity(character.CancelVelocityTowardsSteepSlopes(velocity));

        if (slot.settings.mode == CharacterMotorMode::FirstPerson) {
            character.SetRotation(heading_rotation);
        } else if (!desired_direction.IsNearZero()) {
            const float facing = std::atan2(-desired_direction.GetX(),
                                            -desired_direction.GetZ()) +
                                 JPH::DegreesToRadians(slot.yaw_offset_degrees);
            character.SetRotation(
                JPH::Quat::sRotation(JPH::Vec3::sAxisY(), facing));
        }

        JPH::CharacterVirtual::ExtendedUpdateSettings update_settings;
        update_settings.mWalkStairsStepUp =
            slot.settings.step_height * JPH::Vec3::sAxisY();
        update_settings.mStickToFloorStepDown =
            -slot.settings.step_height * JPH::Vec3::sAxisY();
        character.ExtendedUpdate(
            delta_seconds,
            world_gravity,
            update_settings,
            physics_system.GetDefaultBroadPhaseLayerFilter(character_layer),
            physics_system.GetDefaultLayerFilter(character_layer),
            {},
            {},
            temporary_allocator);
        slot.input.jump = false;
    }

    void clear() noexcept {
        free_constraint_indices.clear();
        free_constraint_indices.reserve(constraint_slots.size());
        for (std::uint32_t index = 0;
             index < static_cast<std::uint32_t>(constraint_slots.size());
             ++index) {
            if (constraint_slots[index].alive) destroy_constraint_slot(index);
        }
        free_constraint_indices.clear();
        for (std::uint32_t index = 0;
             index < static_cast<std::uint32_t>(constraint_slots.size());
             ++index) {
            free_constraint_indices.push_back(index);
        }
        constraint_count = 0;

        free_character_indices.clear();
        free_character_indices.reserve(character_slots.size());
        for (std::size_t index = 0; index < character_slots.size(); ++index) {
            CharacterSlot& slot = character_slots[index];
            if (slot.alive) {
                slot.character = nullptr;
                ++slot.generation;
                if (slot.generation == 0) slot.generation = 1;
            }
            slot.standing_shape = nullptr;
            slot.crouching_shape = nullptr;
            slot.standing_inner_shape = nullptr;
            slot.crouching_inner_shape = nullptr;
            slot.alive = false;
            slot.input = {};
            slot.external_acceleration = {};
            slot.yaw_offset_degrees = 0.0F;
            slot.last_input_sequence = 0;
            slot.crouched = false;
            slot.sprinting = false;
            slot.paused = false;
            free_character_indices.push_back(static_cast<std::uint32_t>(index));
        }
        character_count = 0;

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
        contact_recorder.clear();
    }

    JoltRuntime& runtime;
    std::uint64_t world_id;
    PhysicsWorldConfig config;
    BroadPhaseLayers broadphase_layers;
    ObjectVsBroadPhaseFilter object_vs_broadphase_filter;
    ObjectLayerPairFilter object_layer_pair_filter;
    JPH::TempAllocatorImpl temporary_allocator;
    JPH::JobSystemSingleThreaded job_system;
    ContactRecorder contact_recorder;
    JPH::PhysicsSystem physics_system;
    std::vector<Slot> slots;
    std::vector<std::uint32_t> free_indices;
    std::vector<CharacterSlot> character_slots;
    std::vector<std::uint32_t> free_character_indices;
    std::vector<ConstraintSlot> constraint_slots;
    std::vector<std::uint32_t> free_constraint_indices;
    std::size_t body_count{0};
    std::size_t character_count{0};
    std::size_t constraint_count{0};
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
    if (impl_->body_count + impl_->character_count >= impl_->config.max_bodies) {
        throw PhysicsError("physics world body capacity exhausted");
    }

    const auto checked_shape = [](JPH::ShapeSettings::ShapeResult result,
                                  const std::string_view label) -> JPH::ShapeRefC {
        if (result.HasError()) {
            const auto& error = result.GetError();
            throw std::invalid_argument("Jolt rejected " + std::string(label) + ": " +
                                        std::string(error.data(), error.size()));
        }
        return result.Get();
    };
    JPH::ShapeRefC shape;
    switch (settings.shape) {
    case PhysicsShape::Box:
        shape = checked_shape(JPH::BoxShapeSettings(to_jolt(settings.half_extents)).Create(),
                              "box shape");
        break;
    case PhysicsShape::Sphere:
        shape = checked_shape(JPH::SphereShapeSettings(settings.radius).Create(),
                              "sphere shape");
        break;
    case PhysicsShape::Capsule:
        shape = checked_shape(
            JPH::CapsuleShapeSettings(0.5F * settings.height - settings.radius,
                                      settings.radius).Create(),
            "capsule shape");
        break;
    case PhysicsShape::ConvexHull: {
        JPH::Array<JPH::Vec3> points;
        points.reserve(settings.vertices.size());
        for (const Vec3 point : settings.vertices) points.push_back(to_jolt(point));
        shape = checked_shape(JPH::ConvexHullShapeSettings(points).Create(),
                              "convex hull shape");
        break;
    }
    case PhysicsShape::TriangleMesh: {
        JPH::VertexList vertices;
        vertices.reserve(settings.vertices.size());
        for (const Vec3 point : settings.vertices) {
            vertices.emplace_back(point.x, point.y, point.z);
        }
        JPH::IndexedTriangleList triangles;
        triangles.reserve(settings.indices.size() / 3U);
        for (std::size_t index = 0; index < settings.indices.size(); index += 3U) {
            triangles.emplace_back(settings.indices[index],
                                   settings.indices[index + 1U],
                                   settings.indices[index + 2U],
                                   0U);
        }
        shape = checked_shape(
            JPH::MeshShapeSettings(std::move(vertices), std::move(triangles)).Create(),
            "triangle mesh shape");
        break;
    }
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
    body_settings.mMotionQuality = settings.continuous ? JPH::EMotionQuality::LinearCast
                                                        : JPH::EMotionQuality::Discrete;
    body_settings.mUserData = settings.user_data;
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
    impl_->destroy_constraints_for_body(slot.body_id);
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

PhysicsCharacterHandle PhysicsWorld::create_character(
    const CharacterMotorSettings& settings) {
    validate_settings(settings);
    if (impl_->body_count + impl_->character_count >= impl_->config.max_bodies) {
        throw PhysicsError("physics world character capacity exhausted");
    }

    const auto create_capsule = [](const float height,
                                   const float radius,
                                   const float scale,
                                   const char* const label) {
        const float scaled_radius = radius * scale;
        const float cylinder_half_height =
            0.5F * (height - 2.0F * radius) * scale;
        JPH::ShapeSettings::ShapeResult result = JPH::RotatedTranslatedShapeSettings(
            JPH::Vec3(0.0F, 0.5F * height, 0.0F),
            JPH::Quat::sIdentity(),
            new JPH::CapsuleShape(cylinder_half_height, scaled_radius)).Create();
        if (result.HasError()) {
            const auto& error = result.GetError();
            throw std::invalid_argument(std::string("Jolt rejected character ") + label +
                                        " capsule: " +
                                        std::string(error.data(), error.size()));
        }
        return JPH::RefConst<JPH::Shape>(result.Get());
    };
    JPH::RefConst<JPH::Shape> standing_shape =
        create_capsule(settings.height, settings.radius, 1.0F, "standing");
    JPH::RefConst<JPH::Shape> crouching_shape =
        create_capsule(settings.crouch_height, settings.radius, 1.0F, "crouching");
    JPH::RefConst<JPH::Shape> standing_inner_shape =
        create_capsule(settings.height, settings.radius, 0.9F, "standing inner");
    JPH::RefConst<JPH::Shape> crouching_inner_shape =
        create_capsule(settings.crouch_height, settings.radius, 0.9F, "crouching inner");

    JPH::Ref<JPH::CharacterVirtualSettings> character_settings =
        new JPH::CharacterVirtualSettings();
    character_settings->mShape = standing_shape;
    character_settings->mMaxSlopeAngle = JPH::DegreesToRadians(settings.max_slope_degrees);
    character_settings->mSupportingVolume =
        JPH::Plane(JPH::Vec3::sAxisY(), -settings.radius);
    character_settings->mEnhancedInternalEdgeRemoval = true;
    character_settings->mInnerBodyShape = standing_inner_shape;
    character_settings->mInnerBodyLayer = character_layer;

    JPH::Ref<JPH::CharacterVirtual> character = new JPH::CharacterVirtual(
        character_settings,
        to_jolt_position(settings.position),
        JPH::Quat::sIdentity(),
        settings.user_data,
        &impl_->physics_system);

    std::uint32_t index = 0;
    if (impl_->free_character_indices.empty()) {
        index = static_cast<std::uint32_t>(impl_->character_slots.size());
        impl_->character_slots.emplace_back();
    } else {
        index = impl_->free_character_indices.back();
        impl_->free_character_indices.pop_back();
    }
    Impl::CharacterSlot& slot = impl_->character_slots[index];
    slot.character = std::move(character);
    slot.standing_shape = std::move(standing_shape);
    slot.crouching_shape = std::move(crouching_shape);
    slot.standing_inner_shape = std::move(standing_inner_shape);
    slot.crouching_inner_shape = std::move(crouching_inner_shape);
    slot.settings = settings;
    slot.input = {};
    slot.external_acceleration = {};
    slot.yaw_offset_degrees = 0.0F;
    slot.last_input_sequence = 0;
    slot.crouched = false;
    slot.sprinting = false;
    slot.paused = false;
    slot.alive = true;
    ++impl_->character_count;
    return PhysicsCharacterHandle{impl_->world_id, index, slot.generation};
}

void PhysicsWorld::destroy_character(const PhysicsCharacterHandle handle) {
    Impl::CharacterSlot& slot = impl_->require_slot(handle);
    slot.character = nullptr;
    slot.standing_shape = nullptr;
    slot.crouching_shape = nullptr;
    slot.standing_inner_shape = nullptr;
    slot.crouching_inner_shape = nullptr;
    slot.alive = false;
    slot.input = {};
    slot.external_acceleration = {};
    slot.yaw_offset_degrees = 0.0F;
    slot.last_input_sequence = 0;
    slot.crouched = false;
    slot.sprinting = false;
    slot.paused = false;
    ++slot.generation;
    if (slot.generation == 0) slot.generation = 1;
    impl_->free_character_indices.push_back(handle.index);
    --impl_->character_count;
}

bool PhysicsWorld::is_alive(const PhysicsCharacterHandle handle) const noexcept {
    return impl_->is_alive(handle);
}

std::size_t PhysicsWorld::character_count() const noexcept {
    return impl_->character_count;
}

void PhysicsWorld::set_character_input(const PhysicsCharacterHandle handle,
                                       CharacterMotorInput input) {
    if (!finite(input.movement) || !std::isfinite(input.heading_degrees)) {
        throw std::invalid_argument("character input must be finite");
    }
    input.movement.y = 0.0F;
    const float length_squared = input.movement.length_squared();
    if (length_squared > 1.0F) input.movement = input.movement.normalized();
    impl_->require_slot(handle).input = input;
}

void PhysicsWorld::set_character_sequenced_input(
    const PhysicsCharacterHandle handle,
    const std::uint64_t sequence,
    CharacterMotorInput input) {
    Impl::CharacterSlot& slot = impl_->require_slot(handle);
    if (sequence == 0 || sequence <= slot.last_input_sequence) {
        throw std::invalid_argument(
            "character input sequence must be nonzero and strictly increasing");
    }
    set_character_input(handle, input);
    slot.last_input_sequence = sequence;
}

std::uint64_t PhysicsWorld::character_input_sequence(
    const PhysicsCharacterHandle handle) const {
    return impl_->require_slot(handle).last_input_sequence;
}

CharacterMotorState PhysicsWorld::character_state(
    const PhysicsCharacterHandle handle) const {
    const Impl::CharacterSlot& slot = impl_->require_slot(handle);
    return {from_jolt_position(slot.character->GetPosition()),
            from_jolt(slot.character->GetRotation()),
            from_jolt_vec(slot.character->GetLinearVelocity()),
            from_jolt_vec(slot.character->GetGroundNormal()),
            slot.character->GetGroundState() ==
                JPH::CharacterVirtual::EGroundState::OnGround,
            slot.crouched,
            slot.sprinting};
}

void PhysicsWorld::correct_character(const PhysicsCharacterHandle handle,
                                     const Vec3 position,
                                     const Quat rotation,
                                     const Vec3 linear_velocity) {
    if (!finite(position) || !finite(rotation) || !finite(linear_velocity) ||
        linear_velocity.length() > 500.0F) {
        throw std::invalid_argument(
            "character correction must have finite position/rotation and velocity no greater than 500 m/s");
    }
    Impl::CharacterSlot& slot = impl_->require_slot(handle);
    slot.character->SetPosition(to_jolt_position(position));
    slot.character->SetRotation(to_jolt(rotation.normalized()));
    slot.character->SetLinearVelocity(to_jolt(linear_velocity));
    slot.character->RefreshContacts(
        impl_->physics_system.GetDefaultBroadPhaseLayerFilter(character_layer),
        impl_->physics_system.GetDefaultLayerFilter(character_layer),
        {},
        {},
        impl_->temporary_allocator);
}

void PhysicsWorld::replay_character_input(const PhysicsCharacterHandle handle,
                                          CharacterMotorInput input,
                                          const float delta_seconds) {
    if (!std::isfinite(delta_seconds) || delta_seconds <= 0.0F) {
        throw std::invalid_argument("character replay delta must be finite and positive");
    }
    set_character_input(handle, input);
    impl_->update_character(impl_->require_slot(handle), delta_seconds);
}

void PhysicsWorld::set_character_linear_velocity(
    const PhysicsCharacterHandle handle,
    const Vec3 velocity) {
    if (!finite(velocity) || velocity.length() > 500.0F) {
        throw std::invalid_argument(
            "character linear velocity must be finite and no greater than 500 m/s");
    }
    impl_->require_slot(handle).character->SetLinearVelocity(to_jolt(velocity));
}

void PhysicsWorld::set_character_external_motion(
    const PhysicsCharacterHandle handle,
    const Vec3 acceleration,
    const float yaw_offset_degrees) {
    if (!finite(acceleration) || !std::isfinite(yaw_offset_degrees)) {
        throw std::invalid_argument("character external motion must be finite");
    }
    Impl::CharacterSlot& slot = impl_->require_slot(handle);
    slot.external_acceleration = acceleration;
    slot.yaw_offset_degrees = yaw_offset_degrees;
}

void PhysicsWorld::set_character_paused(const PhysicsCharacterHandle handle,
                                        const bool paused) {
    Impl::CharacterSlot& slot = impl_->require_slot(handle);
    slot.paused = paused;
    if (paused) {
        slot.character->SetLinearVelocity(JPH::Vec3::sZero());
    }
}

void PhysicsWorld::teleport_character(const PhysicsCharacterHandle handle,
                                      const Vec3 position,
                                      const float heading_degrees) {
    if (!finite(position) || !std::isfinite(heading_degrees)) {
        throw std::invalid_argument("character teleport must be finite");
    }
    Impl::CharacterSlot& slot = impl_->require_slot(handle);
    const float heading = JPH::DegreesToRadians(heading_degrees);
    slot.character->SetPosition(to_jolt_position(position));
    slot.character->SetRotation(
        JPH::Quat::sRotation(JPH::Vec3::sAxisY(), heading));
    slot.character->SetLinearVelocity(JPH::Vec3::sZero());
    slot.character->RefreshContacts(
        impl_->physics_system.GetDefaultBroadPhaseLayerFilter(character_layer),
        impl_->physics_system.GetDefaultLayerFilter(character_layer),
        {},
        {},
        impl_->temporary_allocator);
}

PhysicsConstraintHandle PhysicsWorld::create_constraint(
    const PhysicsConstraintSettings& settings) {
    const Impl::Slot& first_slot = impl_->require_slot(settings.first);
    const Impl::Slot& second_slot = impl_->require_slot(settings.second);
    if (settings.first == settings.second) {
        throw std::invalid_argument("a constraint requires two different bodies");
    }
    if (first_slot.motion_type == PhysicsMotionType::Static &&
        second_slot.motion_type == PhysicsMotionType::Static) {
        throw std::invalid_argument("a constraint requires at least one moving body");
    }
    if (!finite(settings.first_anchor) || !finite(settings.second_anchor)) {
        throw std::invalid_argument("constraint anchors must be finite");
    }
    if (impl_->constraint_count >= impl_->config.max_contact_constraints) {
        throw PhysicsError("physics world constraint capacity exhausted");
    }

    JPH::BodyID body_ids[]{first_slot.body_id, second_slot.body_id};
    JPH::BodyLockMultiWrite lock(
        impl_->physics_system.GetBodyLockInterface(), body_ids, 2);
    JPH::Body* first_body = lock.GetBody(0);
    JPH::Body* second_body = lock.GetBody(1);
    if (first_body == nullptr || second_body == nullptr) {
        throw PhysicsError("constraint bodies are no longer available");
    }

    JPH::Ref<JPH::Constraint> constraint;
    if (settings.type == PhysicsConstraintType::Fixed) {
        JPH::FixedConstraintSettings native_settings;
        native_settings.mAutoDetectPoint = settings.auto_detect_fixed_point;
        native_settings.mPoint1 = to_jolt_position(settings.first_anchor);
        native_settings.mPoint2 = to_jolt_position(settings.second_anchor);
        constraint = native_settings.Create(*first_body, *second_body);
    } else {
        const bool automatic_distance = settings.minimum_distance < 0.0F &&
                                        settings.maximum_distance < 0.0F;
        if (!automatic_distance &&
            (!std::isfinite(settings.minimum_distance) ||
             !std::isfinite(settings.maximum_distance) ||
             settings.minimum_distance < 0.0F ||
             settings.maximum_distance < settings.minimum_distance)) {
            throw std::invalid_argument(
                "distance limits must both be negative for automatic length or satisfy 0 <= min <= max");
        }
        JPH::DistanceConstraintSettings native_settings;
        native_settings.mPoint1 = to_jolt_position(settings.first_anchor);
        native_settings.mPoint2 = to_jolt_position(settings.second_anchor);
        native_settings.mMinDistance = settings.minimum_distance;
        native_settings.mMaxDistance = settings.maximum_distance;
        constraint = native_settings.Create(*first_body, *second_body);
    }
    if (constraint == nullptr) throw PhysicsError("Jolt could not create constraint");
    std::uint32_t index = 0;
    if (impl_->free_constraint_indices.empty()) {
        index = static_cast<std::uint32_t>(impl_->constraint_slots.size());
        impl_->constraint_slots.emplace_back();
    } else {
        index = impl_->free_constraint_indices.back();
        impl_->free_constraint_indices.pop_back();
    }
    Impl::ConstraintSlot& slot = impl_->constraint_slots[index];
    slot.constraint = std::move(constraint);
    slot.first_body = first_slot.body_id;
    slot.second_body = second_slot.body_id;
    slot.alive = true;
    impl_->physics_system.AddConstraint(slot.constraint);
    ++impl_->constraint_count;
    return {impl_->world_id, index, slot.generation};
}

void PhysicsWorld::destroy_constraint(const PhysicsConstraintHandle handle) {
    (void)impl_->require_slot(handle);
    impl_->destroy_constraint_slot(handle.index);
}

bool PhysicsWorld::is_alive(const PhysicsConstraintHandle handle) const noexcept {
    return impl_->is_alive(handle);
}

std::size_t PhysicsWorld::constraint_count() const noexcept {
    return impl_->constraint_count;
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

Vec3 PhysicsWorld::body_angular_velocity(const PhysicsBodyHandle handle) const {
    const Impl::Slot& slot = impl_->require_slot(handle);
    return from_jolt_vec(
        impl_->physics_system.GetBodyInterface().GetAngularVelocity(slot.body_id));
}

void PhysicsWorld::set_body_linear_velocity(const PhysicsBodyHandle handle,
                                            const Vec3 velocity) {
    const Impl::Slot& slot = impl_->require_slot(handle);
    if (slot.motion_type == PhysicsMotionType::Static) {
        throw PhysicsError("static physics bodies do not have linear velocity");
    }
    if (!finite(velocity) || velocity.length() > 500.0F) {
        throw std::invalid_argument(
            "physics linear velocity must be finite and no greater than 500 m/s");
    }
    impl_->physics_system.GetBodyInterface().SetLinearVelocity(slot.body_id, to_jolt(velocity));
}

void PhysicsWorld::set_body_angular_velocity(const PhysicsBodyHandle handle,
                                             const Vec3 radians_per_second) {
    const Impl::Slot& slot = impl_->require_slot(handle);
    if (slot.motion_type == PhysicsMotionType::Static) {
        throw PhysicsError("static physics bodies do not have angular velocity");
    }
    if (!finite(radians_per_second)) {
        throw std::invalid_argument("physics angular velocity must be finite");
    }
    impl_->physics_system.GetBodyInterface().SetAngularVelocity(
        slot.body_id, to_jolt(radians_per_second));
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

std::vector<PhysicsQueryHit> PhysicsWorld::raycast_all(
    const Vec3 origin,
    const Vec3 direction,
    const float max_distance,
    const PhysicsQueryFilter filter) const {
    if (!finite(origin) || !finite(direction) || direction.length_squared() <= 1.0e-12F) {
        throw std::invalid_argument("ray origin and nonzero direction must be finite");
    }
    if (!std::isfinite(max_distance) || max_distance <= 0.0F) {
        throw std::invalid_argument("ray max distance must be finite and positive");
    }

    const Vec3 ray_delta = direction.normalized() * max_distance;
    const JPH::RRayCast ray(to_jolt_position(origin), to_jolt(ray_delta));
    JPH::RayCastSettings settings;
    JPH::AllHitCollisionCollector<JPH::CastRayCollector> collector;
    impl_->physics_system.GetNarrowPhaseQuery().CastRay(ray, settings, collector);

    const JPH::BodyInterface& bodies = impl_->physics_system.GetBodyInterface();
    std::vector<PhysicsQueryHit> result;
    result.reserve(collector.mHits.size());
    for (const JPH::RayCastResult& hit : collector.mHits) {
        if (!query_accepts(bodies, hit.mBodyID, filter)) {
            continue;
        }
        const JPH::RVec3 point = ray.GetPointOnRay(hit.mFraction);
        const JPH::TransformedShape transformed = bodies.GetTransformedShape(hit.mBodyID);
        result.push_back({bodies.GetUserData(hit.mBodyID),
                          from_jolt_position(point),
                          from_jolt_vec(
                              transformed.GetWorldSpaceSurfaceNormal(hit.mSubShapeID2, point)),
                          max_distance * hit.mFraction,
                          hit.mFraction});
    }
    std::sort(result.begin(), result.end(), [](const auto& left, const auto& right) {
        if (left.fraction != right.fraction) return left.fraction < right.fraction;
        return left.user_data < right.user_data;
    });
    return result;
}

std::vector<PhysicsQueryHit> PhysicsWorld::overlap_sphere(
    const Vec3 center,
    const float radius,
    const PhysicsQueryFilter filter) const {
    if (!finite(center) || !std::isfinite(radius) || radius <= 0.0F) {
        throw std::invalid_argument("overlap sphere center must be finite and radius positive");
    }
    const JPH::SphereShape shape(radius);
    JPH::CollideShapeSettings settings;
    JPH::AllHitCollisionCollector<JPH::CollideShapeCollector> collector;
    impl_->physics_system.GetNarrowPhaseQuery().CollideShape(
        &shape,
        JPH::Vec3::sOne(),
        JPH::RMat44::sTranslation(to_jolt_position(center)),
        settings,
        JPH::RVec3::sZero(),
        collector);

    const JPH::BodyInterface& bodies = impl_->physics_system.GetBodyInterface();
    std::unordered_set<std::uint64_t> seen;
    std::vector<PhysicsQueryHit> result;
    result.reserve(collector.mHits.size());
    for (const JPH::CollideShapeResult& hit : collector.mHits) {
        if (!query_accepts(bodies, hit.mBodyID2, filter)) continue;
        const std::uint64_t user_data = bodies.GetUserData(hit.mBodyID2);
        if (!seen.insert(user_data).second) continue;
        result.push_back({user_data,
                          from_jolt_vec(hit.mContactPointOn2),
                          from_jolt_vec(
                              (-hit.mPenetrationAxis).NormalizedOr(JPH::Vec3::sZero())),
                          0.0F,
                          0.0F});
    }
    std::sort(result.begin(), result.end(), [](const auto& left, const auto& right) {
        return left.user_data < right.user_data;
    });
    return result;
}

std::vector<PhysicsQueryHit> PhysicsWorld::overlap_box(
    const Vec3 center,
    const Vec3 half_extents,
    const Quat rotation,
    const PhysicsQueryFilter filter) const {
    if (!finite(center) || !finite(half_extents) || !finite(rotation) ||
        half_extents.x <= 0.0F || half_extents.y <= 0.0F || half_extents.z <= 0.0F) {
        throw std::invalid_argument(
            "overlap box transform must be finite and half extents positive");
    }
    const JPH::BoxShape shape(to_jolt(half_extents));
    JPH::CollideShapeSettings settings;
    JPH::AllHitCollisionCollector<JPH::CollideShapeCollector> collector;
    impl_->physics_system.GetNarrowPhaseQuery().CollideShape(
        &shape,
        JPH::Vec3::sOne(),
        JPH::RMat44::sRotationTranslation(to_jolt(rotation.normalized()),
                                         to_jolt_position(center)),
        settings,
        JPH::RVec3::sZero(),
        collector);

    const JPH::BodyInterface& bodies = impl_->physics_system.GetBodyInterface();
    std::unordered_set<std::uint64_t> seen;
    std::vector<PhysicsQueryHit> result;
    result.reserve(collector.mHits.size());
    for (const JPH::CollideShapeResult& hit : collector.mHits) {
        if (!query_accepts(bodies, hit.mBodyID2, filter)) continue;
        const std::uint64_t user_data = bodies.GetUserData(hit.mBodyID2);
        if (!seen.insert(user_data).second) continue;
        result.push_back({user_data,
                          from_jolt_vec(hit.mContactPointOn2),
                          from_jolt_vec(
                              (-hit.mPenetrationAxis).NormalizedOr(JPH::Vec3::sZero())),
                          0.0F,
                          0.0F});
    }
    std::sort(result.begin(), result.end(), [](const auto& left, const auto& right) {
        return left.user_data < right.user_data;
    });
    return result;
}

std::vector<PhysicsQueryHit> PhysicsWorld::sphere_cast_all(
    const Vec3 origin,
    const float radius,
    const Vec3 direction,
    const float max_distance,
    const PhysicsQueryFilter filter) const {
    if (!finite(origin) || !std::isfinite(radius) || radius <= 0.0F ||
        !finite(direction) || direction.length_squared() <= 1.0e-12F ||
        !std::isfinite(max_distance) || max_distance <= 0.0F) {
        throw std::invalid_argument(
            "sphere cast requires finite origin/direction and positive radius/distance");
    }
    const JPH::SphereShape shape(radius);
    return cast_shape_all(
        impl_->physics_system, shape, origin, Quat{}, direction, max_distance, filter);
}

std::vector<PhysicsQueryHit> PhysicsWorld::capsule_cast_all(
    const Vec3 origin,
    const float radius,
    const float height,
    const Quat rotation,
    const Vec3 direction,
    const float max_distance,
    const PhysicsQueryFilter filter) const {
    if (!finite(origin) || !finite(rotation) || !std::isfinite(radius) || radius <= 0.0F ||
        !std::isfinite(height) || height <= radius * 2.0F || !finite(direction) ||
        direction.length_squared() <= 1.0e-12F || !std::isfinite(max_distance) ||
        max_distance <= 0.0F) {
        throw std::invalid_argument(
            "capsule cast requires finite values, positive radius/distance, and height > diameter");
    }
    const JPH::CapsuleShape shape(height * 0.5F - radius, radius);
    return cast_shape_all(
        impl_->physics_system, shape, origin, rotation, direction, max_distance, filter);
}

std::vector<PhysicsContactEvent> PhysicsWorld::drain_contact_events() {
    return impl_->contact_recorder.drain();
}

void PhysicsWorld::step(const float delta_seconds, const std::uint32_t collision_steps) {
    if (!std::isfinite(delta_seconds) || delta_seconds <= 0.0F) {
        throw std::invalid_argument("physics delta must be finite and positive");
    }
    if (collision_steps == 0 || collision_steps > 64) {
        throw std::invalid_argument("physics collision steps must be between 1 and 64");
    }

    for (Impl::CharacterSlot& slot : impl_->character_slots) {
        if (!slot.alive) continue;
        impl_->update_character(slot, delta_seconds);
    }

    const JPH::EPhysicsUpdateError error = impl_->physics_system.Update(
        delta_seconds,
        static_cast<int>(collision_steps),
        &impl_->temporary_allocator,
        &impl_->job_system);
    impl_->contact_recorder.finalize_removals(
        impl_->physics_system.GetBodyInterface());
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
