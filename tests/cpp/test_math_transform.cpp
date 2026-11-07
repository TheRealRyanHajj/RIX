#include "easy3d/math.hpp"
#include "easy3d/scene.hpp"

#include <iostream>
#include <stdexcept>

namespace {

int fail(const int code, const char* message) {
    std::cerr << message << '\n';
    return code;
}

} // namespace

int main() {
    const easy3d::Vec3 vector{3.0F, 4.0F, 0.0F};
    if (!easy3d::almost_equal(vector.length(), 5.0F) ||
        !easy3d::almost_equal(vector.normalized(), {0.6F, 0.8F, 0.0F})) {
        return fail(1, "Vec3 length or normalization failed");
    }
    if (easy3d::Vec3{1.0F, 0.0F, 0.0F}.cross({0.0F, 1.0F, 0.0F}) !=
        easy3d::Vec3{0.0F, 0.0F, 1.0F}) {
        return fail(2, "Vec3 cross product failed");
    }
    try {
        (void)easy3d::Vec3{}.normalized();
        return fail(3, "zero Vec3 normalization was accepted");
    } catch (const std::domain_error&) {
        // Expected.
    }

    const easy3d::Quat yaw = easy3d::Quat::from_euler_degrees({0.0F, 90.0F, 0.0F});
    if (!easy3d::almost_equal(yaw.rotate({0.0F, 0.0F, -1.0F}),
                              {-1.0F, 0.0F, 0.0F},
                              1.0e-4F)) {
        return fail(4, "quaternion rotation failed");
    }
    if (!easy3d::almost_equal(yaw, easy3d::Quat::from_euler_degrees(yaw.to_euler_degrees()))) {
        return fail(5, "quaternion Euler facade round-trip failed");
    }

    easy3d::World world;
    const easy3d::EntityHandle parent = world.create_entity("parent");
    const easy3d::EntityHandle child = world.create_entity("child");
    const easy3d::EntityHandle grandchild = world.create_entity("grandchild");
    world.set_local_transform(parent,
                              {{10.0F, 0.0F, 0.0F}, {}, {1.0F, 1.0F, 1.0F}});
    world.set_local_transform(child, {{1.0F, 2.0F, 3.0F}, {}, {1.0F, 1.0F, 1.0F}});
    world.set_local_transform(grandchild,
                              {{0.0F, 1.0F, 0.0F}, {}, {1.0F, 1.0F, 1.0F}});
    world.set_entity_parent(child, parent);
    world.set_entity_parent(grandchild, child);

    if (!easy3d::almost_equal(world.world_transform(child).position, {11.0F, 2.0F, 3.0F}) ||
        !easy3d::almost_equal(world.world_transform(grandchild).position,
                              {11.0F, 3.0F, 3.0F})) {
        return fail(6, "hierarchical world position failed");
    }

    // Query above populates caches; changing the parent must dirty both descendants.
    world.set_local_transform(parent,
                              {{20.0F, 0.0F, 0.0F}, {}, {1.0F, 1.0F, 1.0F}});
    if (!easy3d::almost_equal(world.world_transform(grandchild).position,
                              {21.0F, 3.0F, 3.0F})) {
        return fail(7, "transform dirty propagation failed");
    }

    try {
        world.set_entity_parent(parent, grandchild);
        return fail(8, "parenting cycle was accepted");
    } catch (const std::invalid_argument&) {
        // Expected.
    }

    const easy3d::Transform child_world_before = world.world_transform(child);
    world.set_entity_parent(child, std::nullopt, true);
    if (world.entity_parent(child).has_value() ||
        !easy3d::almost_equal(world.world_transform(child).position,
                              child_world_before.position)) {
        return fail(9, "keep-world detach failed");
    }
    world.set_entity_parent(child, parent, true);
    if (!easy3d::almost_equal(world.world_transform(child).position,
                              child_world_before.position)) {
        return fail(10, "keep-world reparent failed");
    }

    easy3d::World other_world;
    const easy3d::EntityHandle foreign = other_world.create_entity("foreign");
    try {
        world.set_entity_parent(child, foreign);
        return fail(11, "cross-world parent was accepted");
    } catch (const easy3d::InvalidEntityError&) {
        // Expected.
    }

    const easy3d::Transform preserved = world.world_transform(child);
    world.destroy_entity(parent);
    if (!world.is_alive(child) || world.entity_parent(child).has_value() ||
        !easy3d::almost_equal(world.world_transform(child).position, preserved.position)) {
        return fail(12, "destroying parent did not preserve and detach child");
    }

    std::cout << "rix_math_transform_tests: PASS\n";
    return 0;
}
