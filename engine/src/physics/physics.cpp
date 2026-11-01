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
#include <Jolt/Physics/Collision/Shape/Shape.h>
#include <Jolt/Physics/Collision/Shape/SphereShape.h>
#include <Jolt/Physics/Collision/ShapeCast.h>
#include <Jolt/Physics/PhysicsSystem.h>
#include <Jolt/RegisterTypes.h>

#include <algorithm>
#include <atomic>
#include <cmath>
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
          job_system(JPH::cMaxPhysicsJobs),
          contact_recorder(std::max<std::size_t>(
              1'024U, static_cast<std::size_t>(config.max_contact_constraints) * 4U)) {
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
        physics_system.SetContactListener(&contact_recorder);
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
