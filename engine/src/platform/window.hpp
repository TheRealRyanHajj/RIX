#pragma once

#include "easy3d/core.hpp"

#include <atomic>
#include <cstdint>
#include <memory>
#include <optional>
#include <vector>

namespace easy3d::platform {

class WindowSession final {
public:
    WindowSession(const EngineConfig& config,
                  const Scene* scene,
                  const std::atomic_bool& stop_requested,
                  std::atomic_uint64_t& frame_count,
                  std::atomic<double>& last_frame_seconds,
                  std::atomic_uint32_t& viewport_width,
                  std::atomic_uint32_t& viewport_height,
                  RendererStatsAtomic& renderer_stats,
                  InputSystem& input,
                  AudioSystem& audio);
    ~WindowSession();

    WindowSession(const WindowSession&) = delete;
    WindowSession& operator=(const WindowSession&) = delete;
    WindowSession(WindowSession&&) = delete;
    WindowSession& operator=(WindowSession&&) = delete;

    [[nodiscard]] bool tick(Engine::FrameCallback& frame_callback, double fps_limit);

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

class ExternalWindowSession final {
public:
    ExternalWindowSession(std::uintptr_t native_window,
                          std::uint32_t width,
                          std::uint32_t height,
                          const EngineConfig& config,
                          const Scene* scene);
    ~ExternalWindowSession();

    ExternalWindowSession(const ExternalWindowSession&) = delete;
    ExternalWindowSession& operator=(const ExternalWindowSession&) = delete;
    ExternalWindowSession(ExternalWindowSession&&) = delete;
    ExternalWindowSession& operator=(ExternalWindowSession&&) = delete;

    void resize(std::uint32_t width, std::uint32_t height);
    [[nodiscard]] RendererStats render();
    [[nodiscard]] RendererStats render_offscreen();
    [[nodiscard]] std::vector<std::uint8_t> readback_rgba8();
    [[nodiscard]] std::vector<std::uint8_t> render_viewport_rgba8(
        const Camera& camera,
        std::uint32_t width,
        std::uint32_t height);
    [[nodiscard]] std::uint64_t request_viewport_rgba8(
        const Camera& camera,
        std::uint32_t width,
        std::uint32_t height);
    [[nodiscard]] std::optional<std::vector<std::uint8_t>> poll_viewport_rgba8(
        std::uint64_t request_id);
    [[nodiscard]] std::vector<std::uint8_t> wait_viewport_rgba8(
        std::uint64_t request_id);
    void cancel_viewport_rgba8(std::uint64_t request_id) noexcept;
    [[nodiscard]] RendererStats stats() const noexcept;

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace easy3d::platform

