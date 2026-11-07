#pragma once

#include "easy3d/input.hpp"
#include "easy3d/audio.hpp"

#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>

namespace easy3d {

namespace platform {
class WindowSession;
class ExternalWindowSession;
}

class Scene;
struct Camera;

enum class GraphicsPreset {
    Low,
    Medium,
    High,
    Ultra,
};

struct GraphicsFeatures final {
    bool enhanced_lighting{true};
    bool shadows{false};
    bool postprocessing{false};
    bool fxaa{false};
    std::uint16_t shadow_resolution{0};
    std::uint16_t max_directional_lights{2};
    std::uint16_t max_point_lights{16};
    std::uint16_t max_spot_lights{8};

    friend bool operator==(const GraphicsFeatures&, const GraphicsFeatures&) = default;
};

[[nodiscard]] const char* graphics_preset_name(GraphicsPreset preset) noexcept;
[[nodiscard]] GraphicsFeatures graphics_features(GraphicsPreset preset) noexcept;

[[nodiscard]] const char* engine_version() noexcept;
[[nodiscard]] int native_add(int left, int right) noexcept;

class EngineError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct EngineConfig {
    std::string title{"RIX"};
    std::uint32_t width{1280};
    std::uint32_t height{720};
    bool vsync{true};
    double fps_limit{0.0};
    GraphicsPreset graphics_preset{GraphicsPreset::Medium};
    // Native validation scene used only by the opt-in geometry diagnostic.
    bool geometry_diagnostic{false};
};

struct RendererStats final {
    std::uint64_t draw_calls{0};
    std::uint64_t visible_instances{0};
    std::uint64_t culled_instances{0};
    std::uint64_t instanced_draw_calls{0};
    std::uint64_t ui_draw_calls{0};
    std::uint64_t ui_elements{0};
    bool enhanced_lighting{false};
    bool shadows{false};
    bool postprocessing{false};
    bool fxaa{false};
    std::uint32_t shadow_resolution{0};
    double cpu_frame_ms{0.0};
    double gpu_frame_ms{0.0};
    std::uint64_t texture_count{0};
    std::uint64_t texture_memory_bytes{0};
    std::uint32_t active_directional_lights{0};
    std::uint32_t active_point_lights{0};
    std::uint32_t active_spot_lights{0};
    std::uint32_t culled_lights{0};
    std::uint32_t shadow_passes{0};
    std::uint32_t active_shadow_casters{0};
    std::uint32_t dropped_shadow_casters{0};
    std::uint64_t shadow_memory_bytes{0};

    friend bool operator==(const RendererStats&, const RendererStats&) = default;
};

class RendererStatsAtomic final {
public:
    void reset() noexcept;
    void store(RendererStats stats) noexcept;
    [[nodiscard]] RendererStats load() const noexcept;

private:
    std::atomic_uint64_t sequence_{0};
    std::atomic_uint64_t draw_calls_{0};
    std::atomic_uint64_t visible_instances_{0};
    std::atomic_uint64_t culled_instances_{0};
    std::atomic_uint64_t instanced_draw_calls_{0};
    std::atomic_uint64_t ui_draw_calls_{0};
    std::atomic_uint64_t ui_elements_{0};
    std::atomic_bool enhanced_lighting_{false};
    std::atomic_bool shadows_{false};
    std::atomic_bool postprocessing_{false};
    std::atomic_bool fxaa_{false};
    std::atomic_uint32_t shadow_resolution_{0};
    std::atomic<double> cpu_frame_ms_{0.0};
    std::atomic<double> gpu_frame_ms_{0.0};
    std::atomic_uint64_t texture_count_{0};
    std::atomic_uint64_t texture_memory_bytes_{0};
    std::atomic_uint32_t active_directional_lights_{0};
    std::atomic_uint32_t active_point_lights_{0};
    std::atomic_uint32_t active_spot_lights_{0};
    std::atomic_uint32_t culled_lights_{0};
    std::atomic_uint32_t shadow_passes_{0};
    std::atomic_uint32_t active_shadow_casters_{0};
    std::atomic_uint32_t dropped_shadow_casters_{0};
    std::atomic_uint64_t shadow_memory_bytes_{0};
};

class Engine final {
public:
    using FrameCallback = std::function<void(double)>;
    explicit Engine(EngineConfig config = {});

    Engine(const Engine&) = delete;
    Engine& operator=(const Engine&) = delete;
    Engine(Engine&&) = delete;
    Engine& operator=(Engine&&) = delete;
    ~Engine();

    void run(FrameCallback frame_callback = {});
    [[nodiscard]] double tick(FrameCallback frame_callback = {}, double fps_limit = -1.0);
    void stop() noexcept;
    void close();
    void set_scene(Scene* scene);
    void begin_external_window(std::uintptr_t native_window,
                               std::uint32_t width,
                               std::uint32_t height);
    void resize_external_window(std::uint32_t width, std::uint32_t height);
    void render_external_window();
    void render_external_offscreen();
    [[nodiscard]] std::vector<std::uint8_t> readback_external_window_rgba8();
    [[nodiscard]] std::vector<std::uint8_t> render_external_viewport_rgba8(
        const Camera& camera,
        std::uint32_t width,
        std::uint32_t height);
    [[nodiscard]] std::uint64_t request_external_viewport_rgba8(
        const Camera& camera,
        std::uint32_t width,
        std::uint32_t height);
    [[nodiscard]] std::optional<std::vector<std::uint8_t>>
        poll_external_viewport_rgba8(std::uint64_t request_id);
    [[nodiscard]] std::vector<std::uint8_t> wait_external_viewport_rgba8(
        std::uint64_t request_id);
    void cancel_external_viewport_rgba8(std::uint64_t request_id) noexcept;
    void end_external_window() noexcept;

    [[nodiscard]] bool is_running() const noexcept;
    [[nodiscard]] std::uint64_t frame_count() const noexcept;
    [[nodiscard]] double last_frame_seconds() const noexcept;
    [[nodiscard]] std::pair<std::uint32_t, std::uint32_t> viewport_size() const noexcept;
    [[nodiscard]] RendererStats renderer_stats() const noexcept;
    [[nodiscard]] InputSystem& input() noexcept;
    [[nodiscard]] const InputSystem& input() const noexcept;
    [[nodiscard]] AudioSystem& audio() noexcept;
    [[nodiscard]] const AudioSystem& audio() const noexcept;
    [[nodiscard]] const EngineConfig& config() const noexcept;

private:
    enum class LoopMode {
        None,
        Managed,
        Manual,
        External,
    };

    void begin_loop(LoopMode mode);
    void end_loop() noexcept;
    [[nodiscard]] bool step_window(FrameCallback& frame_callback, double fps_limit);

    EngineConfig config_;
    std::atomic_bool running_{false};
    std::atomic_bool stop_requested_{false};
    std::atomic_uint64_t frame_count_{0};
    std::atomic<double> last_frame_seconds_{0.0};
    std::atomic_uint32_t viewport_width_{1};
    std::atomic_uint32_t viewport_height_{1};
    RendererStatsAtomic renderer_stats_;
    InputSystem input_;
    AudioSystem audio_;
    Scene* scene_{nullptr};
    std::unique_ptr<platform::WindowSession> window_session_;
    std::unique_ptr<platform::ExternalWindowSession> external_window_session_;
    LoopMode loop_mode_{LoopMode::None};
    bool in_tick_{false};
};

} // namespace easy3d

