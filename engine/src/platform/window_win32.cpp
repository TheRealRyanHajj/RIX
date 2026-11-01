#include "platform/window.hpp"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>

#include <SDL3/SDL.h>
#include <bgfx/bgfx.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>

namespace easy3d::platform {
namespace {

[[nodiscard]] std::string sdl_error(const char* action) {
    return std::string(action) + ": " + SDL_GetError();
}

class SdlVideo final {
public:
    SdlVideo() {
        if (!SDL_Init(SDL_INIT_VIDEO)) {
            throw EngineError(sdl_error("SDL video initialization failed"));
        }
    }

    ~SdlVideo() { SDL_Quit(); }
    SdlVideo(const SdlVideo&) = delete;
    SdlVideo& operator=(const SdlVideo&) = delete;
};

struct WindowDeleter {
    void operator()(SDL_Window* window) const noexcept { SDL_DestroyWindow(window); }
};

class BgfxContext final {
public:
    BgfxContext(void* native_window,
                const std::uint32_t width,
                const std::uint32_t height,
                const bool vsync) {
        // Keep device and swap-chain work on the SDL/window thread. Calling
        // renderFrame before init selects bgfx's supported single-threaded
        // mode, which is important for externally owned Win32 HWNDs.
        bgfx::renderFrame();

        bgfx::Init init;
        init.type = bgfx::RendererType::Direct3D11;
        init.fallback = false;
        init.swapChain.nwh = native_window;
        init.swapChain.width = width;
        init.swapChain.height = height;

        // Preserve bgfx::Init's complete swap-chain defaults (including the
        // BGRA8/D24S8 formats and double buffering) for later resize resets.
        // A standalone bgfx::SwapChain defaults its formats to Count and is
        // not a complete primary swap-chain description.
        swap_chain_ = init.swapChain;
        reset_flags_ = vsync ? BGFX_RESET_VSYNC : BGFX_RESET_NONE;
        init.reset = reset_flags_;

        if (!bgfx::init(init)) {
            throw EngineError("bgfx failed to initialize the Direct3D 11 renderer");
        }
        initialized_ = true;

        const bgfx::Caps* caps = bgfx::getCaps();
        std::ostringstream message;
        message << "Easy3D renderer: " << bgfx::getRendererName(bgfx::getRendererType())
                << ", vendor=0x" << std::hex << std::setw(4) << std::setfill('0')
                << caps->vendorId << ", device=0x" << std::setw(4) << caps->deviceId;
        std::cout << message.str() << std::dec << std::endl;

        bgfx::setViewClear(0, BGFX_CLEAR_COLOR | BGFX_CLEAR_DEPTH, 0x28344bff, 1.0F, 0);
        width_ = std::max(width, 1U);
        height_ = std::max(height, 1U);
        bgfx::setViewRect(0,
                          0,
                          0,
                          static_cast<std::uint16_t>(width_),
                          static_cast<std::uint16_t>(height_));
    }

    ~BgfxContext() {
        if (initialized_) {
            bgfx::shutdown();
        }
    }

    BgfxContext(const BgfxContext&) = delete;
    BgfxContext& operator=(const BgfxContext&) = delete;

    void resize(const std::uint32_t width, const std::uint32_t height) {
        width_ = std::max(width, 1U);
        height_ = std::max(height, 1U);
        swap_chain_.width = width_;
        swap_chain_.height = height_;
        bgfx::reset(reset_flags_, &swap_chain_);
        bgfx::setViewRect(0,
                          0,
                          0,
                          static_cast<std::uint16_t>(width_),
                          static_cast<std::uint16_t>(height_));
    }

    void present() {
        bgfx::touch(0);
        bgfx::frame();
    }

private:
    bool initialized_{false};
    std::uint32_t reset_flags_{BGFX_RESET_NONE};
    std::uint32_t width_{1};
    std::uint32_t height_{1};
    bgfx::SwapChain swap_chain_{};
};

} // namespace

void run_window_loop(const EngineConfig& config,
                     const std::atomic_bool& stop_requested,
                     std::atomic_uint64_t& frame_count,
                     std::atomic<double>& last_frame_seconds) {
    SdlVideo sdl;

    const auto flags = static_cast<SDL_WindowFlags>(SDL_WINDOW_RESIZABLE |
                                                    SDL_WINDOW_HIGH_PIXEL_DENSITY);
    std::unique_ptr<SDL_Window, WindowDeleter> window(
        SDL_CreateWindow(config.title.c_str(),
                         static_cast<int>(config.width),
                         static_cast<int>(config.height),
                         flags));
    if (!window) {
        throw EngineError(sdl_error("SDL window creation failed"));
    }

    void* native_window = SDL_GetPointerProperty(SDL_GetWindowProperties(window.get()),
                                                 SDL_PROP_WINDOW_WIN32_HWND_POINTER,
                                                 nullptr);
    if (native_window == nullptr) {
        throw EngineError(sdl_error("SDL did not provide a Win32 HWND"));
    }
    const auto hwnd = static_cast<HWND>(native_window);
    if (!IsWindow(hwnd)) {
        throw EngineError("SDL provided an invalid Win32 HWND");
    }

    RECT client_rect{};
    if (!GetClientRect(hwnd, &client_rect)) {
        throw EngineError("Windows could not query the SDL window client area");
    }
    int pixel_width = 0;
    int pixel_height = 0;
    if (!SDL_GetWindowSizeInPixels(window.get(), &pixel_width, &pixel_height)) {
        throw EngineError(sdl_error("SDL could not query the window pixel size"));
    }

    BgfxContext renderer(native_window,
                         static_cast<std::uint32_t>(std::max(pixel_width, 1)),
                         static_cast<std::uint32_t>(std::max(pixel_height, 1)),
                         config.vsync);

    using Clock = std::chrono::steady_clock;
    const auto minimum_frame = config.fps_limit > 0.0
                                   ? std::chrono::duration_cast<Clock::duration>(
                                         std::chrono::duration<double>(1.0 / config.fps_limit))
                                   : Clock::duration::zero();
    auto previous_frame = Clock::now();
    const SDL_WindowID window_id = SDL_GetWindowID(window.get());

    while (!stop_requested.load()) {
        const auto frame_start = Clock::now();
        last_frame_seconds.store(std::chrono::duration<double>(frame_start - previous_frame).count());
        previous_frame = frame_start;

        SDL_Event event{};
        bool quit = false;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT ||
                (event.type == SDL_EVENT_KEY_DOWN && event.key.scancode == SDL_SCANCODE_ESCAPE)) {
                quit = true;
            }
            if ((event.type == SDL_EVENT_WINDOW_RESIZED ||
                 event.type == SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED) &&
                event.window.windowID == window_id) {
                if (SDL_GetWindowSizeInPixels(window.get(), &pixel_width, &pixel_height)) {
                    renderer.resize(static_cast<std::uint32_t>(std::max(pixel_width, 1)),
                                    static_cast<std::uint32_t>(std::max(pixel_height, 1)));
                }
            }
        }
        if (quit) {
            break;
        }

        renderer.present();
        frame_count.fetch_add(1);

        if (minimum_frame != Clock::duration::zero()) {
            std::this_thread::sleep_until(frame_start + minimum_frame);
        }
    }
}

} // namespace easy3d::platform

