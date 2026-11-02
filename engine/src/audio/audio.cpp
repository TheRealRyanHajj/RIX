#include "easy3d/audio.hpp"

#include "easy3d/core.hpp"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <mutex>
#include <unordered_map>
#include <utility>

namespace easy3d {
namespace {

constexpr std::size_t maximum_sounds = 256;
constexpr std::size_t maximum_voices = 1024;

[[nodiscard]] bool finite(const Vec3 value) noexcept {
    return std::isfinite(value.x) && std::isfinite(value.y) && std::isfinite(value.z);
}

[[nodiscard]] float dot(const Vec3 left, const Vec3 right) noexcept {
    return left.x * right.x + left.y * right.y + left.z * right.z;
}

[[nodiscard]] Vec3 subtract(const Vec3 left, const Vec3 right) noexcept {
    return {left.x - right.x, left.y - right.y, left.z - right.z};
}

[[nodiscard]] float length(const Vec3 value) noexcept {
    return std::sqrt(dot(value, value));
}

} // namespace

class AudioSystem::Impl final {
public:
    struct Sound final {
        std::vector<float> samples;
        std::uint8_t channels{1};
        std::uint32_t sample_rate{48'000};
    };

    struct Voice final {
        std::uint64_t sound{0};
        AudioPlayConfig config;
        double cursor{0.0};
        bool playing{true};
    };

    mutable std::mutex mutex;
    std::unordered_map<std::uint64_t, Sound> sounds;
    std::unordered_map<std::uint64_t, Voice> voices;
    std::uint64_t next_sound{1};
    std::uint64_t next_voice{1};
    Vec3 listener_position{};
    Vec3 listener_right{1.0F, 0.0F, 0.0F};
    std::atomic_bool backend_active{false};
};

AudioSystem::AudioSystem() : impl_(std::make_unique<Impl>()) {}
AudioSystem::~AudioSystem() = default;

std::uint64_t AudioSystem::create_pcm16_sound(std::vector<std::int16_t> samples,
                                              const std::uint8_t channels,
                                              const std::uint32_t sample_rate) {
    if (channels == 0 || channels > 2) {
        throw std::invalid_argument("audio channels must be mono or stereo");
    }
    if (sample_rate < 8'000 || sample_rate > 192'000) {
        throw std::invalid_argument("audio sample rate must be in [8000, 192000]");
    }
    if (samples.empty() || samples.size() % channels != 0) {
        throw std::invalid_argument("PCM16 audio must contain complete non-empty frames");
    }
    std::scoped_lock lock(impl_->mutex);
    if (impl_->sounds.size() >= maximum_sounds) {
        throw EngineError("audio sound limit reached (256)");
    }
    Impl::Sound sound;
    sound.channels = channels;
    sound.sample_rate = sample_rate;
    sound.samples.reserve(samples.size());
    constexpr float scale = 1.0F / 32768.0F;
    for (const std::int16_t sample : samples) {
        sound.samples.push_back(static_cast<float>(sample) * scale);
    }
    const std::uint64_t id = impl_->next_sound++;
    impl_->sounds.emplace(id, std::move(sound));
    return id;
}

std::uint64_t AudioSystem::play(const std::uint64_t sound,
                                AudioPlayConfig config) {
    if (!std::isfinite(config.volume) || config.volume < 0.0F || config.volume > 4.0F) {
        throw std::invalid_argument("audio volume must be finite and in [0, 4]");
    }
    if (!finite(config.position)) {
        throw std::invalid_argument("audio source position must be finite");
    }
    if (!std::isfinite(config.minimum_distance) ||
        !std::isfinite(config.maximum_distance) || config.minimum_distance <= 0.0F ||
        config.maximum_distance <= config.minimum_distance) {
        throw std::invalid_argument(
            "audio distances must be finite with 0 < minimum < maximum");
    }
    std::scoped_lock lock(impl_->mutex);
    if (!impl_->sounds.contains(sound)) {
        throw EngineError("audio sound does not exist");
    }
    if (impl_->voices.size() >= maximum_voices) {
        throw EngineError("audio voice limit reached (1024)");
    }
    const std::uint64_t id = impl_->next_voice++;
    impl_->voices.emplace(id, Impl::Voice{sound, config});
    return id;
}

void AudioSystem::stop(const std::uint64_t voice) {
    std::scoped_lock lock(impl_->mutex);
    const auto found = impl_->voices.find(voice);
    if (found != impl_->voices.end()) {
        impl_->voices.erase(found);
    }
}

void AudioSystem::set_voice_volume(const std::uint64_t voice, const float volume) {
    if (!std::isfinite(volume) || volume < 0.0F || volume > 4.0F) {
        throw std::invalid_argument("audio volume must be finite and in [0, 4]");
    }
    std::scoped_lock lock(impl_->mutex);
    const auto found = impl_->voices.find(voice);
    if (found == impl_->voices.end()) {
        throw EngineError("audio voice does not exist");
    }
    found->second.config.volume = volume;
}

void AudioSystem::set_voice_position(const std::uint64_t voice, const Vec3 position) {
    if (!finite(position)) {
        throw std::invalid_argument("audio source position must be finite");
    }
    std::scoped_lock lock(impl_->mutex);
    const auto found = impl_->voices.find(voice);
    if (found == impl_->voices.end()) {
        throw EngineError("audio voice does not exist");
    }
    found->second.config.position = position;
}

bool AudioSystem::voice_playing(const std::uint64_t voice) const {
    std::scoped_lock lock(impl_->mutex);
    const auto found = impl_->voices.find(voice);
    return found != impl_->voices.end() && found->second.playing;
}

std::size_t AudioSystem::sound_count() const noexcept {
    std::scoped_lock lock(impl_->mutex);
    return impl_->sounds.size();
}

std::size_t AudioSystem::active_voice_count() const noexcept {
    std::scoped_lock lock(impl_->mutex);
    return static_cast<std::size_t>(std::count_if(
        impl_->voices.begin(), impl_->voices.end(),
        [](const auto& entry) { return entry.second.playing; }));
}

void AudioSystem::set_listener(const Vec3 position, const Vec3 right) {
    if (!finite(position) || !finite(right) || length(right) <= 1.0e-6F) {
        throw std::invalid_argument("audio listener vectors must be finite and nonzero");
    }
    const float inverse_length = 1.0F / length(right);
    std::scoped_lock lock(impl_->mutex);
    impl_->listener_position = position;
    impl_->listener_right = {
        right.x * inverse_length, right.y * inverse_length, right.z * inverse_length};
}

void AudioSystem::set_backend_active(const bool active) noexcept {
    impl_->backend_active.store(active);
}

bool AudioSystem::backend_active() const noexcept {
    return impl_->backend_active.load();
}

void AudioSystem::mix(float* const output,
                      const std::size_t frame_count,
                      const std::uint32_t output_sample_rate) noexcept {
    if (output == nullptr || output_sample_rate == 0) {
        return;
    }
    std::fill_n(output, frame_count * 2, 0.0F);
    std::scoped_lock lock(impl_->mutex);
    for (auto& [voice_id, voice] : impl_->voices) {
        (void)voice_id;
        if (!voice.playing) {
            continue;
        }
        const auto sound_found = impl_->sounds.find(voice.sound);
        if (sound_found == impl_->sounds.end()) {
            voice.playing = false;
            continue;
        }
        const Impl::Sound& sound = sound_found->second;
        const std::size_t source_frames = sound.samples.size() / sound.channels;
        const double step = static_cast<double>(sound.sample_rate) /
                            static_cast<double>(output_sample_rate);

        float left_gain = voice.config.volume;
        float right_gain = voice.config.volume;
        if (voice.config.spatial) {
            const Vec3 relative = subtract(voice.config.position, impl_->listener_position);
            const float distance = length(relative);
            if (distance >= voice.config.maximum_distance) {
                left_gain = 0.0F;
                right_gain = 0.0F;
            } else {
                const float attenuation = distance <= voice.config.minimum_distance
                    ? 1.0F
                    : 1.0F - (distance - voice.config.minimum_distance) /
                                     (voice.config.maximum_distance -
                                      voice.config.minimum_distance);
                const float pan = distance <= 1.0e-6F
                    ? 0.0F
                    : std::clamp(dot(relative, impl_->listener_right) / distance,
                                 -1.0F,
                                 1.0F);
                left_gain *= attenuation * std::sqrt(0.5F * (1.0F - pan));
                right_gain *= attenuation * std::sqrt(0.5F * (1.0F + pan));
            }
        }

        for (std::size_t frame = 0; frame < frame_count; ++frame) {
            if (voice.cursor >= static_cast<double>(source_frames)) {
                if (voice.config.loop) {
                    voice.cursor = std::fmod(voice.cursor,
                                             static_cast<double>(source_frames));
                } else {
                    voice.playing = false;
                    break;
                }
            }
            const std::size_t first = static_cast<std::size_t>(voice.cursor);
            const std::size_t second = std::min(first + 1, source_frames - 1);
            const float fraction = static_cast<float>(voice.cursor - first);
            const auto sample = [&](const std::size_t sample_frame,
                                    const std::size_t channel) {
                const std::size_t source_channel = sound.channels == 1 ? 0 : channel;
                return sound.samples[sample_frame * sound.channels + source_channel];
            };
            const float left = sample(first, 0) * (1.0F - fraction) +
                               sample(second, 0) * fraction;
            const float right = sample(first, 1) * (1.0F - fraction) +
                                sample(second, 1) * fraction;
            output[frame * 2] += left * left_gain;
            output[frame * 2 + 1] += right * right_gain;
            voice.cursor += step;
        }
        if (!voice.config.loop &&
            voice.cursor >= static_cast<double>(source_frames)) {
            voice.playing = false;
        }
    }
    for (std::size_t index = 0; index < frame_count * 2; ++index) {
        output[index] = std::clamp(output[index], -1.0F, 1.0F);
    }
    std::erase_if(impl_->voices,
                  [](const auto& entry) { return !entry.second.playing; });
}

} // namespace easy3d
