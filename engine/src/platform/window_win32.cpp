#include "platform/window.hpp"
#include "renderer/bgfx_renderer.hpp"
#include "easy3d/scene.hpp"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>

#include <SDL3/SDL.h>
#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstdint>
#include <memory>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

namespace easy3d::platform {
namespace {

[[nodiscard]] std::string sdl_error(const char* action) {
    return std::string(action) + ": " + SDL_GetError();
}

class SdlVideo final {
public:
    SdlVideo() {
        if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMEPAD)) {
            throw EngineError(sdl_error("SDL video/gamepad initialization failed"));
        }
        if (!SDL_InitSubSystem(SDL_INIT_AUDIO)) {
            std::cerr << "Easy3D audio: SDL audio initialization unavailable ("
                      << SDL_GetError() << ")\n";
        }
    }

    ~SdlVideo() { SDL_Quit(); }
    SdlVideo(const SdlVideo&) = delete;
    SdlVideo& operator=(const SdlVideo&) = delete;
};

struct WindowDeleter {
    void operator()(SDL_Window* window) const noexcept { SDL_DestroyWindow(window); }
};

struct GamepadDeleter {
    void operator()(SDL_Gamepad* gamepad) const noexcept { SDL_CloseGamepad(gamepad); }
};

void SDLCALL fill_audio(void* const userdata,
                        SDL_AudioStream* const stream,
                        const int additional_amount,
                        const int) {
    if (userdata == nullptr || additional_amount <= 0) {
        return;
    }
    constexpr std::size_t channels = 2;
    constexpr std::uint32_t sample_rate = 48'000;
    const std::size_t frame_count = static_cast<std::size_t>(additional_amount) /
                                    (sizeof(float) * channels);
    if (frame_count == 0) {
        return;
    }
    try {
        thread_local std::vector<float> buffer;
        buffer.resize(frame_count * channels);
        static_cast<AudioSystem*>(userdata)->mix(buffer.data(), frame_count, sample_rate);
        (void)SDL_PutAudioStreamData(
            stream, buffer.data(), static_cast<int>(buffer.size() * sizeof(float)));
    } catch (...) {
        // Exceptions must never cross SDL's native audio callback boundary.
    }
}

class SdlAudioOutput final {
public:
    explicit SdlAudioOutput(AudioSystem& audio) : audio_(audio) {
        const SDL_AudioSpec spec{SDL_AUDIO_F32, 2, 48'000};
        stream_ = SDL_OpenAudioDeviceStream(
            SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec, fill_audio, &audio_);
        if (stream_ == nullptr) {
            std::cerr << "Easy3D audio: unavailable (" << SDL_GetError() << ")\n";
            return;
        }
        if (!SDL_ResumeAudioStreamDevice(stream_)) {
            std::cerr << "Easy3D audio: could not start (" << SDL_GetError() << ")\n";
            SDL_DestroyAudioStream(stream_);
            stream_ = nullptr;
            return;
        }
        audio_.set_backend_active(true);
        std::cout << "Easy3D audio: SDL3 default playback, 48000 Hz stereo float\n";
    }

    ~SdlAudioOutput() {
        audio_.set_backend_active(false);
        if (stream_ != nullptr) {
            SDL_DestroyAudioStream(stream_);
        }
    }
    SdlAudioOutput(const SdlAudioOutput&) = delete;
    SdlAudioOutput& operator=(const SdlAudioOutput&) = delete;

private:
    AudioSystem& audio_;
    SDL_AudioStream* stream_{nullptr};
};

[[nodiscard]] std::string canonical_name(const std::string_view device,
                                         const char* const value) {
    std::string result(device);
    result.push_back(':');
    for (const unsigned char character : std::string_view(value == nullptr ? "" : value)) {
        if (std::isalnum(character) != 0) {
            result.push_back(static_cast<char>(std::tolower(character)));
        } else if (result.back() != '_') {
            result.push_back('_');
        }
    }
    while (result.ends_with('_')) {
        result.pop_back();
    }
    return result;
}

[[nodiscard]] std::string canonical_key(const SDL_Scancode scancode) {
    switch (scancode) {
    case SDL_SCANCODE_APOSTROPHE:
        return "key:apostrophe";
    case SDL_SCANCODE_COMMA:
        return "key:comma";
    case SDL_SCANCODE_MINUS:
        return "key:minus";
    case SDL_SCANCODE_PERIOD:
        return "key:period";
    case SDL_SCANCODE_SLASH:
        return "key:slash";
    case SDL_SCANCODE_SEMICOLON:
        return "key:semicolon";
    case SDL_SCANCODE_EQUALS:
        return "key:equals";
    case SDL_SCANCODE_LEFTBRACKET:
        return "key:left_bracket";
    case SDL_SCANCODE_BACKSLASH:
        return "key:backslash";
    case SDL_SCANCODE_RIGHTBRACKET:
        return "key:right_bracket";
    case SDL_SCANCODE_GRAVE:
        return "key:grave";
    default:
        break;
    }
    std::string result = canonical_name("key", SDL_GetScancodeName(scancode));
    if (result.ends_with(':')) {
        result += "scancode_" + std::to_string(static_cast<int>(scancode));
    }
    return result;
}

[[nodiscard]] const char* mouse_button_name(const std::uint8_t button) noexcept {
    switch (button) {
    case SDL_BUTTON_LEFT:
        return "left";
    case SDL_BUTTON_MIDDLE:
        return "middle";
    case SDL_BUTTON_RIGHT:
        return "right";
    case SDL_BUTTON_X1:
        return "x1";
    case SDL_BUTTON_X2:
        return "x2";
    default:
        return nullptr;
    }
}

[[nodiscard]] const char* gamepad_button_name(const SDL_GamepadButton button) noexcept {
    switch (button) {
    case SDL_GAMEPAD_BUTTON_SOUTH:
        return "a";
    case SDL_GAMEPAD_BUTTON_EAST:
        return "b";
    case SDL_GAMEPAD_BUTTON_WEST:
        return "x";
    case SDL_GAMEPAD_BUTTON_NORTH:
        return "y";
    case SDL_GAMEPAD_BUTTON_BACK:
        return "back";
    case SDL_GAMEPAD_BUTTON_GUIDE:
        return "guide";
    case SDL_GAMEPAD_BUTTON_START:
        return "start";
    case SDL_GAMEPAD_BUTTON_LEFT_STICK:
        return "left_stick";
    case SDL_GAMEPAD_BUTTON_RIGHT_STICK:
        return "right_stick";
    case SDL_GAMEPAD_BUTTON_LEFT_SHOULDER:
        return "left_shoulder";
    case SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER:
        return "right_shoulder";
    case SDL_GAMEPAD_BUTTON_DPAD_UP:
        return "dpad_up";
    case SDL_GAMEPAD_BUTTON_DPAD_DOWN:
        return "dpad_down";
    case SDL_GAMEPAD_BUTTON_DPAD_LEFT:
        return "dpad_left";
    case SDL_GAMEPAD_BUTTON_DPAD_RIGHT:
        return "dpad_right";
    case SDL_GAMEPAD_BUTTON_MISC1:
        return "misc1";
    case SDL_GAMEPAD_BUTTON_RIGHT_PADDLE1:
        return "right_paddle1";
    case SDL_GAMEPAD_BUTTON_LEFT_PADDLE1:
        return "left_paddle1";
    case SDL_GAMEPAD_BUTTON_RIGHT_PADDLE2:
        return "right_paddle2";
    case SDL_GAMEPAD_BUTTON_LEFT_PADDLE2:
        return "left_paddle2";
    case SDL_GAMEPAD_BUTTON_TOUCHPAD:
        return "touchpad";
    default:
        return nullptr;
    }
}

[[nodiscard]] const char* gamepad_axis_name(const SDL_GamepadAxis axis) noexcept {
    switch (axis) {
    case SDL_GAMEPAD_AXIS_LEFTX:
        return "left_x";
    case SDL_GAMEPAD_AXIS_LEFTY:
        return "left_y";
    case SDL_GAMEPAD_AXIS_RIGHTX:
        return "right_x";
    case SDL_GAMEPAD_AXIS_RIGHTY:
        return "right_y";
    case SDL_GAMEPAD_AXIS_LEFT_TRIGGER:
        return "left_trigger";
    case SDL_GAMEPAD_AXIS_RIGHT_TRIGGER:
        return "right_trigger";
    default:
        return nullptr;
    }
}

[[nodiscard]] float normalized_axis(const SDL_GamepadAxis axis,
                                    const std::int16_t value) noexcept {
    if (axis == SDL_GAMEPAD_AXIS_LEFT_TRIGGER ||
        axis == SDL_GAMEPAD_AXIS_RIGHT_TRIGGER) {
        return std::clamp(static_cast<float>(value) / 32767.0F, 0.0F, 1.0F);
    }
    return value < 0 ? static_cast<float>(value) / 32768.0F
                     : static_cast<float>(value) / 32767.0F;
}

} // namespace

void run_window_loop(const EngineConfig& config,
                     const Scene* const scene,
                     const std::atomic_bool& stop_requested,
                     std::atomic_uint64_t& frame_count,
                     std::atomic<double>& last_frame_seconds,
                     std::atomic_uint32_t& viewport_width,
                     std::atomic_uint32_t& viewport_height,
                     RendererStatsAtomic& renderer_stats,
                     InputSystem& input,
                     AudioSystem& audio,
                     Engine::FrameCallback frame_callback) {
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
    input.set_focused(
        (SDL_GetWindowFlags(window.get()) & SDL_WINDOW_INPUT_FOCUS) != 0);
    (void)SDL_RaiseWindow(window.get());

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
    int logical_width = 0;
    int logical_height = 0;
    if (!SDL_GetWindowSize(window.get(), &logical_width, &logical_height)) {
        throw EngineError(sdl_error("SDL could not query the logical window size"));
    }
    if (!SDL_GetWindowSizeInPixels(window.get(), &pixel_width, &pixel_height)) {
        throw EngineError(sdl_error("SDL could not query the window pixel size"));
    }
    viewport_width.store(static_cast<std::uint32_t>(std::max(pixel_width, 1)));
    viewport_height.store(static_cast<std::uint32_t>(std::max(pixel_height, 1)));

    renderer::BgfxRenderer renderer(native_window,
                                    static_cast<std::uint32_t>(std::max(pixel_width, 1)),
                                    static_cast<std::uint32_t>(std::max(pixel_height, 1)),
                                    config.vsync,
                                    config.graphics_preset,
                                    config.geometry_diagnostic,
                                    scene);
    if (scene != nullptr && scene->active()) {
        audio.set_listener(scene->camera().position, scene->camera().right());
    }
    SdlAudioOutput audio_output(audio);

    using Clock = std::chrono::steady_clock;
    const auto minimum_frame = config.fps_limit > 0.0
                                   ? std::chrono::duration_cast<Clock::duration>(
                                         std::chrono::duration<double>(1.0 / config.fps_limit))
                                   : Clock::duration::zero();
    auto previous_frame = Clock::now();
    const SDL_WindowID window_id = SDL_GetWindowID(window.get());
    std::unique_ptr<SDL_Gamepad, GamepadDeleter> gamepad;
    SDL_JoystickID gamepad_id = 0;
    bool applied_pointer_lock = false;

    const auto open_gamepad = [&](const SDL_JoystickID id) {
        if (gamepad) {
            return;
        }
        gamepad.reset(SDL_OpenGamepad(id));
        if (!gamepad) {
            return;
        }
        gamepad_id = SDL_GetGamepadID(gamepad.get());
        const char* name = SDL_GetGamepadName(gamepad.get());
        input.set_gamepad_connected(true, name == nullptr ? "Gamepad" : name);
    };

    while (!stop_requested.load()) {
        const auto frame_start = Clock::now();
        last_frame_seconds.store(std::chrono::duration<double>(frame_start - previous_frame).count());
        previous_frame = frame_start;

        input.begin_frame();
        SDL_Event event{};
        bool quit = false;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT ||
                (event.type == SDL_EVENT_KEY_DOWN && event.key.scancode == SDL_SCANCODE_ESCAPE)) {
                quit = true;
            }
            if ((event.type == SDL_EVENT_KEY_DOWN || event.type == SDL_EVENT_KEY_UP) &&
                event.key.windowID == window_id && !event.key.repeat) {
                input.set_control(canonical_key(event.key.scancode),
                                  event.key.down ? 1.0F : 0.0F);
            }
            if (event.type == SDL_EVENT_MOUSE_MOTION && event.motion.windowID == window_id) {
                const float scale_x = static_cast<float>(std::max(pixel_width, 1)) /
                                      static_cast<float>(std::max(logical_width, 1));
                const float scale_y = static_cast<float>(std::max(pixel_height, 1)) /
                                      static_cast<float>(std::max(logical_height, 1));
                input.add_pointer_motion(event.motion.x * scale_x,
                                         event.motion.y * scale_y,
                                         event.motion.xrel * scale_x,
                                         event.motion.yrel * scale_y);
            }
            if ((event.type == SDL_EVENT_MOUSE_BUTTON_DOWN ||
                 event.type == SDL_EVENT_MOUSE_BUTTON_UP) &&
                event.button.windowID == window_id) {
                if (const char* name = mouse_button_name(event.button.button); name != nullptr) {
                    input.set_control(canonical_name("mouse", name),
                                      event.button.down ? 1.0F : 0.0F);
                }
            }
            if (event.type == SDL_EVENT_MOUSE_WHEEL && event.wheel.windowID == window_id) {
                input.add_wheel(event.wheel.x, event.wheel.y);
            }
            if (event.type == SDL_EVENT_WINDOW_FOCUS_GAINED &&
                event.window.windowID == window_id) {
                input.set_focused(true);
            }
            if (event.type == SDL_EVENT_WINDOW_FOCUS_LOST &&
                event.window.windowID == window_id) {
                input.set_focused(false);
            }
            if (event.type == SDL_EVENT_GAMEPAD_ADDED) {
                open_gamepad(event.gdevice.which);
            }
            if (event.type == SDL_EVENT_GAMEPAD_REMOVED &&
                event.gdevice.which == gamepad_id) {
                gamepad.reset();
                gamepad_id = 0;
                input.set_gamepad_connected(false);
            }
            if ((event.type == SDL_EVENT_GAMEPAD_BUTTON_DOWN ||
                 event.type == SDL_EVENT_GAMEPAD_BUTTON_UP) &&
                event.gbutton.which == gamepad_id) {
                const auto button = static_cast<SDL_GamepadButton>(event.gbutton.button);
                if (const char* name = gamepad_button_name(button); name != nullptr) {
                    input.set_control(canonical_name("gamepad", name),
                                      event.gbutton.down ? 1.0F : 0.0F);
                }
            }
            if (event.type == SDL_EVENT_GAMEPAD_AXIS_MOTION &&
                event.gaxis.which == gamepad_id) {
                const auto axis = static_cast<SDL_GamepadAxis>(event.gaxis.axis);
                if (const char* name = gamepad_axis_name(axis); name != nullptr) {
                    input.set_control(canonical_name("gamepad", name),
                                      normalized_axis(axis, event.gaxis.value));
                }
            }
            if ((event.type == SDL_EVENT_WINDOW_RESIZED ||
                 event.type == SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED) &&
                event.window.windowID == window_id) {
                if (SDL_GetWindowSize(window.get(), &logical_width, &logical_height) &&
                    SDL_GetWindowSizeInPixels(window.get(), &pixel_width, &pixel_height)) {
                    viewport_width.store(
                        static_cast<std::uint32_t>(std::max(pixel_width, 1)));
                    viewport_height.store(
                        static_cast<std::uint32_t>(std::max(pixel_height, 1)));
                    renderer.resize(static_cast<std::uint32_t>(std::max(pixel_width, 1)),
                                    static_cast<std::uint32_t>(std::max(pixel_height, 1)));
                }
            }
        }
        if (quit) {
            break;
        }

        const bool window_focused =
            (SDL_GetWindowFlags(window.get()) & SDL_WINDOW_INPUT_FOCUS) != 0;
        if (window_focused != input.focused()) {
            input.set_focused(window_focused);
        }

        const bool desired_pointer_lock =
            input.pointer_lock_requested() && input.focused();
        if (desired_pointer_lock != applied_pointer_lock) {
            if (!SDL_SetWindowRelativeMouseMode(window.get(), desired_pointer_lock)) {
                throw EngineError(sdl_error("SDL could not change relative mouse mode"));
            }
            applied_pointer_lock = desired_pointer_lock;
        }
        input.set_pointer_lock_active(applied_pointer_lock);
        input.end_frame();
        if (frame_callback) {
            frame_callback(last_frame_seconds.load());
        }
        if (scene != nullptr && scene->active()) {
            audio.set_listener(scene->camera().position, scene->camera().right());
        }

        renderer.present();
        renderer_stats.store(renderer.stats());
        frame_count.fetch_add(1);

        if (minimum_frame != Clock::duration::zero()) {
            std::this_thread::sleep_until(frame_start + minimum_frame);
        }
    }
    input.set_focused(false);
    input.set_gamepad_connected(false);
}

} // namespace easy3d::platform

