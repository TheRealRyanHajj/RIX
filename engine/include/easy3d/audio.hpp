#pragma once

#include "easy3d/math.hpp"

#include <cstddef>
#include <cstdint>
#include <memory>
#include <vector>

namespace easy3d {

struct AudioPlayConfig final {
    float volume{1.0F};
    bool loop{false};
    bool spatial{false};
    Vec3 position{};
    float minimum_distance{1.0F};
    float maximum_distance{50.0F};
};

class AudioSystem final {
public:
    AudioSystem();
    ~AudioSystem();
    AudioSystem(const AudioSystem&) = delete;
    AudioSystem& operator=(const AudioSystem&) = delete;

    [[nodiscard]] std::uint64_t create_pcm16_sound(
        std::vector<std::int16_t> samples,
        std::uint8_t channels,
        std::uint32_t sample_rate);
    [[nodiscard]] std::uint64_t play(std::uint64_t sound,
                                     AudioPlayConfig config = {});
    void stop(std::uint64_t voice);
    void set_voice_volume(std::uint64_t voice, float volume);
    void set_voice_position(std::uint64_t voice, Vec3 position);
    [[nodiscard]] bool voice_playing(std::uint64_t voice) const;
    [[nodiscard]] std::size_t sound_count() const noexcept;
    [[nodiscard]] std::size_t active_voice_count() const noexcept;

    void set_listener(Vec3 position, Vec3 right);
    void set_backend_active(bool active) noexcept;
    [[nodiscard]] bool backend_active() const noexcept;
    void mix(float* stereo_samples,
             std::size_t frame_count,
             std::uint32_t output_sample_rate) noexcept;

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace easy3d
