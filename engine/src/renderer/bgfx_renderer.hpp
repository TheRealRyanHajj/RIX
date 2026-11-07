#pragma once

#include "easy3d/core.hpp"

#include <cstdint>
#include <memory>
#include <optional>
#include <vector>

namespace easy3d {
struct Camera;
class Scene;
}

namespace easy3d::renderer {

class BgfxRenderer final {
public:
    BgfxRenderer(void* native_window,
                 std::uint32_t width,
                 std::uint32_t height,
                 bool vsync,
                 GraphicsPreset graphics_preset,
                 bool geometry_diagnostic,
                 const Scene* scene);
    ~BgfxRenderer();

    BgfxRenderer(const BgfxRenderer&) = delete;
    BgfxRenderer& operator=(const BgfxRenderer&) = delete;
    BgfxRenderer(BgfxRenderer&&) = delete;
    BgfxRenderer& operator=(BgfxRenderer&&) = delete;

    void resize(std::uint32_t width, std::uint32_t height);
    void present();
    void render_offscreen();
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

} // namespace easy3d::renderer
