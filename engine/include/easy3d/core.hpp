#pragma once

#include "easy3d/input.hpp"

#include <atomic>
#include <cstdint>
#include <functional>
#include <stdexcept>
#include <string>

namespace easy3d {

class Scene;

[[nodiscard]] const char* engine_version() noexcept;
[[nodiscard]] int native_add(int left, int right) noexcept;

class EngineError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct EngineConfig {
    std::string title{"Easy3D"};
    std::uint32_t width{1280};
    std::uint32_t height{720};
    bool vsync{true};
    double fps_limit{0.0};
    // Native validation scene used only by the opt-in geometry diagnostic.
    bool geometry_diagnostic{false};
};

struct RendererStats final {
    std::uint64_t draw_calls{0};
    std::uint64_t visible_instances{0};
    std::uint64_t culled_instances{0};
    std::uint64_t instanced_draw_calls{0};

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
};

class Engine final {
public:
    using FrameCallback = std::function<void(double)>;
    explicit Engine(EngineConfig config = {});

    Engine(const Engine&) = delete;
    Engine& operator=(const Engine&) = delete;
    Engine(Engine&&) = delete;
    Engine& operator=(Engine&&) = delete;
    ~Engine() = default;

    void run(FrameCallback frame_callback = {});
    void stop() noexcept;
    void set_scene(Scene* scene);

    [[nodiscard]] bool is_running() const noexcept;
    [[nodiscard]] std::uint64_t frame_count() const noexcept;
    [[nodiscard]] double last_frame_seconds() const noexcept;
    [[nodiscard]] RendererStats renderer_stats() const noexcept;
    [[nodiscard]] InputSystem& input() noexcept;
    [[nodiscard]] const InputSystem& input() const noexcept;
    [[nodiscard]] const EngineConfig& config() const noexcept;

private:
    EngineConfig config_;
    std::atomic_bool running_{false};
    std::atomic_bool stop_requested_{false};
    std::atomic_uint64_t frame_count_{0};
    std::atomic<double> last_frame_seconds_{0.0};
    RendererStatsAtomic renderer_stats_;
    InputSystem input_;
    Scene* scene_{nullptr};
};

} // namespace easy3d

