#include "easy3d/physics.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

int main() {
    using namespace easy3d;

    assert(!PhysicsWorld::layers_collide(CollisionLayer::Static, CollisionLayer::Static));
    assert(!PhysicsWorld::layers_collide(CollisionLayer::Sensor, CollisionLayer::Sensor));
    assert(PhysicsWorld::layers_collide(CollisionLayer::Static, CollisionLayer::Dynamic));
    assert(PhysicsWorld::layers_collide(CollisionLayer::Dynamic, CollisionLayer::Static));
    assert(PhysicsWorld::layers_collide(CollisionLayer::Character, CollisionLayer::Sensor));

    bool rejected_capacity = false;
    try {
        (void)PhysicsWorld(PhysicsWorldConfig{.max_bodies = 0});
    } catch (const std::invalid_argument&) {
        rejected_capacity = true;
    }
    assert(rejected_capacity);

    PhysicsWorld world(PhysicsWorldConfig{
        .max_bodies = 32,
        .max_body_pairs = 128,
        .max_contact_constraints = 64,
        .temporary_allocator_bytes = 1024U * 1024U,
    });
    world.set_gravity({0.0F, -9.81F, 0.0F});
    assert(almost_equal(world.gravity(), Vec3{0.0F, -9.81F, 0.0F}));

    PhysicsBodySettings floor_settings{};
    floor_settings.motion_type = PhysicsMotionType::Static;
    floor_settings.layer = CollisionLayer::Static;
    floor_settings.position = {0.0F, -0.5F, 0.0F};
    floor_settings.half_extents = {5.0F, 0.5F, 5.0F};
    floor_settings.user_data = 101;
    const PhysicsBodyHandle floor = world.create_body(floor_settings);

    PhysicsBodySettings ball_settings{};
    ball_settings.shape = PhysicsShape::Sphere;
    ball_settings.position = {0.0F, 3.0F, 0.0F};
    ball_settings.radius = 0.5F;
    ball_settings.user_data = 202;
    const PhysicsBodyHandle ball = world.create_body(ball_settings);
    assert(world.body_count() == 2);

    for (int step = 0; step < 240; ++step) {
        world.step(1.0F / 60.0F);
    }
    assert(world.step_count() == 240);
    const Vec3 settled = world.body_position(ball);
    assert(std::abs(settled.x) < 1.0e-3F);
    assert(settled.y > 0.45F && settled.y < 0.56F);
    assert(std::abs(settled.z) < 1.0e-3F);

    const std::vector<PhysicsQueryHit> ray_hits =
        world.raycast_all({0.0F, 5.0F, 0.0F}, {0.0F, -1.0F, 0.0F}, 10.0F);
    assert(ray_hits.size() == 2);
    assert(ray_hits[0].user_data == 202);
    assert(ray_hits[1].user_data == 101);
    assert(ray_hits[0].distance < ray_hits[1].distance);
    const std::vector<PhysicsQueryHit> filtered_ray_hits = world.raycast_all(
        {0.0F, 5.0F, 0.0F},
        {0.0F, -1.0F, 0.0F},
        10.0F,
        PhysicsQueryFilter{.excluded_user_data = 202});
    assert(filtered_ray_hits.size() == 1 && filtered_ray_hits[0].user_data == 101);

    const std::vector<PhysicsQueryHit> sphere_overlaps =
        world.overlap_sphere(settled, 0.25F);
    assert(sphere_overlaps.size() == 1 && sphere_overlaps[0].user_data == 202);
    const std::vector<PhysicsQueryHit> box_overlaps =
        world.overlap_box(settled, {0.25F, 0.25F, 0.25F});
    assert(box_overlaps.size() == 1 && box_overlaps[0].user_data == 202);
    const std::vector<PhysicsQueryHit> sphere_cast_hits = world.sphere_cast_all(
        {0.0F, 5.0F, 0.0F}, 0.25F, {0.0F, -1.0F, 0.0F}, 10.0F);
    assert(sphere_cast_hits.size() == 2 && sphere_cast_hits[0].user_data == 202 &&
           sphere_cast_hits[1].user_data == 101);
    const std::vector<PhysicsQueryHit> capsule_cast_hits = world.capsule_cast_all(
        {0.0F, 5.0F, 0.0F},
        0.2F,
        1.0F,
        Quat{},
        {0.0F, -1.0F, 0.0F},
        10.0F);
    assert(capsule_cast_hits.size() == 2 && capsule_cast_hits[0].user_data == 202 &&
           capsule_cast_hits[1].user_data == 101);

    const std::vector<PhysicsContactEvent> contacts = world.drain_contact_events();
    assert(std::any_of(contacts.begin(), contacts.end(), [](const auto& event) {
        return event.phase == PhysicsContactPhase::Enter &&
               ((event.first_user_data == 101 && event.second_user_data == 202) ||
                (event.first_user_data == 202 && event.second_user_data == 101));
    }));
    assert(std::any_of(contacts.begin(), contacts.end(), [](const auto& event) {
        return event.phase == PhysicsContactPhase::Stay;
    }));
    assert(std::none_of(contacts.begin(), contacts.end(), [](const auto& event) {
        return event.phase == PhysicsContactPhase::Exit;
    }));

    world.set_body_transform(ball, {0.0F, 10.0F, 0.0F}, Quat{});
    world.step(1.0F / 60.0F);
    const std::vector<PhysicsContactEvent> exits = world.drain_contact_events();
    assert(std::any_of(exits.begin(), exits.end(), [](const auto& event) {
        return event.phase == PhysicsContactPhase::Exit;
    }));

    world.destroy_body(ball);
    assert(!world.is_alive(ball));
    assert(world.body_count() == 1);
    bool rejected_stale = false;
    try {
        (void)world.body_position(ball);
    } catch (const PhysicsError&) {
        rejected_stale = true;
    }
    assert(rejected_stale);

    world.clear();
    assert(!world.is_alive(floor));
    assert(world.body_count() == 0);

    PhysicsWorld opposite_gravity(PhysicsWorldConfig{
        .max_bodies = 4,
        .max_body_pairs = 4,
        .max_contact_constraints = 4,
        .temporary_allocator_bytes = 256U * 1024U,
    });
    opposite_gravity.set_gravity({0.0F, 5.0F, 0.0F});
    const PhysicsBodyHandle rising = opposite_gravity.create_body(ball_settings);
    PhysicsBodySettings another_ball_settings = ball_settings;
    another_ball_settings.position = {2.0F, 3.0F, 0.0F};
    const PhysicsBodyHandle local_live = world.create_body(another_ball_settings);
    assert(!world.is_alive(rising));
    assert(!opposite_gravity.is_alive(local_live));
    bool rejected_cross_world = false;
    try {
        opposite_gravity.destroy_body(local_live);
    } catch (const PhysicsError&) {
        rejected_cross_world = true;
    }
    assert(rejected_cross_world);
    opposite_gravity.step(0.1F);
    assert(opposite_gravity.body_position(rising).y > ball_settings.position.y);
    assert(world.body_count() == 1);
    world.destroy_body(local_live);
    assert(world.body_count() == 0);

    PhysicsWorld force_world(PhysicsWorldConfig{
        .max_bodies = 4,
        .max_body_pairs = 4,
        .max_contact_constraints = 4,
        .temporary_allocator_bytes = 256U * 1024U,
    });
    force_world.set_gravity({0.0F, 0.0F, 0.0F});
    PhysicsBodySettings force_body_settings{};
    force_body_settings.shape = PhysicsShape::Sphere;
    force_body_settings.mass = 2.0F;
    force_body_settings.material = {.friction = 0.7F, .restitution = 0.25F};
    const PhysicsBodyHandle force_body = force_world.create_body(force_body_settings);
    force_world.add_impulse(force_body, {2.0F, 0.0F, 0.0F});
    assert(almost_equal(force_world.body_linear_velocity(force_body),
                        Vec3{1.0F, 0.0F, 0.0F},
                        1.0e-4F));
    force_world.add_force(force_body, {2.0F, 0.0F, 0.0F});
    force_world.step(0.5F);
    assert(force_world.body_linear_velocity(force_body).x > 1.4F);
    force_world.set_body_linear_velocity(force_body, {0.0F, 2.0F, 0.0F});
    force_world.set_body_angular_velocity(force_body, {0.0F, 1.5F, 0.0F});
    assert(almost_equal(force_world.body_angular_velocity(force_body),
                        Vec3{0.0F, 1.5F, 0.0F},
                        1.0e-4F));
    force_world.set_body_transform(force_body, {4.0F, 5.0F, 6.0F}, Quat{});
    assert(almost_equal(force_world.body_position(force_body), Vec3{4.0F, 5.0F, 6.0F}));

    bool rejected_material = false;
    try {
        PhysicsMaterial{.friction = 0.2F, .restitution = 1.1F}.validate();
    } catch (const std::invalid_argument&) {
        rejected_material = true;
    }
    assert(rejected_material);

    PhysicsWorld character_world(PhysicsWorldConfig{
        .max_bodies = 32,
        .max_body_pairs = 128,
        .max_contact_constraints = 64,
        .temporary_allocator_bytes = 1024U * 1024U,
    });
    PhysicsBodySettings character_floor{};
    character_floor.motion_type = PhysicsMotionType::Static;
    character_floor.layer = CollisionLayer::Static;
    character_floor.position = {0.0F, -0.5F, 0.0F};
    character_floor.half_extents = {10.0F, 0.5F, 10.0F};
    (void)character_world.create_body(character_floor);
    PhysicsBodySettings step_settings = character_floor;
    step_settings.position = {0.0F, 0.15F, -2.0F};
    step_settings.half_extents = {1.0F, 0.15F, 0.5F};
    (void)character_world.create_body(step_settings);

    const PhysicsCharacterHandle first_person = character_world.create_character(
        CharacterMotorSettings{.mode = CharacterMotorMode::FirstPerson,
                               .position = {0.0F, 0.0F, 0.0F},
                               .speed = 3.0F,
                               .acceleration = 30.0F,
                               .jump_speed = 5.0F,
                               .max_slope_degrees = 45.0F,
                               .step_height = 0.4F});
    for (int step = 0; step < 5; ++step) character_world.step(1.0F / 60.0F);
    assert(character_world.character_state(first_person).grounded);
    character_world.set_character_input(
        first_person, {.movement = {0.0F, 0.0F, 1.0F}});
    for (int step = 0; step < 120; ++step) character_world.step(1.0F / 60.0F);
    const CharacterMotorState walked = character_world.character_state(first_person);
    assert(walked.position.z < -4.0F);
    assert(walked.position.y > -0.02F && walked.position.y < 0.05F);
    assert(walked.grounded);

    character_world.set_character_input(
        first_person, {.movement = {}, .jump = true});
    for (int step = 0; step < 10; ++step) character_world.step(1.0F / 60.0F);
    const CharacterMotorState jumping = character_world.character_state(first_person);
    assert(!jumping.grounded && jumping.position.y > 0.3F &&
           jumping.linear_velocity.y > 0.0F);
    for (int step = 0; step < 120; ++step) character_world.step(1.0F / 60.0F);
    assert(character_world.character_state(first_person).grounded);

    // A jump pulse on the first walkable landing frame skips ground friction
    // and retains horizontal momentum. There is no coyote time or jump buffer.
    character_world.set_character_input(
        first_person, {.movement = {1.0F, 0.0F, 0.0F}});
    for (int step = 0; step < 30; ++step) character_world.step(1.0F / 60.0F);
    const float momentum_before_hop =
        character_world.character_state(first_person).linear_velocity.x;
    assert(momentum_before_hop > 2.9F);
    character_world.set_character_input(first_person, {.jump = true});
    character_world.step(1.0F / 60.0F);
    bool began_falling = false;
    bool found_landing = false;
    bool jumped_after_landing = false;
    CharacterMotorState second_takeoff{};
    for (int step = 0; step < 180; ++step) {
        const CharacterMotorState before_step =
            character_world.character_state(first_person);
        began_falling = began_falling || before_step.linear_velocity.y < -0.5F;
        if (began_falling && before_step.grounded) {
            found_landing = true;
            character_world.set_character_input(first_person, {.jump = true});
        } else {
            character_world.set_character_input(first_person, {});
        }
        character_world.step(1.0F / 60.0F);
        const CharacterMotorState state = character_world.character_state(first_person);
        if (found_landing && state.linear_velocity.y > 3.0F) {
            jumped_after_landing = true;
            second_takeoff = state;
            break;
        }
    }
    assert(found_landing);
    assert(jumped_after_landing);
    assert(second_takeoff.linear_velocity.x > momentum_before_hop * 0.95F);

    // Input magnitude is clamped, eliminating the diagonal speed boost.
    character_world.set_character_input(first_person, {});
    for (int step = 0; step < 120; ++step) character_world.step(1.0F / 60.0F);
    assert(character_world.character_state(first_person).grounded);
    character_world.set_character_input(
        first_person, {.movement = {1.0F, 0.0F, 1.0F}});
    for (int step = 0; step < 30; ++step) character_world.step(1.0F / 60.0F);
    const CharacterMotorState diagonal = character_world.character_state(first_person);
    assert(std::sqrt(diagonal.linear_velocity.x * diagonal.linear_velocity.x +
                     diagonal.linear_velocity.z * diagonal.linear_velocity.z) < 3.1F);

    // Air acceleration fills only the wish-direction projection. Forward input
    // cannot increase an already-full projection; perpendicular strafing can
    // add a component and therefore curve/gain speed.
    character_world.set_character_linear_velocity(first_person, {3.0F, 2.0F, 0.0F});
    character_world.set_character_input(
        first_person, {.movement = {1.0F, 0.0F, 0.0F}});
    character_world.step(1.0F / 60.0F);
    assert(std::abs(character_world.character_state(first_person).linear_velocity.x - 3.0F) <
           0.02F);
    character_world.set_character_linear_velocity(first_person, {3.0F, 2.0F, 0.0F});
    character_world.set_character_input(
        first_person, {.movement = {0.0F, 0.0F, 1.0F}});
    character_world.step(1.0F / 60.0F);
    const CharacterMotorState air_strafe = character_world.character_state(first_person);
    assert(air_strafe.linear_velocity.z < -0.1F);
    assert(std::sqrt(air_strafe.linear_velocity.x * air_strafe.linear_velocity.x +
                     air_strafe.linear_velocity.z * air_strafe.linear_velocity.z) > 3.0F);

    character_world.teleport_character(first_person, {0.0F, 1.0F, 0.0F}, 0.0F);
    character_world.set_character_linear_velocity(first_person, {});
    character_world.set_character_input(first_person, {});
    for (int step = 0; step < 120; ++step) character_world.step(1.0F / 60.0F);
    assert(character_world.character_state(first_person).grounded);

    character_world.set_character_input(
        first_person, {.movement = {1.0F, 0.0F, 0.0F}, .sprint = true});
    for (int step = 0; step < 30; ++step) character_world.step(1.0F / 60.0F);
    const CharacterMotorState sprinting = character_world.character_state(first_person);
    assert(sprinting.sprinting && !sprinting.crouched &&
           sprinting.linear_velocity.x > 4.5F);

    character_world.set_character_input(first_person, {.crouch = true});
    character_world.step(1.0F / 60.0F);
    assert(character_world.character_state(first_person).crouched);
    const CharacterMotorState crouched = character_world.character_state(first_person);
    PhysicsBodySettings low_ceiling = character_floor;
    low_ceiling.position = {crouched.position.x, 1.55F, crouched.position.z};
    low_ceiling.half_extents = {1.0F, 0.2F, 1.0F};
    const PhysicsBodyHandle ceiling = character_world.create_body(low_ceiling);
    character_world.set_character_input(first_person, {});
    character_world.step(1.0F / 60.0F);
    assert(character_world.character_state(first_person).crouched);
    character_world.destroy_body(ceiling);
    character_world.step(1.0F / 60.0F);
    assert(!character_world.character_state(first_person).crouched);

    const PhysicsCharacterHandle third_person = character_world.create_character(
        CharacterMotorSettings{.mode = CharacterMotorMode::ThirdPerson,
                               .position = {3.0F, 0.0F, 0.0F},
                               .speed = 2.0F,
                               .acceleration = 30.0F});
    character_world.set_character_input(
        third_person, {.movement = {1.0F, 0.0F, 0.0F}});
    for (int step = 0; step < 30; ++step) character_world.step(1.0F / 60.0F);
    const CharacterMotorState third_state = character_world.character_state(third_person);
    assert(third_state.position.x > 3.5F);
    assert(std::abs(third_state.rotation.y) > 0.5F);
    assert(character_world.character_count() == 2);

    character_world.teleport_character(first_person, {-3.0F, 1.0F, 2.0F}, 90.0F);
    assert(almost_equal(character_world.character_state(first_person).position,
                        Vec3{-3.0F, 1.0F, 2.0F},
                        1.0e-4F));
    character_world.destroy_character(first_person);
    assert(!character_world.is_alive(first_person));
    assert(character_world.character_count() == 1);
    const PhysicsCharacterHandle reused_character = character_world.create_character({});
    assert(reused_character.index == first_person.index);
    assert(reused_character.generation != first_person.generation);
    character_world.destroy_character(reused_character);
    const PhysicsCharacterHandle externally_moved = character_world.create_character(
        CharacterMotorSettings{.mode = CharacterMotorMode::FirstPerson,
                               .position = {6.0F, 1.0F, 0.0F},
                               .speed = 2.0F,
                               .acceleration = 30.0F});
    character_world.set_character_linear_velocity(
        externally_moved, {1.0F, 0.0F, 0.0F});
    character_world.set_character_external_motion(
        externally_moved, {2.0F, 0.0F, 0.0F}, 45.0F);
    character_world.step(0.25F);
    const CharacterMotorState externally_moved_state =
        character_world.character_state(externally_moved);
    assert(externally_moved_state.linear_velocity.x > 1.4F);
    assert(externally_moved_state.position.x > 6.3F);
    assert(std::abs(externally_moved_state.rotation.y) > 0.25F);
    character_world.clear();
    assert(!character_world.is_alive(third_person));
    assert(character_world.character_count() == 0);

    PhysicsWorld slope_world(PhysicsWorldConfig{
        .max_bodies = 16,
        .max_body_pairs = 64,
        .max_contact_constraints = 32,
        .temporary_allocator_bytes = 1024U * 1024U,
    });
    PhysicsBodySettings slope_floor = character_floor;
    slope_floor.half_extents = {10.0F, 0.5F, 10.0F};
    (void)slope_world.create_body(slope_floor);
    PhysicsBodySettings gentle_ramp = character_floor;
    gentle_ramp.position = {-3.0F, 2.0F, -2.464F};
    gentle_ramp.rotation = Quat::from_euler_degrees({30.0F, 0.0F, 0.0F});
    gentle_ramp.half_extents = {1.0F, 0.1F, 4.0F};
    (void)slope_world.create_body(gentle_ramp);
    PhysicsBodySettings steep_ramp = character_floor;
    steep_ramp.position = {3.0F, 3.464F, -1.0F};
    steep_ramp.rotation = Quat::from_euler_degrees({60.0F, 0.0F, 0.0F});
    steep_ramp.half_extents = {1.0F, 0.1F, 4.0F};
    (void)slope_world.create_body(steep_ramp);
    const PhysicsCharacterHandle gentle_climber = slope_world.create_character(
        CharacterMotorSettings{.position = {-3.0F, 0.0F, 2.0F},
                               .speed = 2.0F,
                               .acceleration = 30.0F,
                               .max_slope_degrees = 45.0F});
    const PhysicsCharacterHandle steep_climber = slope_world.create_character(
        CharacterMotorSettings{.position = {3.0F, 0.0F, 2.0F},
                               .speed = 2.0F,
                               .acceleration = 30.0F,
                               .max_slope_degrees = 45.0F});
    slope_world.set_character_input(
        gentle_climber, {.movement = {0.0F, 0.0F, 1.0F}});
    slope_world.set_character_input(
        steep_climber, {.movement = {0.0F, 0.0F, 1.0F}});
    for (int step = 0; step < 120; ++step) slope_world.step(1.0F / 60.0F);
    const CharacterMotorState gentle_state = slope_world.character_state(gentle_climber);
    const CharacterMotorState steep_state = slope_world.character_state(steep_climber);
    assert(gentle_state.position.y > 1.0F && gentle_state.position.z < 0.0F);
    assert(steep_state.position.y < 0.5F && steep_state.position.z > 0.0F);

    PhysicsWorld advanced_world(PhysicsWorldConfig{
        .max_bodies = 32,
        .max_body_pairs = 128,
        .max_contact_constraints = 64,
        .temporary_allocator_bytes = 2U * 1024U * 1024U,
    });
    PhysicsBodySettings mesh_floor{};
    mesh_floor.shape = PhysicsShape::TriangleMesh;
    mesh_floor.motion_type = PhysicsMotionType::Static;
    mesh_floor.layer = CollisionLayer::Static;
    mesh_floor.vertices = {{-5.0F, 0.0F, -5.0F},
                           {5.0F, 0.0F, -5.0F},
                           {5.0F, 0.0F, 5.0F},
                           {-5.0F, 0.0F, 5.0F}};
    mesh_floor.indices = {0, 2, 1, 0, 3, 2};
    (void)advanced_world.create_body(mesh_floor);
    PhysicsBodySettings capsule_settings{};
    capsule_settings.shape = PhysicsShape::Capsule;
    capsule_settings.position = {-2.0F, 4.0F, 0.0F};
    capsule_settings.radius = 0.4F;
    capsule_settings.height = 2.0F;
    const PhysicsBodyHandle capsule = advanced_world.create_body(capsule_settings);
    PhysicsBodySettings convex_settings{};
    convex_settings.shape = PhysicsShape::ConvexHull;
    convex_settings.position = {2.0F, 4.0F, 0.0F};
    convex_settings.vertices = {{-0.5F, -0.5F, -0.5F},
                                {0.5F, -0.5F, -0.5F},
                                {0.5F, -0.5F, 0.5F},
                                {-0.5F, -0.5F, 0.5F},
                                {-0.5F, 0.5F, -0.5F},
                                {0.5F, 0.5F, -0.5F},
                                {0.5F, 0.5F, 0.5F},
                                {-0.5F, 0.5F, 0.5F}};
    const PhysicsBodyHandle convex = advanced_world.create_body(convex_settings);
    for (int step = 0; step < 240; ++step) advanced_world.step(1.0F / 60.0F);
    assert(advanced_world.body_position(capsule).y > 0.95F &&
           advanced_world.body_position(capsule).y < 1.05F);
    assert(advanced_world.body_position(convex).y > 0.45F &&
           advanced_world.body_position(convex).y < 0.55F);

    PhysicsBodySettings anchor_settings{};
    anchor_settings.motion_type = PhysicsMotionType::Static;
    anchor_settings.layer = CollisionLayer::Static;
    anchor_settings.position = {0.0F, 6.0F, 0.0F};
    const PhysicsBodyHandle anchor = advanced_world.create_body(anchor_settings);
    PhysicsBodySettings hanging_settings{};
    hanging_settings.position = {0.0F, 3.0F, 0.0F};
    const PhysicsBodyHandle hanging = advanced_world.create_body(hanging_settings);
    const PhysicsConstraintHandle distance = advanced_world.create_constraint(
        {.type = PhysicsConstraintType::Distance,
         .first = anchor,
         .second = hanging,
         .first_anchor = {0.0F, 6.0F, 0.0F},
         .second_anchor = {0.0F, 3.0F, 0.0F}});
    for (int step = 0; step < 120; ++step) advanced_world.step(1.0F / 60.0F);
    assert(std::abs((advanced_world.body_position(anchor) -
                     advanced_world.body_position(hanging)).length() - 3.0F) < 0.05F);
    assert(advanced_world.is_alive(distance));
    advanced_world.destroy_constraint(distance);
    assert(!advanced_world.is_alive(distance));

    PhysicsBodySettings welded_settings{};
    welded_settings.position = {3.0F, 6.0F, 0.0F};
    const PhysicsBodyHandle welded = advanced_world.create_body(welded_settings);
    const PhysicsConstraintHandle fixed = advanced_world.create_constraint(
        {.type = PhysicsConstraintType::Fixed, .first = anchor, .second = welded});
    for (int step = 0; step < 60; ++step) advanced_world.step(1.0F / 60.0F);
    assert(almost_equal(advanced_world.body_position(welded),
                        Vec3{3.0F, 6.0F, 0.0F},
                        0.05F));
    assert(advanced_world.constraint_count() == 1);
    advanced_world.destroy_body(welded);
    assert(!advanced_world.is_alive(fixed) && advanced_world.constraint_count() == 0);

    PhysicsWorld ccd_world(PhysicsWorldConfig{
        .max_bodies = 8,
        .max_body_pairs = 16,
        .max_contact_constraints = 16,
        .temporary_allocator_bytes = 1024U * 1024U,
    });
    ccd_world.set_gravity({0.0F, 0.0F, 0.0F});
    PhysicsBodySettings thin_wall{};
    thin_wall.motion_type = PhysicsMotionType::Static;
    thin_wall.layer = CollisionLayer::Static;
    thin_wall.half_extents = {0.05F, 5.0F, 5.0F};
    (void)ccd_world.create_body(thin_wall);
    PhysicsBodySettings fast_sphere{};
    fast_sphere.shape = PhysicsShape::Sphere;
    fast_sphere.position = {-5.0F, -2.0F, 0.0F};
    fast_sphere.radius = 0.2F;
    fast_sphere.linear_velocity = {501.0F, 0.0F, 0.0F};
    bool rejected_unsafe_velocity = false;
    try {
        (void)ccd_world.create_body(fast_sphere);
    } catch (const std::invalid_argument&) {
        rejected_unsafe_velocity = true;
    }
    assert(rejected_unsafe_velocity);
    fast_sphere.linear_velocity = {400.0F, 0.0F, 0.0F};
    fast_sphere.continuous = true;
    const PhysicsBodyHandle continuous = ccd_world.create_body(fast_sphere);
    fast_sphere.position = {-5.0F, 2.0F, 0.0F};
    fast_sphere.continuous = false;
    const PhysicsBodyHandle discrete = ccd_world.create_body(fast_sphere);
    ccd_world.step(1.0F / 60.0F);
    assert(ccd_world.body_position(continuous).x < 0.0F);
    assert(ccd_world.body_position(discrete).x > 1.0F);

    std::cout << "rix_physics_tests: PASS\n";
    return 0;
}
