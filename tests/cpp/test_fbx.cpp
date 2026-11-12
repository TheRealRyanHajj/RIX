#include "easy3d/assets.hpp"
#include "easy3d/scene.hpp"
#include <ufbx.h>

#include <filesystem>
#include <fstream>
#include <cstdlib>
#include <iostream>
#include <cmath>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

void require(const bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

[[nodiscard]] easy3d::Matrix4 matrix(const easy3d::Transform& transform) {
    const easy3d::Quat q = transform.rotation.normalized();
    const float xx = q.x * q.x, yy = q.y * q.y, zz = q.z * q.z;
    const float xy = q.x * q.y, xz = q.x * q.z, yz = q.y * q.z;
    const float wx = q.w * q.x, wy = q.w * q.y, wz = q.w * q.z;
    easy3d::Matrix4 result;
    result.values = {
        (1.0F - 2.0F * (yy + zz)) * transform.scale.x,
        (2.0F * (xy + wz)) * transform.scale.x,
        (2.0F * (xz - wy)) * transform.scale.x, 0.0F,
        (2.0F * (xy - wz)) * transform.scale.y,
        (1.0F - 2.0F * (xx + zz)) * transform.scale.y,
        (2.0F * (yz + wx)) * transform.scale.y, 0.0F,
        (2.0F * (xz + wy)) * transform.scale.z,
        (2.0F * (yz - wx)) * transform.scale.z,
        (1.0F - 2.0F * (xx + yy)) * transform.scale.z, 0.0F,
        transform.position.x, transform.position.y, transform.position.z, 1.0F,
    };
    return result;
}

void require_usable_skinned_bounds(const easy3d::ModelData& model,
                                   const std::vector<easy3d::Transform>& pose) {
    const easy3d::Skeleton& skeleton = *model.skeleton;
    std::vector<easy3d::Matrix4> globals(skeleton.joints.size());
    std::vector<easy3d::Matrix4> palette(skeleton.joints.size());
    for (std::size_t index = 0; index < skeleton.joints.size(); ++index) {
        const auto local = matrix(pose[index]);
        globals[index] = skeleton.joints[index].parent >= 0
            ? globals[static_cast<std::size_t>(skeleton.joints[index].parent)] * local
            : local;
        palette[index] = globals[index] * skeleton.joints[index].inverse_bind;
    }
    easy3d::Vec3 minimum{1.0e30F, 1.0e30F, 1.0e30F};
    easy3d::Vec3 maximum{-1.0e30F, -1.0e30F, -1.0e30F};
    for (const auto& part : model.parts) {
        for (const auto& vertex : part.mesh.vertices) {
            easy3d::Vec3 deformed{};
            for (std::size_t influence = 0; influence < 4; ++influence) {
                deformed = deformed +
                    palette[vertex.joints[influence]].transform_point(vertex.position) *
                        vertex.weights[influence];
            }
            minimum.x = std::min(minimum.x, deformed.x);
            minimum.y = std::min(minimum.y, deformed.y);
            minimum.z = std::min(minimum.z, deformed.z);
            maximum.x = std::max(maximum.x, deformed.x);
            maximum.y = std::max(maximum.y, deformed.y);
            maximum.z = std::max(maximum.z, deformed.z);
        }
    }
    const easy3d::Vec3 extent = maximum - minimum;
    std::cout << "deformed_bounds=" << minimum.x << ',' << minimum.y << ','
              << minimum.z << ".." << maximum.x << ',' << maximum.y << ','
              << maximum.z << '\n';
    require(extent.x > 0.25F && extent.y > 0.75F && extent.z > 0.25F,
            "CPU-skinned character bounds collapsed");
    require(maximum.length() < 20.0F && minimum.length() < 20.0F,
            "CPU-skinned character bounds exploded");
}

void describe_bind_palette(const easy3d::ModelData& model) {
    const easy3d::Skeleton& skeleton = *model.skeleton;
    std::vector<easy3d::Matrix4> globals(skeleton.joints.size());
    float maximum_error = 0.0F;
    for (std::size_t index = 0; index < skeleton.joints.size(); ++index) {
        const auto local = matrix(skeleton.joints[index].local_bind);
        globals[index] = skeleton.joints[index].parent >= 0
            ? globals[static_cast<std::size_t>(skeleton.joints[index].parent)] * local
            : local;
        const auto palette = globals[index] * skeleton.joints[index].inverse_bind;
        for (std::size_t component = 0; component < 16; ++component) {
            const float expected = component % 5 == 0 ? 1.0F : 0.0F;
            maximum_error = std::max(
                maximum_error, std::abs(palette.values[component] - expected));
        }
    }
    std::cout << "bind_palette_max_identity_error=" << maximum_error << '\n';
}

void describe(const char* label, const easy3d::ModelData& model) {
    std::size_t vertices = 0;
    std::size_t weighted = 0;
    easy3d::Vec3 minimum{1.0e30F, 1.0e30F, 1.0e30F};
    easy3d::Vec3 maximum{-1.0e30F, -1.0e30F, -1.0e30F};
    for (const auto& part : model.parts) {
        vertices += part.mesh.vertices.size();
        for (const auto& vertex : part.mesh.vertices) {
            minimum.x = std::min(minimum.x, vertex.position.x);
            minimum.y = std::min(minimum.y, vertex.position.y);
            minimum.z = std::min(minimum.z, vertex.position.z);
            maximum.x = std::max(maximum.x, vertex.position.x);
            maximum.y = std::max(maximum.y, vertex.position.y);
            maximum.z = std::max(maximum.z, vertex.position.z);
            if (vertex.weights[0] > 0.0F) ++weighted;
        }
    }
    std::cout << label << ": parts=" << model.parts.size()
              << " materials=" << model.materials.size()
              << " triangles=" << model.triangle_count()
              << " vertices=" << vertices
              << " weighted_vertices=" << weighted
              << " joints=" << (model.skeleton ? model.skeleton->joints.size() : 0U)
              << " clips=" << model.animations.size() << '\n';
    if (!model.parts.empty()) {
        std::cout << label << " bounds=" << minimum.x << ',' << minimum.y << ','
                  << minimum.z << ".." << maximum.x << ',' << maximum.y << ','
                  << maximum.z << '\n';
    }
    if (model.skeleton) {
        for (std::size_t index = 0; index < model.skeleton->joints.size(); ++index) {
            const auto& joint = model.skeleton->joints[index];
            std::cout << "joint[" << index << "]=" << joint.name
                      << " parent=" << joint.parent << '\n';
        }
    }
    for (const auto& clip : model.animations) {
        std::cout << "clip=" << clip.name << " duration=" << clip.duration
                  << " channels=" << clip.channels.size() << '\n';
    }
    for (const auto& warning : model.warnings) {
        std::cout << "warning=" << warning << '\n';
    }
}

void describe_source(const char* label, const std::filesystem::path& path) {
    ufbx_error error{};
    ufbx_scene* scene = ufbx_load_file(path.string().c_str(), nullptr, &error);
    require(scene != nullptr, "raw ufbx audit load failed");
    std::size_t embedded = 0;
    for (std::size_t index = 0; index < scene->textures.count; ++index) {
        if (scene->textures.data[index]->content.size > 0) ++embedded;
    }
    std::cout << label << " source: ascii=" << scene->metadata.ascii
              << " version=" << scene->metadata.version
              << " unit_meters=" << scene->settings.unit_meters
              << " axes=" << static_cast<int>(scene->settings.axes.right) << ','
              << static_cast<int>(scene->settings.axes.up) << ','
              << static_cast<int>(scene->settings.axes.front)
              << " fps=" << scene->settings.frames_per_second
              << " meshes=" << scene->meshes.count
              << " skins=" << scene->skin_deformers.count
              << " bones=" << scene->bones.count
              << " stacks=" << scene->anim_stacks.count
              << " textures=" << scene->textures.count
              << " embedded_textures=" << embedded << '\n';
    ufbx_free_scene(scene);
}

} // namespace

int main() {
    try {
        const char* configured_assets = std::getenv("RIX_ANIMATION_TEST_ASSETS");
        const std::filesystem::path assets = configured_assets != nullptr
            ? std::filesystem::path(configured_assets)
            : std::filesystem::path(RIX_SOURCE_DIR).parent_path() / "code" /
                "python" / "rix things" / "animation test" / "assets";
        const std::filesystem::path ascii_fixture =
            std::filesystem::path(RIX_UFBX_SOURCE_DIR) / "data" /
            "blender_279_default_6100_ascii.fbx";
        const auto ascii = easy3d::load_fbx(ascii_fixture);
        require(ascii->triangle_count() > 0, "ASCII FBX fixture has no geometry");
        bool missing_failed = false;
        try {
            (void)easy3d::load_fbx(assets / "does-not-exist.fbx");
        } catch (const easy3d::AssetError&) {
            missing_failed = true;
        }
        require(missing_failed, "missing FBX did not raise AssetError");
        const auto invalid_path = std::filesystem::temp_directory_path() /
                                  "rix-invalid-animation-test.fbx";
        {
            std::ofstream invalid(invalid_path, std::ios::binary);
            invalid << "this is not an FBX file";
        }
        bool invalid_failed = false;
        try {
            (void)easy3d::load_fbx(invalid_path);
        } catch (const easy3d::AssetError&) {
            invalid_failed = true;
        }
        std::error_code remove_error;
        std::filesystem::remove(invalid_path, remove_error);
        require(invalid_failed, "invalid FBX did not raise AssetError");
        if (!std::filesystem::is_regular_file(assets / "YBot.fbx") ||
            !std::filesystem::is_regular_file(assets / "Thriller Animation.fbx")) {
            std::cout << "SKIP real YBot/Thriller regression: set "
                         "RIX_ANIMATION_TEST_ASSETS to the external assets directory\n";
            return 0;
        }
        describe_source("YBot", assets / "YBot.fbx");
        describe_source("Thriller", assets / "Thriller Animation.fbx");
        const auto ybot = easy3d::load_fbx(assets / "YBot.fbx");
        const auto thriller = easy3d::load_fbx(assets / "Thriller Animation.fbx");
        describe("YBot", *ybot);
        describe("Thriller", *thriller);
        require(ybot->triangle_count() > 0, "YBot has no geometry");
        require(ybot->skeleton.has_value(), "YBot has no skeleton");
        require(!ybot->skeleton->joints.empty(), "YBot skeleton is empty");
        describe_bind_palette(*ybot);
        require(thriller->skeleton.has_value(), "Thriller has no skeleton");
        require(!thriller->animations.empty(), "Thriller has no animation clips");
        std::unordered_map<std::string, std::size_t> source_joints;
        for (std::size_t index = 0; index < thriller->skeleton->joints.size(); ++index) {
            source_joints.emplace(thriller->skeleton->joints[index].name, index);
        }
        float maximum_rest_translation_delta = 0.0F;
        float minimum_rest_rotation_dot = 1.0F;
        for (const auto& target : ybot->skeleton->joints) {
            const auto found = source_joints.find(target.name);
            require(found != source_joints.end(), "Thriller is missing a YBot skin joint");
            const auto& source = thriller->skeleton->joints[found->second];
            const auto delta = target.local_bind.position - source.local_bind.position;
            maximum_rest_translation_delta = std::max(
                maximum_rest_translation_delta, delta.length());
            const auto& a = target.local_bind.rotation;
            const auto& b = source.local_bind.rotation;
            minimum_rest_rotation_dot = std::min(
                minimum_rest_rotation_dot,
                std::abs(a.w*b.w + a.x*b.x + a.y*b.y + a.z*b.z));
            if (target.parent >= 0) {
                const std::string& target_parent =
                    ybot->skeleton->joints[static_cast<std::size_t>(target.parent)].name;
                require(source.parent >= 0, "Thriller joint has incompatible root parent");
                require(thriller->skeleton->joints[
                            static_cast<std::size_t>(source.parent)].name == target_parent,
                        "Thriller joint hierarchy differs from YBot");
            }
        }
        std::cout << "compatibility=mapped " << ybot->skeleton->joints.size()
                  << "/" << thriller->skeleton->joints.size()
                  << " max_rest_translation_delta=" << maximum_rest_translation_delta
                  << " min_rest_rotation_abs_dot=" << minimum_rest_rotation_dot << '\n';
        const auto pose0 = thriller->animations.front().sample(*thriller->skeleton, 0.0F);
        const auto pose1 = thriller->animations.front().sample(
            *thriller->skeleton, thriller->animations.front().duration * 0.5F);
        const auto pose_end = thriller->animations.front().sample(
            *thriller->skeleton, thriller->animations.front().duration, false);
        const auto root_delta = pose_end.front().position - pose0.front().position;
        std::cout << "root_translation_delta=" << root_delta.x << ','
                  << root_delta.y << ',' << root_delta.z << '\n';
        require(pose0.size() == pose1.size(), "sampled pose sizes differ");
        bool changed = false;
        for (std::size_t index = 0; index < pose0.size(); ++index) {
            if (pose0[index].position != pose1[index].position ||
                pose0[index].rotation != pose1[index].rotation ||
                pose0[index].scale != pose1[index].scale) {
                changed = true;
                break;
            }
        }
        require(changed, "Thriller poses do not change over time");

        easy3d::Scene scene("animation-test");
        const auto entity = scene.create_entity("YBot");
        scene.add_model_renderer(entity, assets / "YBot.fbx");
        scene.add_model_animation(entity, "Thriller",
                                  assets / "Thriller Animation.fbx");
        scene.play_model_animation(entity, "Thriller", true, 1.0F, 0.2F, false);
        scene.step_physics(1.0F / 60.0F);
        const auto& playback = *scene.render_component(entity).animation;
        require(playback.playing, "native animation did not enter playing state");
        require(playback.current_clip == "Thriller", "wrong active external clip");
        require(playback.time_seconds > 0.0F, "native animation did not advance");
        require(playback.pose.size() == ybot->skeleton->joints.size(),
                "retargeted playback pose has the wrong joint count");
        require_usable_skinned_bounds(*ybot, playback.pose);
        const auto first_pose = playback.pose;
        scene.step_physics(0.1F);
        require(playback.pose != first_pose, "animation pose did not advance");

        const float before_restart = playback.time_seconds;
        scene.play_model_animation(entity, "Thriller", true, 1.0F, 0.25F, false);
        require(playback.time_seconds == 0.0F && before_restart > 0.0F,
                "replaying a clip did not restart it");
        require(!playback.blend_from.empty() && playback.blend_duration == 0.25F,
                "animation restart did not preserve a blend source");
        scene.step_physics(0.125F);
        require(playback.blend_elapsed > 0.0F &&
                    playback.blend_elapsed < playback.blend_duration,
                "animation blend did not advance through its transition");

        scene.play_model_animation(entity, "Thriller", true, -1.0F, 0.0F, false);
        const float reverse_start = playback.time_seconds;
        scene.step_physics(0.25F);
        require(playback.time_seconds < reverse_start,
                "reverse animation playback did not move backward");
        scene.step_physics(thriller->animations.front().duration);
        require(playback.time_seconds >= 0.0F &&
                    playback.time_seconds < thriller->animations.front().duration,
                "reverse looping did not wrap into the clip range");

        const auto entity_two = scene.create_entity("YBot-two");
        scene.add_model_renderer(entity_two, assets / "YBot.fbx");
        scene.add_model_animation(entity_two, "Thriller",
                                  assets / "Thriller Animation.fbx");
        scene.play_model_animation(entity_two, "Thriller", true, 0.5F, 0.0F, false);
        scene.step_physics(0.2F);
        const auto& playback_main = *scene.render_component(entity).animation;
        const auto& playback_two = *scene.render_component(entity_two).animation;
        require(playback_main.time_seconds != playback_two.time_seconds,
                "animated instances did not maintain independent clocks");
        scene.destroy_entity(entity_two);

        scene.play_model_animation(entity, "Thriller", true, 1.0F, 0.0F, false);
        scene.step_physics(0.1F);
        const auto& current_playback = *scene.render_component(entity).animation;
        scene.pause_model_animation(entity);
        const float paused_time = current_playback.time_seconds;
        scene.step_physics(1.0F / 60.0F);
        require(current_playback.time_seconds == paused_time, "paused animation advanced");
        scene.resume_model_animation(entity);
        scene.step_physics(1.0F / 60.0F);
        require(current_playback.time_seconds > paused_time,
                "resumed animation did not advance");
        scene.stop_model_animation(entity);
        require(!current_playback.playing && current_playback.current_clip.empty(),
                "stopped animation retained playback state");
        const easy3d::Transform root_motion_start = scene.world_transform(entity);
        scene.play_model_animation(entity, "Thriller", true, 1.0F, 0.0F, true);
        scene.step_physics(1.0F);
        const easy3d::Transform root_motion_end = scene.world_transform(entity);
        const easy3d::Vec3 root_owner_delta =
            root_motion_end.position - root_motion_start.position;
        require(std::abs(root_owner_delta.x) + std::abs(root_owner_delta.z) > 0.01F,
                "root-motion playback did not drive the owning entity");
        require(std::abs(root_motion_end.position.y - root_motion_start.position.y) <
                    1.0e-5F,
                "root motion moved the owning entity vertically");
        require(easy3d::almost_equal(
                    root_motion_end.rotation.rotate({0.0F, 1.0F, 0.0F}),
                    easy3d::Vec3{0.0F, 1.0F, 0.0F}, 1.0e-4F),
                "root motion tilted the owning entity away from world up");
        const auto root_motion_first = current_playback.clips.at("Thriller").sample(
            *ybot->skeleton, 0.0F, false);
        const auto root_motion_sample = current_playback.clips.at("Thriller").sample(
            *ybot->skeleton, current_playback.time_seconds, false);
        require(std::abs(current_playback.pose.front().position.x -
                         root_motion_first.front().position.x) < 1.0e-4F &&
                    std::abs(current_playback.pose.front().position.z -
                             root_motion_first.front().position.z) < 1.0e-4F,
                "horizontal root translation was applied to both entity and pose");
        require(std::abs(current_playback.pose.front().position.y -
                         root_motion_sample.front().position.y) < 1.0e-4F,
                "vertical root translation was removed from the authored pose");
        const easy3d::Quat combined_root_rotation =
            (root_motion_end.rotation *
             current_playback.pose.front().rotation).normalized();
        const easy3d::Quat sampled_root_rotation =
            root_motion_sample.front().rotation.normalized();
        const float root_rotation_dot = std::abs(
            combined_root_rotation.w * sampled_root_rotation.w +
            combined_root_rotation.x * sampled_root_rotation.x +
            combined_root_rotation.y * sampled_root_rotation.y +
            combined_root_rotation.z * sampled_root_rotation.z);
        require(root_rotation_dot > 0.9999F,
                "yaw extraction changed the authored root orientation");

        scene.pause_model_animation(entity);
        const easy3d::Transform root_motion_paused = scene.world_transform(entity);
        scene.step_physics(0.5F);
        require(easy3d::almost_equal(scene.world_transform(entity).position,
                                     root_motion_paused.position),
                "paused root motion changed the owning entity");
        scene.resume_model_animation(entity);
        scene.step_physics(0.25F);
        require(!easy3d::almost_equal(scene.world_transform(entity).position,
                                      root_motion_paused.position),
                "resumed root motion did not move the owning entity");

        const easy3d::Transform before_root_restart = scene.world_transform(entity);
        scene.play_model_animation(entity, "Thriller", true, 1.0F, 0.0F, true);
        require(easy3d::almost_equal(scene.world_transform(entity).position,
                                     before_root_restart.position),
                "restarting root motion teleported the owning entity");
        scene.step_physics(thriller->animations.front().duration + 0.125F);
        require(!easy3d::almost_equal(scene.world_transform(entity).position,
                                      before_root_restart.position),
                "looped root motion did not accumulate owner displacement");
        require(std::abs(scene.world_transform(entity).position.y -
                         root_motion_start.position.y) < 1.0e-5F,
                "looped root motion accumulated vertical owner displacement");
        require(std::abs(current_playback.pose.front().position.x -
                         root_motion_first.front().position.x) < 1.0e-4F &&
                    std::abs(current_playback.pose.front().position.z -
                             root_motion_first.front().position.z) < 1.0e-4F,
                "looped root motion accumulated horizontal visual displacement");

        easy3d::ModelCache cache;
        const auto cached_first = cache.load(assets / "YBot.fbx");
        const auto cached_second = cache.load(assets / "." / "YBot.fbx");
        require(cached_first == cached_second && cache.size() == 1,
                "model cache did not share repeated FBX loads");
        cache.clear();
        require(cache.size() == 0, "model cache did not release FBX entries");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
