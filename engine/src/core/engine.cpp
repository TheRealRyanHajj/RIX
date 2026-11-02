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

const char* graphics_preset_name(const GraphicsPreset preset) noexcept {
    switch (preset) {
    case GraphicsPreset::Low: return "low";
    case GraphicsPreset::Medium: return "medium";
    case GraphicsPreset::High: return "high";
    case GraphicsPreset::Ultra: return "ultra";
    }
    return "medium";
}

GraphicsFeatures graphics_features(const GraphicsPreset preset) noexcept {
    switch (preset) {
    case GraphicsPreset::Low:
        return {.enhanced_lighting = false};
    case GraphicsPreset::Medium:
        return {.enhanced_lighting = true,
                .postprocessing = true,
                .fxaa = true};
    case GraphicsPreset::High:
        return {.enhanced_lighting = true,
                .shadows = true,
                .postprocessing = true,
                .fxaa = true,
                .shadow_resolution = 2048};
    case GraphicsPreset::Ultra:
        return {.enhanced_lighting = true,
                .shadows = true,
                .postprocessing = true,
                .fxaa = true,
                .shadow_resolution = 4096};
    }
    return {};
}

void RendererStatsAtomic::reset() noexcept {
    store({});
}

void RendererStatsAtomic::store(const RendererStats stats) noexcept {
    sequence_.fetch_add(1, std::memory_order_acq_rel);
    draw_calls_.store(stats.draw_calls, std::memory_order_relaxed);
    visible_instances_.store(stats.visible_instances, std::memory_order_relaxed);
    culled_instances_.store(stats.culled_instances, std::memory_order_relaxed);
    instanced_draw_calls_.store(stats.instanced_draw_calls, std::memory_order_relaxed);
    ui_draw_calls_.store(stats.ui_draw_calls, std::memory_order_relaxed);
    ui_elements_.store(stats.ui_elements, std::memory_order_relaxed);
    enhanced_lighting_.store(stats.enhanced_lighting, std::memory_order_relaxed);
    shadows_.store(stats.shadows, std::memory_order_relaxed);
    postprocessing_.store(stats.postprocessing, std::memory_order_relaxed);
    fxaa_.store(stats.fxaa, std::memory_order_relaxed);
    shadow_resolution_.store(stats.shadow_resolution, std::memory_order_relaxed);
    sequence_.fetch_add(1, std::memory_order_release);
}

RendererStats RendererStatsAtomic::load() const noexcept {
    for (;;) {
        const std::uint64_t before = sequence_.load(std::memory_order_acquire);
        if ((before & 1U) != 0) {
            continue;
        }
        const RendererStats result{
            draw_calls_.load(std::memory_order_relaxed),
            visible_instances_.load(std::memory_order_relaxed),
            culled_instances_.load(std::memory_order_relaxed),
            instanced_draw_calls_.load(std::memory_order_relaxed),
            ui_draw_calls_.load(std::memory_order_relaxed),
            ui_elements_.load(std::memory_order_relaxed),
            enhanced_lighting_.load(std::memory_order_relaxed),
            shadows_.load(std::memory_order_relaxed),
            postprocessing_.load(std::memory_order_relaxed),
            fxaa_.load(std::memory_order_relaxed),
            shadow_resolution_.load(std::memory_order_relaxed),
        };
        if (before == sequence_.load(std::memory_order_acquire)) {
            return result;
        }
    }
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
    viewport_width_.store(config_.width);
    viewport_height_.store(config_.height);
}

void Engine::run(FrameCallback frame_callback) {
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
    renderer_stats_.reset();
    viewport_width_.store(config_.width);
    viewport_height_.store(config_.height);
    platform::run_window_loop(
        config_,
        scene_,
        stop_requested_,
        frame_count_,
        last_frame_seconds_,
        viewport_width_,
        viewport_height_,
        renderer_stats_,
        input_,
        audio_,
        std::move(frame_callback));
}

void Engine::stop() noexcept {
    stop_requested_.store(true);
}

void Engine::set_scene(Scene* const scene) {
    if (is_running()) {
        throw EngineError("cannot replace the active scene while the Engine is running");
    }
    scene_ = scene;
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

std::pair<std::uint32_t, std::uint32_t> Engine::viewport_size() const noexcept {
    return {viewport_width_.load(), viewport_height_.load()};
}

RendererStats Engine::renderer_stats() const noexcept {
    return renderer_stats_.load();
}

InputSystem& Engine::input() noexcept {
    return input_;
}

const InputSystem& Engine::input() const noexcept {
    return input_;
}

AudioSystem& Engine::audio() noexcept {
    return audio_;
}

const AudioSystem& Engine::audio() const noexcept {
    return audio_;
}

const EngineConfig& Engine::config() const noexcept {
    return config_;
}

} // namespace easy3d

