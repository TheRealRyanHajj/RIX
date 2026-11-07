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
        return {.enhanced_lighting = false,
                .max_directional_lights = 1,
                .max_point_lights = 4,
                .max_spot_lights = 2};
    case GraphicsPreset::Medium:
        return {.enhanced_lighting = true,
                .postprocessing = true,
                .fxaa = true,
                .max_directional_lights = 2,
                .max_point_lights = 16,
                .max_spot_lights = 8};
    case GraphicsPreset::High:
        return {.enhanced_lighting = true,
                .shadows = true,
                .postprocessing = true,
                .fxaa = true,
                .shadow_resolution = 2048,
                .max_directional_lights = 4,
                .max_point_lights = 32,
                .max_spot_lights = 16};
    case GraphicsPreset::Ultra:
        return {.enhanced_lighting = true,
                .shadows = true,
                .postprocessing = true,
                .fxaa = true,
                .shadow_resolution = 4096,
                .max_directional_lights = 4,
                .max_point_lights = 64,
                .max_spot_lights = 32};
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
    cpu_frame_ms_.store(stats.cpu_frame_ms, std::memory_order_relaxed);
    gpu_frame_ms_.store(stats.gpu_frame_ms, std::memory_order_relaxed);
    texture_count_.store(stats.texture_count, std::memory_order_relaxed);
    texture_memory_bytes_.store(stats.texture_memory_bytes, std::memory_order_relaxed);
    active_directional_lights_.store(stats.active_directional_lights,
                                     std::memory_order_relaxed);
    active_point_lights_.store(stats.active_point_lights, std::memory_order_relaxed);
    active_spot_lights_.store(stats.active_spot_lights, std::memory_order_relaxed);
    culled_lights_.store(stats.culled_lights, std::memory_order_relaxed);
    shadow_passes_.store(stats.shadow_passes, std::memory_order_relaxed);
    active_shadow_casters_.store(stats.active_shadow_casters, std::memory_order_relaxed);
    dropped_shadow_casters_.store(stats.dropped_shadow_casters, std::memory_order_relaxed);
    shadow_memory_bytes_.store(stats.shadow_memory_bytes, std::memory_order_relaxed);
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
            cpu_frame_ms_.load(std::memory_order_relaxed),
            gpu_frame_ms_.load(std::memory_order_relaxed),
            texture_count_.load(std::memory_order_relaxed),
            texture_memory_bytes_.load(std::memory_order_relaxed),
            active_directional_lights_.load(std::memory_order_relaxed),
            active_point_lights_.load(std::memory_order_relaxed),
            active_spot_lights_.load(std::memory_order_relaxed),
            culled_lights_.load(std::memory_order_relaxed),
            shadow_passes_.load(std::memory_order_relaxed),
            active_shadow_casters_.load(std::memory_order_relaxed),
            dropped_shadow_casters_.load(std::memory_order_relaxed),
            shadow_memory_bytes_.load(std::memory_order_relaxed),
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

Engine::~Engine() {
    end_loop();
}

void Engine::begin_loop(const LoopMode mode) {
    bool expected = false;
    if (!running_.compare_exchange_strong(expected, true)) {
        throw EngineError(
            mode == LoopMode::Managed
                ? "cannot call run() while this Engine is already running or in a manual loop"
                : "cannot call tick() while this Engine is controlled by run()");
    }

    stop_requested_.store(false);
    frame_count_.store(0);
    last_frame_seconds_.store(0.0);
    renderer_stats_.reset();
    viewport_width_.store(config_.width);
    viewport_height_.store(config_.height);
    loop_mode_ = mode;
    try {
        window_session_ = std::make_unique<platform::WindowSession>(
            config_,
            scene_,
            stop_requested_,
            frame_count_,
            last_frame_seconds_,
            viewport_width_,
            viewport_height_,
            renderer_stats_,
            input_,
            audio_);
    } catch (...) {
        loop_mode_ = LoopMode::None;
        running_.store(false);
        throw;
    }
}

void Engine::end_loop() noexcept {
    window_session_.reset();
    external_window_session_.reset();
    loop_mode_ = LoopMode::None;
    in_tick_ = false;
    running_.store(false);
}

bool Engine::step_window(FrameCallback& frame_callback, const double fps_limit) {
    if (window_session_ == nullptr) {
        throw EngineError("the native window session is not initialized");
    }
    return window_session_->tick(frame_callback, fps_limit);
}

void Engine::run(FrameCallback frame_callback) {
    begin_loop(LoopMode::Managed);
    try {
        while (!stop_requested_.load() &&
               step_window(frame_callback, config_.fps_limit)) {
        }
    } catch (...) {
        end_loop();
        throw;
    }
    end_loop();
}

double Engine::tick(FrameCallback frame_callback, const double fps_limit) {
    if (!std::isfinite(fps_limit) || fps_limit < -1.0) {
        throw std::invalid_argument(
            "tick fps_limit must be None/default, zero (unlimited), or positive");
    }
    if (in_tick_) {
        throw EngineError("recursive tick() is not allowed");
    }
    if (!is_running()) {
        begin_loop(LoopMode::Manual);
    } else if (loop_mode_ != LoopMode::Manual) {
        throw EngineError("cannot call tick() while this Engine is controlled by run()");
    }

    struct TickReset final {
        bool& value;
        ~TickReset() { value = false; }
    } reset{in_tick_};
    in_tick_ = true;
    const double selected_limit = fps_limit < 0.0 ? config_.fps_limit : fps_limit;
    try {
        if (stop_requested_.load() || !step_window(frame_callback, selected_limit)) {
            const double elapsed = last_frame_seconds_.load();
            end_loop();
            return elapsed;
        }
    } catch (...) {
        end_loop();
        throw;
    }
    return last_frame_seconds_.load();
}

void Engine::stop() noexcept {
    stop_requested_.store(true);
}

void Engine::close() {
    if (loop_mode_ == LoopMode::Managed || in_tick_) {
        throw EngineError("cannot close the Engine while a frame loop is active");
    }
    end_loop();
}

void Engine::set_scene(Scene* const scene) {
    if (is_running()) {
        throw EngineError("cannot replace the active scene while the Engine is running");
    }
    scene_ = scene;
}

void Engine::begin_external_window(const std::uintptr_t native_window,
                                   const std::uint32_t width,
                                   const std::uint32_t height) {
    bool expected = false;
    if (!running_.compare_exchange_strong(expected, true)) {
        throw EngineError("cannot attach an external window while the Engine is running");
    }
    stop_requested_.store(false);
    frame_count_.store(0);
    last_frame_seconds_.store(0.0);
    renderer_stats_.reset();
    viewport_width_.store(width);
    viewport_height_.store(height);
    loop_mode_ = LoopMode::External;
    try {
        external_window_session_ = std::make_unique<platform::ExternalWindowSession>(
            native_window, width, height, config_, scene_);
    } catch (...) {
        loop_mode_ = LoopMode::None;
        running_.store(false);
        throw;
    }
}

void Engine::resize_external_window(const std::uint32_t width,
                                    const std::uint32_t height) {
    if (loop_mode_ != LoopMode::External || external_window_session_ == nullptr) {
        throw EngineError("no external window is attached");
    }
    external_window_session_->resize(width, height);
    viewport_width_.store(width);
    viewport_height_.store(height);
}

void Engine::render_external_window() {
    if (loop_mode_ != LoopMode::External || external_window_session_ == nullptr) {
        throw EngineError("no external window is attached");
    }
    if (stop_requested_.load()) return;
    renderer_stats_.store(external_window_session_->render());
    frame_count_.fetch_add(1);
}

void Engine::render_external_offscreen() {
    if (loop_mode_ != LoopMode::External || external_window_session_ == nullptr) {
        throw EngineError("no external window is attached");
    }
    if (stop_requested_.load()) return;
    renderer_stats_.store(external_window_session_->render_offscreen());
    frame_count_.fetch_add(1);
}

std::vector<std::uint8_t> Engine::readback_external_window_rgba8() {
    if (loop_mode_ != LoopMode::External || external_window_session_ == nullptr) {
        throw EngineError("no external window is attached");
    }
    return external_window_session_->readback_rgba8();
}

std::vector<std::uint8_t> Engine::render_external_viewport_rgba8(
    const Camera& camera,
    const std::uint32_t width,
    const std::uint32_t height) {
    if (loop_mode_ != LoopMode::External || external_window_session_ == nullptr) {
        throw EngineError("no external window is attached");
    }
    auto pixels = external_window_session_->render_viewport_rgba8(camera, width, height);
    renderer_stats_.store(external_window_session_->stats());
    return pixels;
}

std::uint64_t Engine::request_external_viewport_rgba8(
    const Camera& camera,
    const std::uint32_t width,
    const std::uint32_t height) {
    if (loop_mode_ != LoopMode::External || external_window_session_ == nullptr) {
        throw EngineError("no external window is attached");
    }
    const std::uint64_t request =
        external_window_session_->request_viewport_rgba8(camera, width, height);
    renderer_stats_.store(external_window_session_->stats());
    return request;
}

std::optional<std::vector<std::uint8_t>> Engine::poll_external_viewport_rgba8(
    const std::uint64_t request_id) {
    if (loop_mode_ != LoopMode::External || external_window_session_ == nullptr) {
        throw EngineError("no external window is attached");
    }
    return external_window_session_->poll_viewport_rgba8(request_id);
}

std::vector<std::uint8_t> Engine::wait_external_viewport_rgba8(
    const std::uint64_t request_id) {
    if (loop_mode_ != LoopMode::External || external_window_session_ == nullptr) {
        throw EngineError("no external window is attached");
    }
    return external_window_session_->wait_viewport_rgba8(request_id);
}

void Engine::cancel_external_viewport_rgba8(const std::uint64_t request_id) noexcept {
    if (loop_mode_ == LoopMode::External && external_window_session_ != nullptr) {
        external_window_session_->cancel_viewport_rgba8(request_id);
    }
}

void Engine::end_external_window() noexcept {
    if (loop_mode_ == LoopMode::External) end_loop();
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

