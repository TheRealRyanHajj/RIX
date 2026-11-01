#pragma once

#include <cstddef>
#include <mutex>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace easy3d {

struct InputBinding final {
    std::string control;
    float scale{1.0F};
    float deadzone{0.0F};
};

struct InputActionState final {
    float value{0.0F};
    bool down{false};
    bool pressed{false};
    bool released{false};
};

struct PointerState final {
    float x{0.0F};
    float y{0.0F};
    float delta_x{0.0F};
    float delta_y{0.0F};
    float wheel_x{0.0F};
    float wheel_y{0.0F};
};

class InputSystem final {
public:
    void begin_frame();
    void end_frame();

    void set_control(std::string_view control, float value);
    [[nodiscard]] float control_value(std::string_view control) const;
    void add_pointer_motion(float x, float y, float delta_x, float delta_y);
    void add_wheel(float x, float y);
    [[nodiscard]] PointerState pointer_state() const;

    void set_focused(bool focused);
    [[nodiscard]] bool focused() const;
    void request_pointer_lock(bool enabled);
    [[nodiscard]] bool pointer_lock_requested() const;
    void set_pointer_lock_active(bool active);
    [[nodiscard]] bool pointer_lock_active() const;

    void set_gamepad_connected(bool connected, std::string name = {});
    [[nodiscard]] bool gamepad_connected() const;
    [[nodiscard]] std::string gamepad_name() const;

    void bind_action(std::string action,
                     std::vector<InputBinding> bindings,
                     bool replace = true);
    void unbind_action(std::string_view action);
    void clear_actions();
    [[nodiscard]] InputActionState action_state(std::string_view action) const;
    [[nodiscard]] std::vector<InputBinding> action_bindings(
        std::string_view action) const;
    [[nodiscard]] std::size_t action_count() const;

private:
    struct Action final {
        std::vector<InputBinding> bindings;
        InputActionState state;
    };

    static void validate_control(std::string_view control);
    static void validate_action(std::string_view action);
    [[nodiscard]] float evaluate(const Action& action) const noexcept;
    void reset_controls_locked();

    mutable std::mutex mutex_;
    std::unordered_map<std::string, float> controls_;
    std::unordered_map<std::string, Action> actions_;
    PointerState pointer_;
    bool focused_{true};
    bool pointer_lock_requested_{false};
    bool pointer_lock_active_{false};
    bool gamepad_connected_{false};
    std::string gamepad_name_;
};

} // namespace easy3d
