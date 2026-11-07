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
            std::cerr << "RIX audio: SDL audio initialization unavailable ("
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
            std::cerr << "RIX audio: unavailable (" << SDL_GetError() << ")\n";
            return;
        }
        if (!SDL_ResumeAudioStreamDevice(stream_)) {
            std::cerr << "RIX audio: could not start (" << SDL_GetError() << ")\n";
            SDL_DestroyAudioStream(stream_);
            stream_ = nullptr;
            return;
        }
        audio_.set_backend_active(true);
        std::cout << "RIX audio: SDL3 default playback, 48000 Hz stereo float\n";
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

class WindowSession::Impl final {
public:
    using Clock = std::chrono::steady_clock;

    Impl(const EngineConfig& config,
         const Scene* const scene,
         const std::atomic_bool& stop_requested,
         std::atomic_uint64_t& frame_count,
         std::atomic<double>& last_frame_seconds,
         std::atomic_uint32_t& viewport_width,
         std::atomic_uint32_t& viewport_height,
         RendererStatsAtomic& renderer_stats,
         InputSystem& input,
         AudioSystem& audio)
        : config_(config),
          scene_(scene),
          stop_requested_(stop_requested),
          frame_count_(frame_count),
          last_frame_seconds_(last_frame_seconds),
          viewport_width_(viewport_width),
          viewport_height_(viewport_height),
          renderer_stats_(renderer_stats),
          input_(input),
          audio_(audio) {
        const auto flags = static_cast<SDL_WindowFlags>(
            SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY);
        window_.reset(SDL_CreateWindow(config_.title.c_str(),
                                       static_cast<int>(config_.width),
                                       static_cast<int>(config_.height),
                                       flags));
        if (!window_) {
            throw EngineError(sdl_error("SDL window creation failed"));
        }
        input_.set_focused(
            (SDL_GetWindowFlags(window_.get()) & SDL_WINDOW_INPUT_FOCUS) != 0);
        (void)SDL_RaiseWindow(window_.get());

        void* native_window = SDL_GetPointerProperty(
            SDL_GetWindowProperties(window_.get()),
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
        if (!SDL_GetWindowSize(window_.get(), &logical_width_, &logical_height_)) {
            throw EngineError(sdl_error("SDL could not query the logical window size"));
        }
        if (!SDL_GetWindowSizeInPixels(window_.get(), &pixel_width_, &pixel_height_)) {
            throw EngineError(sdl_error("SDL could not query the window pixel size"));
        }
        viewport_width_.store(
            static_cast<std::uint32_t>(std::max(pixel_width_, 1)));
        viewport_height_.store(
            static_cast<std::uint32_t>(std::max(pixel_height_, 1)));

        renderer_ = std::make_unique<renderer::BgfxRenderer>(
            native_window,
            static_cast<std::uint32_t>(std::max(pixel_width_, 1)),
            static_cast<std::uint32_t>(std::max(pixel_height_, 1)),
            config_.vsync,
            config_.graphics_preset,
            config_.geometry_diagnostic,
            scene_);
        if (scene_ != nullptr && scene_->active()) {
            audio_.set_listener(scene_->camera().position, scene_->camera().right());
        }
        audio_output_ = std::make_unique<SdlAudioOutput>(audio_);
        previous_frame_ = Clock::now();
        window_id_ = SDL_GetWindowID(window_.get());
    }

    ~Impl() {
        input_.set_pointer_lock_active(false);
        input_.set_focused(false);
        input_.set_gamepad_connected(false);
    }

    [[nodiscard]] bool tick(Engine::FrameCallback& frame_callback,
                            const double fps_limit) {
        if (stop_requested_.load()) {
            return false;
        }
        const auto frame_start = Clock::now();
        last_frame_seconds_.store(
            std::chrono::duration<double>(frame_start - previous_frame_).count());
        previous_frame_ = frame_start;

        input_.begin_frame();
        SDL_Event event{};
        bool quit = false;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT) {
                quit = true;
            }
            if ((event.type == SDL_EVENT_KEY_DOWN || event.type == SDL_EVENT_KEY_UP) &&
                event.key.windowID == window_id_ && !event.key.repeat) {
                input_.set_control(canonical_key(event.key.scancode),
                                   event.key.down ? 1.0F : 0.0F);
            }
            if (event.type == SDL_EVENT_MOUSE_MOTION &&
                event.motion.windowID == window_id_) {
                const float scale_x = static_cast<float>(std::max(pixel_width_, 1)) /
                                      static_cast<float>(std::max(logical_width_, 1));
                const float scale_y = static_cast<float>(std::max(pixel_height_, 1)) /
                                      static_cast<float>(std::max(logical_height_, 1));
                input_.add_pointer_motion(event.motion.x * scale_x,
                                          event.motion.y * scale_y,
                                          event.motion.xrel * scale_x,
                                          event.motion.yrel * scale_y);
            }
            if ((event.type == SDL_EVENT_MOUSE_BUTTON_DOWN ||
                 event.type == SDL_EVENT_MOUSE_BUTTON_UP) &&
                event.button.windowID == window_id_) {
                if (const char* name = mouse_button_name(event.button.button);
                    name != nullptr) {
                    input_.set_control(canonical_name("mouse", name),
                                       event.button.down ? 1.0F : 0.0F);
                }
            }
            if (event.type == SDL_EVENT_MOUSE_WHEEL &&
                event.wheel.windowID == window_id_) {
                input_.add_wheel(event.wheel.x, event.wheel.y);
            }
            if (event.type == SDL_EVENT_WINDOW_FOCUS_GAINED &&
                event.window.windowID == window_id_) {
                input_.set_focused(true);
            }
            if (event.type == SDL_EVENT_WINDOW_FOCUS_LOST &&
                event.window.windowID == window_id_) {
                input_.set_focused(false);
            }
            if (event.type == SDL_EVENT_GAMEPAD_ADDED) {
                open_gamepad(event.gdevice.which);
            }
            if (event.type == SDL_EVENT_GAMEPAD_REMOVED &&
                event.gdevice.which == gamepad_id_) {
                gamepad_.reset();
                gamepad_id_ = 0;
                input_.set_gamepad_connected(false);
            }
            if ((event.type == SDL_EVENT_GAMEPAD_BUTTON_DOWN ||
                 event.type == SDL_EVENT_GAMEPAD_BUTTON_UP) &&
                event.gbutton.which == gamepad_id_) {
                const auto button = static_cast<SDL_GamepadButton>(event.gbutton.button);
                if (const char* name = gamepad_button_name(button); name != nullptr) {
                    input_.set_control(canonical_name("gamepad", name),
                                       event.gbutton.down ? 1.0F : 0.0F);
                }
            }
            if (event.type == SDL_EVENT_GAMEPAD_AXIS_MOTION &&
                event.gaxis.which == gamepad_id_) {
                const auto axis = static_cast<SDL_GamepadAxis>(event.gaxis.axis);
                if (const char* name = gamepad_axis_name(axis); name != nullptr) {
                    input_.set_control(canonical_name("gamepad", name),
                                       normalized_axis(axis, event.gaxis.value));
                }
            }
            if ((event.type == SDL_EVENT_WINDOW_RESIZED ||
                 event.type == SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED) &&
                event.window.windowID == window_id_) {
                if (SDL_GetWindowSize(window_.get(), &logical_width_, &logical_height_) &&
                    SDL_GetWindowSizeInPixels(window_.get(), &pixel_width_, &pixel_height_)) {
                    viewport_width_.store(
                        static_cast<std::uint32_t>(std::max(pixel_width_, 1)));
                    viewport_height_.store(
                        static_cast<std::uint32_t>(std::max(pixel_height_, 1)));
                    renderer_->resize(
                        static_cast<std::uint32_t>(std::max(pixel_width_, 1)),
                        static_cast<std::uint32_t>(std::max(pixel_height_, 1)));
                }
            }
        }
        if (quit) {
            input_.end_frame();
            return false;
        }

        const bool window_focused =
            (SDL_GetWindowFlags(window_.get()) & SDL_WINDOW_INPUT_FOCUS) != 0;
        if (window_focused != input_.focused()) {
            input_.set_focused(window_focused);
        }
        const bool desired_pointer_lock =
            input_.pointer_lock_requested() && input_.focused();
        if (desired_pointer_lock != applied_pointer_lock_) {
            if (!SDL_SetWindowRelativeMouseMode(window_.get(), desired_pointer_lock)) {
                throw EngineError(sdl_error("SDL could not change relative mouse mode"));
            }
            applied_pointer_lock_ = desired_pointer_lock;
        }
        input_.set_pointer_lock_active(applied_pointer_lock_);
        input_.end_frame();

        if (frame_callback) {
            frame_callback(last_frame_seconds_.load());
        }
        if (scene_ != nullptr && scene_->active()) {
            audio_.set_listener(scene_->camera().position, scene_->camera().right());
        }
        renderer_->present();
        renderer_stats_.store(renderer_->stats());
        frame_count_.fetch_add(1);

        if (fps_limit > 0.0) {
            const auto minimum_frame = std::chrono::duration_cast<Clock::duration>(
                std::chrono::duration<double>(1.0 / fps_limit));
            std::this_thread::sleep_until(frame_start + minimum_frame);
        }
        return !stop_requested_.load();
    }

private:
    void open_gamepad(const SDL_JoystickID id) {
        if (gamepad_) {
            return;
        }
        gamepad_.reset(SDL_OpenGamepad(id));
        if (!gamepad_) {
            return;
        }
        gamepad_id_ = SDL_GetGamepadID(gamepad_.get());
        const char* name = SDL_GetGamepadName(gamepad_.get());
        input_.set_gamepad_connected(true, name == nullptr ? "Gamepad" : name);
    }

    const EngineConfig& config_;
    const Scene* scene_;
    const std::atomic_bool& stop_requested_;
    std::atomic_uint64_t& frame_count_;
    std::atomic<double>& last_frame_seconds_;
    std::atomic_uint32_t& viewport_width_;
    std::atomic_uint32_t& viewport_height_;
    RendererStatsAtomic& renderer_stats_;
    InputSystem& input_;
    AudioSystem& audio_;
    SdlVideo sdl_;
    std::unique_ptr<SDL_Window, WindowDeleter> window_;
    std::unique_ptr<renderer::BgfxRenderer> renderer_;
    std::unique_ptr<SdlAudioOutput> audio_output_;
    std::unique_ptr<SDL_Gamepad, GamepadDeleter> gamepad_;
    Clock::time_point previous_frame_{};
    SDL_WindowID window_id_{0};
    SDL_JoystickID gamepad_id_{0};
    int pixel_width_{0};
    int pixel_height_{0};
    int logical_width_{0};
    int logical_height_{0};
    bool applied_pointer_lock_{false};
};

WindowSession::WindowSession(const EngineConfig& config,
                             const Scene* const scene,
                             const std::atomic_bool& stop_requested,
                             std::atomic_uint64_t& frame_count,
                             std::atomic<double>& last_frame_seconds,
                             std::atomic_uint32_t& viewport_width,
                             std::atomic_uint32_t& viewport_height,
                             RendererStatsAtomic& renderer_stats,
                             InputSystem& input,
                             AudioSystem& audio)
    : impl_(std::make_unique<Impl>(config,
                                   scene,
                                   stop_requested,
                                   frame_count,
                                   last_frame_seconds,
                                   viewport_width,
                                   viewport_height,
                                   renderer_stats,
                                   input,
                                   audio)) {}

WindowSession::~WindowSession() = default;

bool WindowSession::tick(Engine::FrameCallback& frame_callback,
                         const double fps_limit) {
    return impl_->tick(frame_callback, fps_limit);
}

class ExternalWindowSession::Impl final {
public:
    Impl(const std::uintptr_t native_window,
         const std::uint32_t width,
         const std::uint32_t height,
         const EngineConfig& config,
         const Scene* const scene) {
        if (native_window == 0) {
            throw std::invalid_argument("external window handle must not be zero");
        }
        const auto hwnd = reinterpret_cast<HWND>(native_window);
        if (!IsWindow(hwnd)) {
            throw EngineError("external window handle is not a live Win32 HWND");
        }
        if (width == 0 || height == 0 ||
            width > std::numeric_limits<std::uint16_t>::max() ||
            height > std::numeric_limits<std::uint16_t>::max()) {
            throw std::invalid_argument(
                "external renderer dimensions must be positive and fit in 16 bits");
        }
        renderer_ = std::make_unique<renderer::BgfxRenderer>(
            hwnd,
            width,
            height,
            config.vsync,
            config.graphics_preset,
            config.geometry_diagnostic,
            scene);
    }

    void resize(const std::uint32_t width, const std::uint32_t height) {
        if (width == 0 || height == 0 ||
            width > std::numeric_limits<std::uint16_t>::max() ||
            height > std::numeric_limits<std::uint16_t>::max()) {
            throw std::invalid_argument(
                "external renderer dimensions must be positive and fit in 16 bits");
        }
        renderer_->resize(width, height);
    }

    [[nodiscard]] RendererStats render() {
        renderer_->present();
        return renderer_->stats();
    }

    [[nodiscard]] RendererStats render_offscreen() {
        renderer_->render_offscreen();
        return renderer_->stats();
    }

    [[nodiscard]] std::vector<std::uint8_t> readback_rgba8() {
        return renderer_->readback_rgba8();
    }

    [[nodiscard]] std::vector<std::uint8_t> render_viewport_rgba8(
        const Camera& camera,
        const std::uint32_t width,
        const std::uint32_t height) {
        return renderer_->render_viewport_rgba8(camera, width, height);
    }

    [[nodiscard]] std::uint64_t request_viewport_rgba8(
        const Camera& camera,
        const std::uint32_t width,
        const std::uint32_t height) {
        return renderer_->request_viewport_rgba8(camera, width, height);
    }

    [[nodiscard]] std::optional<std::vector<std::uint8_t>> poll_viewport_rgba8(
        const std::uint64_t request_id) {
        return renderer_->poll_viewport_rgba8(request_id);
    }

    [[nodiscard]] std::vector<std::uint8_t> wait_viewport_rgba8(
        const std::uint64_t request_id) {
        return renderer_->wait_viewport_rgba8(request_id);
    }

    void cancel_viewport_rgba8(const std::uint64_t request_id) noexcept {
        renderer_->cancel_viewport_rgba8(request_id);
    }

    [[nodiscard]] RendererStats stats() const noexcept {
        return renderer_->stats();
    }

private:
    std::unique_ptr<renderer::BgfxRenderer> renderer_;
};

ExternalWindowSession::ExternalWindowSession(
    const std::uintptr_t native_window,
    const std::uint32_t width,
    const std::uint32_t height,
    const EngineConfig& config,
    const Scene* const scene)
    : impl_(std::make_unique<Impl>(native_window, width, height, config, scene)) {}

ExternalWindowSession::~ExternalWindowSession() = default;

void ExternalWindowSession::resize(const std::uint32_t width,
                                   const std::uint32_t height) {
    impl_->resize(width, height);
}

RendererStats ExternalWindowSession::render() {
    return impl_->render();
}

RendererStats ExternalWindowSession::render_offscreen() {
    return impl_->render_offscreen();
}

std::vector<std::uint8_t> ExternalWindowSession::readback_rgba8() {
    return impl_->readback_rgba8();
}

std::vector<std::uint8_t> ExternalWindowSession::render_viewport_rgba8(
    const Camera& camera,
    const std::uint32_t width,
    const std::uint32_t height) {
    return impl_->render_viewport_rgba8(camera, width, height);
}

std::uint64_t ExternalWindowSession::request_viewport_rgba8(
    const Camera& camera,
    const std::uint32_t width,
    const std::uint32_t height) {
    return impl_->request_viewport_rgba8(camera, width, height);
}

std::optional<std::vector<std::uint8_t>> ExternalWindowSession::poll_viewport_rgba8(
    const std::uint64_t request_id) {
    return impl_->poll_viewport_rgba8(request_id);
}

std::vector<std::uint8_t> ExternalWindowSession::wait_viewport_rgba8(
    const std::uint64_t request_id) {
    return impl_->wait_viewport_rgba8(request_id);
}

void ExternalWindowSession::cancel_viewport_rgba8(
    const std::uint64_t request_id) noexcept {
    impl_->cancel_viewport_rgba8(request_id);
}

RendererStats ExternalWindowSession::stats() const noexcept {
    return impl_->stats();
}

} // namespace easy3d::platform

