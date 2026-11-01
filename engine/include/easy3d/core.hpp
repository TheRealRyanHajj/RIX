#pragma once

#include <atomic>
#include <cstdint>
#include <stdexcept>
#include <string>

namespace easy3d {

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
    // Native validation scene used by renderer diagnostics. Ordinary Game
    // instances leave this disabled and retain the blank-window behavior.
    bool geometry_diagnostic{false};
};

class Engine final {
public:
    explicit Engine(EngineConfig config = {});

    Engine(const Engine&) = delete;
    Engine& operator=(const Engine&) = delete;
    Engine(Engine&&) = delete;
    Engine& operator=(Engine&&) = delete;
    ~Engine() = default;

    void run();
    void stop() noexcept;

    [[nodiscard]] bool is_running() const noexcept;
    [[nodiscard]] std::uint64_t frame_count() const noexcept;
    [[nodiscard]] double last_frame_seconds() const noexcept;
    [[nodiscard]] const EngineConfig& config() const noexcept;

private:
    EngineConfig config_;
    std::atomic_bool running_{false};
    std::atomic_bool stop_requested_{false};
    std::atomic_uint64_t frame_count_{0};
    std::atomic<double> last_frame_seconds_{0.0};
};

} // namespace easy3d

