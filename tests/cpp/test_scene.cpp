#include "easy3d/scene.hpp"

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
    if (!scene.active() || scene.entity_count() != 1 || !scene.is_alive(scene_entity)) {
        return fail(9, "scene ownership state is invalid");
    }
    scene.clear();
    if (scene.entity_count() != 0 || scene.is_alive(scene_entity)) {
        return fail(10, "scene clear did not invalidate entities");
    }

    try {
        (void)easy3d::Scene("");
        return fail(11, "empty scene name was accepted");
    } catch (const std::invalid_argument&) {
        // Expected.
    }

    std::cout << "easy3d_scene_tests: PASS\n";
    return 0;
}
