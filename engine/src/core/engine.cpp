#include "easy3d/core.hpp"

#include "easy3d/version.hpp"
#include "platform/window.hpp"

#include <cmath>
#include <limits>
#include <utility>

namespace easy3d {

const char* engine_version() noexcept {
    return EASY3D_VERSION;
}

int native_add(const int left, const int right) noexcept {
    return left + right;
}

Engine::Engine(EngineConfig config) : config_(std::move(config)) {
    if (config_.title.empty()) {
        throw std::invalid_argument("window title must not be empty");
    }
    if (config_.width == 0 || config_.height == 0) {
        throw std::invalid_argument("window width and height must be greater than zero");
    }
    if (config_.width > std::numeric_limits<std::uint16_t>::max() ||
        config_.height > std::numeric_limits<std::uint16_t>::max()) {
        throw std::invalid_argument("window dimensions must fit in 16 bits");
    }
    if (!std::isfinite(config_.fps_limit) || config_.fps_limit < 0.0) {
        throw std::invalid_argument("fps_limit must be zero (unlimited) or positive");
    }
}

void Engine::run() {
    bool expected = false;
    if (!running_.compare_exchange_strong(expected, true)) {
        throw EngineError("this Engine is already running");
    }

    struct RunningReset final {
        std::atomic_bool& value;
        ~RunningReset() { value.store(false); }
    } reset{running_};

    stop_requested_.store(false);
    frame_count_.store(0);
    last_frame_seconds_.store(0.0);
    platform::run_window_loop(config_, stop_requested_, frame_count_, last_frame_seconds_);
}

void Engine::stop() noexcept {
    stop_requested_.store(true);
}

bool Engine::is_running() const noexcept {
    return running_.load();
}

std::uint64_t Engine::frame_count() const noexcept {
    return frame_count_.load();
}

double Engine::last_frame_seconds() const noexcept {
    return last_frame_seconds_.load();
}

const EngineConfig& Engine::config() const noexcept {
    return config_;
}

} // namespace easy3d

