#pragma once

#include <cstdint>
#include <memory>

namespace easy3d::renderer {

class BgfxRenderer final {
public:
    BgfxRenderer(void* native_window,
                 std::uint32_t width,
                 std::uint32_t height,
                 bool vsync,
                 bool geometry_diagnostic);
    ~BgfxRenderer();

    BgfxRenderer(const BgfxRenderer&) = delete;
    BgfxRenderer& operator=(const BgfxRenderer&) = delete;
    BgfxRenderer(BgfxRenderer&&) = delete;
    BgfxRenderer& operator=(BgfxRenderer&&) = delete;

    void resize(std::uint32_t width, std::uint32_t height);
    void present();

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace easy3d::renderer
