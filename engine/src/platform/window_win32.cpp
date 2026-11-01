#include "platform/window.hpp"
#include "renderer/bgfx_renderer.hpp"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>

#include <SDL3/SDL.h>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <memory>
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

    renderer::BgfxRenderer renderer(native_window,
                                    static_cast<std::uint32_t>(std::max(pixel_width, 1)),
                                    static_cast<std::uint32_t>(std::max(pixel_height, 1)),
                                    config.vsync,
                                    config.geometry_diagnostic);

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

