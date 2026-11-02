#include "easy3d/audio.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {

int fail(const int code, const char* const message) {
    std::cerr << message << '\n';
    return code;
}

[[nodiscard]] bool close(const float left, const float right) {
    return std::abs(left - right) <= 1.0e-4F;
}

} // namespace

int main() {
    try {
        easy3d::AudioSystem audio;
        const std::uint64_t sound =
            audio.create_pcm16_sound(std::vector<std::int16_t>(48, 16'384), 1, 48'000);
        if (audio.sound_count() != 1 || audio.backend_active()) {
            return fail(1, "initial audio state is incorrect");
        }
        audio.set_backend_active(true);
        if (!audio.backend_active()) {
            return fail(2, "backend state did not update");
        }

        const std::uint64_t voice = audio.play(sound);
        std::vector<float> output(24 * 2);
        audio.mix(output.data(), 24, 48'000);
        if (!audio.voice_playing(voice) || !close(output[0], 0.5F) ||
            !close(output[1], 0.5F)) {
            return fail(3, "mono non-spatial mix is incorrect");
        }
        audio.mix(output.data(), 24, 48'000);
        audio.mix(output.data(), 1, 48'000);
        if (audio.voice_playing(voice) || audio.active_voice_count() != 0) {
            return fail(4, "one-shot voice did not complete and retire");
        }

        easy3d::AudioPlayConfig loop;
        loop.loop = true;
        const std::uint64_t loop_voice = audio.play(sound, loop);
        audio.mix(output.data(), 24, 48'000);
        audio.mix(output.data(), 24, 48'000);
        audio.mix(output.data(), 24, 48'000);
        if (!audio.voice_playing(loop_voice)) {
            return fail(5, "looping voice stopped at the buffer boundary");
        }
        audio.set_voice_volume(loop_voice, 0.25F);
        audio.stop(loop_voice);
        audio.stop(loop_voice);
        if (audio.voice_playing(loop_voice)) {
            return fail(6, "voice stop was not idempotent");
        }

        audio.set_listener({0.0F, 0.0F, 0.0F}, {1.0F, 0.0F, 0.0F});
        easy3d::AudioPlayConfig spatial;
        spatial.loop = true;
        spatial.spatial = true;
        spatial.position = {2.0F, 0.0F, 0.0F};
        spatial.minimum_distance = 1.0F;
        spatial.maximum_distance = 10.0F;
        const std::uint64_t spatial_voice = audio.play(sound, spatial);
        audio.mix(output.data(), 1, 48'000);
        if (!(output[1] > 0.4F && std::abs(output[0]) < 1.0e-5F)) {
            return fail(7, "right-side positional panning is incorrect");
        }
        audio.set_voice_position(spatial_voice, {10.0F, 0.0F, 0.0F});
        audio.mix(output.data(), 1, 48'000);
        if (!close(output[0], 0.0F) || !close(output[1], 0.0F)) {
            return fail(8, "maximum-distance attenuation did not reach silence");
        }
        audio.stop(spatial_voice);

        output.resize(49 * 2);
        for (int replay = 0; replay < 1'100; ++replay) {
            const std::uint64_t replay_voice = audio.play(sound);
            audio.mix(output.data(), 49, 48'000);
            if (audio.voice_playing(replay_voice)) {
                return fail(9, "completed replay voice was not retired");
            }
        }

        try {
            (void)audio.create_pcm16_sound({1, 2}, 3, 48'000);
            return fail(10, "invalid channel count was accepted");
        } catch (const std::invalid_argument&) {
        }
        try {
            spatial.volume = -1.0F;
            (void)audio.play(sound, spatial);
            return fail(11, "invalid gain was accepted");
        } catch (const std::invalid_argument&) {
        }
        try {
            audio.set_listener({}, {});
            return fail(12, "zero listener orientation was accepted");
        } catch (const std::invalid_argument&) {
        }

        std::cout << "easy3d_audio_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "easy3d_audio_tests: FAIL: " << error.what() << '\n';
        return 13;
    }
}
