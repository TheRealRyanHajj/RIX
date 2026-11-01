#include "easy3d/physics.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <iostream>
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
    force_world.set_body_transform(force_body, {4.0F, 5.0F, 6.0F}, Quat{});
    assert(almost_equal(force_world.body_position(force_body), Vec3{4.0F, 5.0F, 6.0F}));

    bool rejected_material = false;
    try {
        PhysicsMaterial{.friction = 0.2F, .restitution = 1.1F}.validate();
    } catch (const std::invalid_argument&) {
        rejected_material = true;
    }
    assert(rejected_material);

    std::cout << "easy3d_physics_tests: PASS\n";
    return 0;
}
