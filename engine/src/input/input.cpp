#include "easy3d/input.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace easy3d {
namespace {

[[nodiscard]] bool finite(const float value) noexcept {
    return std::isfinite(value);
}

} // namespace

void InputSystem::begin_frame() {
    std::scoped_lock lock(mutex_);
    pointer_.delta_x = 0.0F;
    pointer_.delta_y = 0.0F;
    pointer_.wheel_x = 0.0F;
    pointer_.wheel_y = 0.0F;
    controls_["mouse:delta_x"] = 0.0F;
    controls_["mouse:delta_y"] = 0.0F;
    controls_["mouse:wheel_x"] = 0.0F;
    controls_["mouse:wheel_y"] = 0.0F;
    for (auto& [name, action] : actions_) {
        (void)name;
        action.state.pressed = false;
        action.state.released = false;
    }
}

void InputSystem::end_frame() {
    std::scoped_lock lock(mutex_);
    for (auto& [name, action] : actions_) {
        (void)name;
        const bool was_down = action.state.down;
        action.state.value = evaluate(action);
        action.state.down = std::abs(action.state.value) > 1.0e-6F;
        action.state.pressed = !was_down && action.state.down;
        action.state.released = was_down && !action.state.down;
    }
}

void InputSystem::set_control(const std::string_view control, const float value) {
    validate_control(control);
    if (!finite(value)) {
        throw std::invalid_argument("input control value must be finite");
    }
    std::scoped_lock lock(mutex_);
    if (!focused_) {
        return;
    }
    controls_[std::string(control)] = std::clamp(value, -1.0F, 1.0F);
}

float InputSystem::control_value(const std::string_view control) const {
    validate_control(control);
    std::scoped_lock lock(mutex_);
    const auto found = controls_.find(std::string(control));
    return found == controls_.end() ? 0.0F : found->second;
}

void InputSystem::add_pointer_motion(const float x,
                                     const float y,
                                     const float delta_x,
                                     const float delta_y) {
    if (!finite(x) || !finite(y) || !finite(delta_x) || !finite(delta_y)) {
        throw std::invalid_argument("pointer motion values must be finite");
    }
    std::scoped_lock lock(mutex_);
    if (!focused_) {
        return;
    }
    pointer_.x = x;
    pointer_.y = y;
    pointer_.delta_x += delta_x;
    pointer_.delta_y += delta_y;
    controls_["mouse:delta_x"] += delta_x;
    controls_["mouse:delta_y"] += delta_y;
}

void InputSystem::add_wheel(const float x, const float y) {
    if (!finite(x) || !finite(y)) {
        throw std::invalid_argument("pointer wheel values must be finite");
    }
    std::scoped_lock lock(mutex_);
    if (!focused_) {
        return;
    }
    pointer_.wheel_x += x;
    pointer_.wheel_y += y;
    controls_["mouse:wheel_x"] += x;
    controls_["mouse:wheel_y"] += y;
}

PointerState InputSystem::pointer_state() const {
    std::scoped_lock lock(mutex_);
    return pointer_;
}

void InputSystem::set_focused(const bool focused) {
    std::scoped_lock lock(mutex_);
    focused_ = focused;
    if (!focused) {
        reset_controls_locked();
        pointer_lock_active_ = false;
    }
}

bool InputSystem::focused() const {
    std::scoped_lock lock(mutex_);
    return focused_;
}

void InputSystem::request_pointer_lock(const bool enabled) {
    std::scoped_lock lock(mutex_);
    pointer_lock_requested_ = enabled;
}

bool InputSystem::pointer_lock_requested() const {
    std::scoped_lock lock(mutex_);
    return pointer_lock_requested_;
}

void InputSystem::set_pointer_lock_active(const bool active) {
    std::scoped_lock lock(mutex_);
    pointer_lock_active_ = active && focused_;
}

bool InputSystem::pointer_lock_active() const {
    std::scoped_lock lock(mutex_);
    return pointer_lock_active_;
}

void InputSystem::set_gamepad_connected(const bool connected, std::string name) {
    std::scoped_lock lock(mutex_);
    gamepad_connected_ = connected;
    gamepad_name_ = connected ? std::move(name) : std::string{};
    if (!connected) {
        for (auto& [control, value] : controls_) {
            if (control.starts_with("gamepad:")) {
                value = 0.0F;
            }
        }
    }
}

bool InputSystem::gamepad_connected() const {
    std::scoped_lock lock(mutex_);
    return gamepad_connected_;
}

std::string InputSystem::gamepad_name() const {
    std::scoped_lock lock(mutex_);
    return gamepad_name_;
}

void InputSystem::bind_action(std::string action,
                              std::vector<InputBinding> bindings,
                              const bool replace) {
    validate_action(action);
    if (bindings.empty()) {
        throw std::invalid_argument("input action requires at least one binding");
    }
    for (const InputBinding& binding : bindings) {
        validate_control(binding.control);
        if (!finite(binding.scale) || !finite(binding.deadzone) ||
            binding.deadzone < 0.0F || binding.deadzone >= 1.0F) {
            throw std::invalid_argument(
                "input binding scale must be finite and deadzone must be in [0, 1)");
        }
    }

    std::scoped_lock lock(mutex_);
    Action& target = actions_[std::move(action)];
    if (replace) {
        target.bindings = std::move(bindings);
    } else {
        target.bindings.insert(target.bindings.end(), bindings.begin(), bindings.end());
    }
    target.state.value = evaluate(target);
    target.state.down = std::abs(target.state.value) > 1.0e-6F;
    target.state.pressed = false;
    target.state.released = false;
}

void InputSystem::unbind_action(const std::string_view action) {
    validate_action(action);
    std::scoped_lock lock(mutex_);
    actions_.erase(std::string(action));
}

void InputSystem::clear_actions() {
    std::scoped_lock lock(mutex_);
    actions_.clear();
}

InputActionState InputSystem::action_state(const std::string_view action) const {
    validate_action(action);
    std::scoped_lock lock(mutex_);
    const auto found = actions_.find(std::string(action));
    if (found == actions_.end()) {
        throw std::out_of_range("input action is not bound: " + std::string(action));
    }
    return found->second.state;
}

std::vector<InputBinding> InputSystem::action_bindings(
    const std::string_view action) const {
    validate_action(action);
    std::scoped_lock lock(mutex_);
    const auto found = actions_.find(std::string(action));
    if (found == actions_.end()) {
        throw std::out_of_range("input action is not bound: " + std::string(action));
    }
    return found->second.bindings;
}

std::size_t InputSystem::action_count() const {
    std::scoped_lock lock(mutex_);
    return actions_.size();
}

void InputSystem::validate_control(const std::string_view control) {
    const auto separator = control.find(':');
    if (control.empty() || separator == std::string_view::npos || separator == 0 ||
        separator + 1 >= control.size()) {
        throw std::invalid_argument(
            "input control must use a non-empty 'device:name' identifier");
    }
}

void InputSystem::validate_action(const std::string_view action) {
    if (action.empty()) {
        throw std::invalid_argument("input action name must not be empty");
    }
}

float InputSystem::evaluate(const Action& action) const noexcept {
    float value = 0.0F;
    for (const InputBinding& binding : action.bindings) {
        const auto found = controls_.find(binding.control);
        if (found == controls_.end()) {
            continue;
        }
        float contribution = found->second;
        if (std::abs(contribution) <= binding.deadzone) {
            contribution = 0.0F;
        } else if (binding.deadzone > 0.0F) {
            const float magnitude = (std::abs(contribution) - binding.deadzone) /
                                    (1.0F - binding.deadzone);
            contribution = std::copysign(magnitude, contribution);
        }
        value += contribution * binding.scale;
    }
    return std::clamp(value, -1.0F, 1.0F);
}

void InputSystem::reset_controls_locked() {
    for (auto& [control, value] : controls_) {
        (void)control;
        value = 0.0F;
    }
    pointer_.delta_x = 0.0F;
    pointer_.delta_y = 0.0F;
    pointer_.wheel_x = 0.0F;
    pointer_.wheel_y = 0.0F;
}

} // namespace easy3d
