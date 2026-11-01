#include "easy3d/input.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {

int fail(const int code, const char* const message) {
    std::cerr << message << '\n';
    return code;
}

[[nodiscard]] bool close(const float left, const float right) {
    return std::abs(left - right) <= 1.0e-5F;
}

} // namespace

int main() {
    try {
        easy3d::InputSystem input;
        input.bind_action("move_x",
                          {{"key:d", 1.0F, 0.0F},
                           {"key:a", -1.0F, 0.0F},
                           {"gamepad:left_x", 1.0F, 0.2F}});
        input.bind_action("jump", {{"key:space", 1.0F, 0.0F}});
        input.bind_action("look_x", {{"mouse:delta_x", 0.1F, 0.0F}});

        input.begin_frame();
        input.set_control("key:d", 1.0F);
        input.end_frame();
        auto move = input.action_state("move_x");
        if (!move.down || !move.pressed || move.released || !close(move.value, 1.0F)) {
            return fail(1, "digital action press transition is incorrect");
        }

        input.begin_frame();
        input.end_frame();
        move = input.action_state("move_x");
        if (!move.down || move.pressed || move.released) {
            return fail(2, "held action transition is incorrect");
        }

        input.begin_frame();
        input.set_control("key:d", 0.0F);
        input.set_control("gamepad:left_x", 0.6F);
        input.end_frame();
        move = input.action_state("move_x");
        if (!close(move.value, 0.5F)) {
            return fail(3, "analog deadzone rescaling is incorrect");
        }

        input.begin_frame();
        input.set_control("gamepad:left_x", 0.0F);
        input.end_frame();
        move = input.action_state("move_x");
        if (move.down || !move.released || !close(move.value, 0.0F)) {
            return fail(4, "action release transition is incorrect");
        }

        input.begin_frame();
        input.add_pointer_motion(50.0F, 25.0F, 4.0F, -2.0F);
        input.add_pointer_motion(54.0F, 23.0F, 4.0F, -2.0F);
        input.add_wheel(1.0F, -3.0F);
        input.end_frame();
        const easy3d::PointerState pointer = input.pointer_state();
        if (!close(pointer.x, 54.0F) || !close(pointer.y, 23.0F) ||
            !close(pointer.delta_x, 8.0F) || !close(pointer.delta_y, -4.0F) ||
            !close(pointer.wheel_x, 1.0F) || !close(pointer.wheel_y, -3.0F)) {
            return fail(5, "pointer accumulation is incorrect");
        }
        if (!close(input.action_state("look_x").value, 0.8F)) {
            return fail(6, "pointer delta action mapping is incorrect");
        }

        input.request_pointer_lock(true);
        input.set_pointer_lock_active(true);
        input.set_gamepad_connected(true, "Test Pad");
        input.set_control("key:space", 1.0F);
        input.set_control("gamepad:a", 1.0F);
        input.set_focused(false);
        input.end_frame();
        if (input.focused() || input.pointer_lock_active() ||
            !input.pointer_lock_requested() || input.control_value("key:space") != 0.0F ||
            input.control_value("gamepad:a") != 0.0F) {
            return fail(7, "focus loss did not clear held input and active pointer lock");
        }
        input.set_control("key:space", 1.0F);
        input.add_pointer_motion(100.0F, 100.0F, 20.0F, 20.0F);
        if (input.control_value("key:space") != 0.0F) {
            return fail(8, "unfocused input event was accepted");
        }

        input.set_focused(true);
        input.set_gamepad_connected(false);
        if (input.gamepad_connected() || !input.gamepad_name().empty()) {
            return fail(9, "gamepad disconnect state is incorrect");
        }

        input.bind_action("jump", {{"gamepad:a", 1.0F, 0.0F}}, false);
        if (input.action_bindings("jump").size() != 2 || input.action_count() != 3) {
            return fail(10, "action remapping did not append bindings");
        }
        input.unbind_action("jump");
        if (input.action_count() != 2) {
            return fail(11, "action unbind is incorrect");
        }

        try {
            input.bind_action("bad", {{"key:w", 1.0F, 1.0F}});
            return fail(12, "invalid binding deadzone was accepted");
        } catch (const std::invalid_argument&) {
            // Expected.
        }

        std::cout << "easy3d_input_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "easy3d_input_tests: FAIL: " << error.what() << '\n';
        return 13;
    }
}
