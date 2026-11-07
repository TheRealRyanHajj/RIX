#include "easy3d/scene.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

int fail(const int code, const char* message) {
    std::cerr << message << '\n';
    return code;
}

} // namespace

int main() {
    easy3d::World world;
    const easy3d::EntityHandle first = world.create_entity("first");
    if (!first.valid() || !world.is_alive(first) || world.entity_count() != 1) {
        return fail(1, "new entity handle is invalid");
    }
    if (world.entity_name(first) != "first" || !world.entity_enabled(first) ||
        !world.entity_visible(first)) {
        return fail(2, "new entity defaults are invalid");
    }

    world.set_entity_name(first, "renamed");
    world.set_entity_enabled(first, false);
    world.set_entity_visible(first, false);
    if (world.entity_name(first) != "renamed" || world.entity_enabled(first) ||
        world.entity_visible(first)) {
        return fail(3, "entity property update failed");
    }

    world.destroy_entity(first);
    if (world.is_alive(first) || world.entity_count() != 0) {
        return fail(4, "destroyed entity remained alive");
    }
    try {
        (void)world.entity_name(first);
        return fail(5, "stale handle access was accepted");
    } catch (const easy3d::InvalidEntityError&) {
        // Expected.
    }

    const easy3d::EntityHandle reused = world.create_entity("reused");
    if (reused.index != first.index || reused.generation == first.generation ||
        reused.id() == first.id()) {
        return fail(6, "entity slot reuse did not advance generation");
    }
    if (!easy3d::almost_equal(world.motion(reused).velocity, easy3d::Vec3{}) ||
        !easy3d::almost_equal(world.motion(reused).acceleration, easy3d::Vec3{}) ||
        !easy3d::almost_equal(world.motion(reused).angular_velocity, easy3d::Vec3{}) ||
        !easy3d::almost_equal(world.motion(reused).angular_acceleration,
                              easy3d::Vec3{})) {
        return fail(24, "reused entity slot retained motion state");
    }

    easy3d::World other_world;
    const easy3d::EntityHandle other = other_world.create_entity("other");
    if (world.is_alive(other)) {
        return fail(7, "cross-world handle was reported alive");
    }
    try {
        world.destroy_entity(other);
        return fail(8, "cross-world handle destruction was accepted");
    } catch (const easy3d::InvalidEntityError&) {
        // Expected.
    }

    easy3d::Scene scene("main");
    scene.set_active(true);
    const easy3d::EntityHandle scene_entity = scene.create_entity("scene entity");
    easy3d::PhysicsBodySettings body_settings{};
    body_settings.shape = easy3d::PhysicsShape::Sphere;
    body_settings.radius = 0.5F;
    const easy3d::PhysicsBodyHandle physics_body = scene.physics().create_body(body_settings);
    scene.set_physics_gravity({0.0F, -2.0F, 0.0F});
    scene.step_physics(1.0F / 60.0F);
    if (!scene.active() || scene.entity_count() != 1 || !scene.is_alive(scene_entity)) {
        return fail(9, "scene ownership state is invalid");
    }
    scene.clear();
    if (scene.entity_count() != 0 || scene.is_alive(scene_entity) ||
        scene.physics().is_alive(physics_body) || scene.physics().body_count() != 0) {
        return fail(10, "scene clear did not invalidate entities and physics bodies");
    }

    easy3d::Scene motion_scene("motion");
    const easy3d::EntityHandle moving = motion_scene.create_entity("moving");
    motion_scene.set_entity_velocity(moving, {1.0F, 0.0F, 0.0F});
    motion_scene.set_entity_acceleration(moving, {2.0F, 0.0F, 0.0F});
    motion_scene.set_entity_angular_velocity(moving, {0.0F, 10.0F, 0.0F});
    motion_scene.set_entity_angular_acceleration(moving, {0.0F, 20.0F, 0.0F});
    motion_scene.step_physics(0.5F);
    if (!easy3d::almost_equal(motion_scene.entity_velocity(moving),
                              {2.0F, 0.0F, 0.0F}) ||
        !easy3d::almost_equal(motion_scene.local_transform(moving).position,
                              {1.0F, 0.0F, 0.0F}) ||
        !easy3d::almost_equal(motion_scene.entity_angular_velocity(moving),
                              {0.0F, 20.0F, 0.0F})) {
        return fail(25, "plain entity semi-implicit integration failed");
    }
    const easy3d::Vec3 rotated_forward =
        motion_scene.local_transform(moving).rotation.rotate({0.0F, 0.0F, -1.0F});
    if (!easy3d::almost_equal(
            rotated_forward,
            {-std::sin(10.0F * 3.14159265358979323846F / 180.0F),
             0.0F,
             -std::cos(10.0F * 3.14159265358979323846F / 180.0F)},
            1.0e-4F)) {
        return fail(26, "plain entity world-axis angular integration failed");
    }

    const easy3d::EntityHandle motion_parent = motion_scene.create_entity("parent");
    easy3d::Transform parent_transform{};
    parent_transform.position = {10.0F, 0.0F, 0.0F};
    parent_transform.rotation = easy3d::Quat::from_euler_degrees({0.0F, 90.0F, 0.0F});
    parent_transform.scale = {2.0F, 2.0F, 2.0F};
    motion_scene.set_local_transform(motion_parent, parent_transform);
    const easy3d::EntityHandle motion_child = motion_scene.create_entity("child");
    motion_scene.set_entity_parent(motion_child, motion_parent);
    const easy3d::Vec3 child_before = motion_scene.world_transform(motion_child).position;
    motion_scene.set_entity_velocity(motion_child, {1.0F, 0.0F, 0.0F});
    motion_scene.step_physics(0.25F);
    if (!easy3d::almost_equal(motion_scene.world_transform(motion_child).position,
                              child_before + easy3d::Vec3{0.25F, 0.0F, 0.0F},
                              1.0e-4F)) {
        return fail(27, "parented entity motion was not world-space");
    }
    motion_scene.set_entity_enabled(moving, false);
    const easy3d::Vec3 frozen_position = motion_scene.world_transform(moving).position;
    const easy3d::Vec3 frozen_velocity = motion_scene.entity_velocity(moving);
    motion_scene.step_physics(1.0F);
    if (!easy3d::almost_equal(motion_scene.world_transform(moving).position,
                              frozen_position) ||
        !easy3d::almost_equal(motion_scene.entity_velocity(moving), frozen_velocity)) {
        return fail(28, "disabled entity did not freeze while retaining motion");
    }
    motion_scene.set_entity_enabled(moving, true);
    motion_scene.step_physics(0.5F);
    if (!easy3d::almost_equal(motion_scene.entity_velocity(moving),
                              frozen_velocity + easy3d::Vec3{1.0F, 0.0F, 0.0F})) {
        return fail(29, "re-enabled entity did not resume saved motion");
    }
    const easy3d::EntityHandle stable_rotation =
        motion_scene.create_entity("stable rotation");
    motion_scene.set_entity_angular_velocity(
        stable_rotation, {73.0F, -41.0F, 19.0F});
    for (int step = 0; step < 3600; ++step) {
        motion_scene.step_physics(1.0F / 120.0F);
    }
    const easy3d::Quat stable_quaternion =
        motion_scene.local_transform(stable_rotation).rotation;
    if (!std::isfinite(stable_quaternion.w) ||
        !std::isfinite(stable_quaternion.x) ||
        !std::isfinite(stable_quaternion.y) ||
        !std::isfinite(stable_quaternion.z) ||
        std::abs(stable_quaternion.length() - 1.0F) > 1.0e-4F) {
        return fail(30, "long-running angular integration lost quaternion stability");
    }
    const easy3d::EntityHandle invalid_static =
        motion_scene.create_entity("invalid moving static collider");
    motion_scene.set_entity_velocity(invalid_static, {1.0F, 0.0F, 0.0F});
    try {
        motion_scene.add_collider_component(invalid_static, {});
        return fail(31, "moving collider-only entity was accepted");
    } catch (const easy3d::PhysicsError&) {
        // Expected.
    }

    easy3d::Scene physics_scene("physics components");
    const easy3d::EntityHandle floor_entity = physics_scene.create_entity("floor");
    easy3d::Transform floor_transform{};
    floor_transform.position = {0.0F, -0.5F, 0.0F};
    physics_scene.set_local_transform(floor_entity, floor_transform);
    physics_scene.add_collider_component(
        floor_entity,
        {.shape = easy3d::PhysicsShape::Box,
         .half_extents = {5.0F, 0.5F, 5.0F},
         .material = {.friction = 0.8F, .restitution = 0.0F}});

    const easy3d::EntityHandle dynamic_entity = physics_scene.create_entity("ball");
    easy3d::Transform dynamic_transform{};
    dynamic_transform.position = {0.0F, 3.0F, 0.0F};
    physics_scene.set_local_transform(dynamic_entity, dynamic_transform);
    physics_scene.add_collider_component(
        dynamic_entity,
        {.shape = easy3d::PhysicsShape::Sphere,
         .radius = 0.5F,
         .material = {.friction = 0.2F, .restitution = 0.1F}});
    physics_scene.add_rigid_body_component(
        dynamic_entity,
        {.motion_type = easy3d::PhysicsMotionType::Dynamic,
         .mass = 2.0F,
         .use_gravity = true});
    physics_scene.add_rigid_body_impulse(dynamic_entity, {2.0F, 0.0F, 0.0F});
    for (int step = 0; step < 180; ++step) {
        physics_scene.step_physics(1.0F / 60.0F);
    }
    if (!physics_scene.has_collider_component(dynamic_entity) ||
        !physics_scene.has_rigid_body_component(dynamic_entity) ||
        physics_scene.local_transform(dynamic_entity).position.y < 0.45F) {
        return fail(15, "scene physics components did not synchronize dynamic pose");
    }
    const easy3d::Vec3 dynamic_position =
        physics_scene.local_transform(dynamic_entity).position;
    const std::vector<easy3d::ScenePhysicsQueryHit> scene_ray_hits =
        physics_scene.raycast_all({dynamic_position.x, 5.0F, dynamic_position.z},
                                  {0.0F, -1.0F, 0.0F},
                                  10.0F);
    if (scene_ray_hits.size() != 2 || scene_ray_hits.front().entity != dynamic_entity ||
        scene_ray_hits.back().entity != floor_entity) {
        return fail(18, "scene raycast did not return sorted entity snapshots");
    }
    const std::vector<easy3d::ScenePhysicsContactEvent> scene_contacts =
        physics_scene.drain_physics_events();
    if (scene_contacts.empty() ||
        !std::any_of(scene_contacts.begin(), scene_contacts.end(), [](const auto& event) {
            return event.phase == easy3d::PhysicsContactPhase::Enter;
        })) {
        return fail(19, "scene did not translate native contact events");
    }
    physics_scene.teleport_rigid_body(
        dynamic_entity, {1.0F, 4.0F, 0.0F}, easy3d::Quat{});
    if (!easy3d::almost_equal(physics_scene.local_transform(dynamic_entity).position,
                              easy3d::Vec3{1.0F, 4.0F, 0.0F})) {
        return fail(16, "rigid body teleport did not synchronize entity pose");
    }
    physics_scene.destroy_entity(dynamic_entity);
    if (physics_scene.physics().body_count() != 1) {
        return fail(17, "entity destruction did not release its physics body");
    }

    easy3d::Scene ui_scene("ui");
    const std::uint64_t panel_id = ui_scene.add_ui_element(
        {.kind = easy3d::UiElementKind::Panel,
         .anchor = easy3d::UiAnchor::BottomRight,
         .x = -16.0F,
         .y = -16.0F,
         .width = 240.0F,
         .height = 80.0F,
         .color = {0.1F, 0.2F, 0.3F, 0.8F}});
    const std::uint64_t text_id = ui_scene.add_ui_element(
        {.kind = easy3d::UiElementKind::Text,
         .width = 120.0F,
         .height = 30.0F,
         .text = "Score: 3",
         .font_size = 24.0F,
         .z_index = 1});
    if (panel_id == text_id || ui_scene.ui_elements().size() != 2 ||
        ui_scene.ui_element(panel_id).anchor != easy3d::UiAnchor::BottomRight) {
        return fail(20, "scene UI element creation failed");
    }
    easy3d::UiElement replacement = ui_scene.ui_element(text_id);
    replacement.text = "Score: 4";
    replacement.visible = false;
    ui_scene.update_ui_element(text_id, replacement);
    if (ui_scene.ui_element(text_id).text != "Score: 4" ||
        ui_scene.ui_element(text_id).visible) {
        return fail(21, "scene UI element update failed");
    }
    ui_scene.remove_ui_element(panel_id);
    try {
        (void)ui_scene.ui_element(panel_id);
        return fail(22, "removed UI element remained accessible");
    } catch (const easy3d::EngineError&) {
        // Expected.
    }
    ui_scene.clear();
    if (!ui_scene.ui_elements().empty()) {
        return fail(23, "scene clear retained UI elements");
    }

    try {
        (void)easy3d::Scene("");
        return fail(11, "empty scene name was accepted");
    } catch (const std::invalid_argument&) {
        // Expected.
    }

    std::cout << "rix_scene_tests: PASS\n";
    return 0;
}
