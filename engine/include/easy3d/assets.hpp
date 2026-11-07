#pragma once

#include "easy3d/core.hpp"
#include "easy3d/renderer.hpp"

#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace easy3d {

enum class TextureColorSpace {
    Linear,
    Srgb,
};

enum class TextureFilter {
    Linear,
    Nearest,
};

enum class TextureWrap {
    Repeat,
    Clamp,
};

struct TextureSampler final {
    TextureFilter min_filter{TextureFilter::Nearest};
    TextureFilter mag_filter{TextureFilter::Nearest};
    TextureFilter mip_filter{TextureFilter::Nearest};
    TextureWrap wrap_u{TextureWrap::Repeat};
    TextureWrap wrap_v{TextureWrap::Repeat};

    friend bool operator==(const TextureSampler&, const TextureSampler&) = default;
};

class AssetError : public EngineError {
public:
    using EngineError::EngineError;
};

class MissingAssetError final : public AssetError {
public:
    using AssetError::AssetError;
};

struct ImageData final {
    std::filesystem::path source_path;
    std::uint32_t width{0};
    std::uint32_t height{0};
    TextureColorSpace color_space{TextureColorSpace::Srgb};
    std::vector<std::uint8_t> rgba8;
    std::uint64_t revision{1};

    void validate() const;
    [[nodiscard]] std::size_t byte_size() const noexcept;
};

[[nodiscard]] std::shared_ptr<const ImageData> load_image(
    const std::filesystem::path& path,
    TextureColorSpace color_space = TextureColorSpace::Srgb);

class TextureCache final {
public:
    TextureCache() = default;
    TextureCache(const TextureCache&) = delete;
    TextureCache& operator=(const TextureCache&) = delete;

    [[nodiscard]] std::shared_ptr<const ImageData> load(
        const std::filesystem::path& path,
        TextureColorSpace color_space = TextureColorSpace::Srgb,
        bool hot_reload = true);
    [[nodiscard]] std::size_t poll_changes(
        std::chrono::milliseconds minimum_interval = std::chrono::milliseconds{250}) const noexcept;
    [[nodiscard]] std::size_t size() const noexcept;
    void clear() noexcept;

private:
    struct Entry final {
        std::shared_ptr<ImageData> image;
        std::filesystem::file_time_type modified{};
        bool hot_reload{true};
    };

    mutable std::mutex mutex_;
    mutable std::unordered_map<std::string, Entry> images_;
    mutable std::chrono::steady_clock::time_point last_poll_{};
};

struct ModelMaterial final {
    std::string name{"default"};
    Color diffuse_color{};
    std::optional<std::filesystem::path> diffuse_texture;
    std::optional<std::filesystem::path> normal_texture;
    std::optional<std::filesystem::path> roughness_texture;
    std::optional<std::filesystem::path> metallic_texture;
    std::optional<std::filesystem::path> emissive_texture;
    std::optional<std::filesystem::path> ambient_occlusion_texture;
    float metallic{0.0F};
    float roughness{0.5F};
    float emission{0.0F};
    float normal_strength{1.0F};
    bool packed_metallic_roughness{false};
    bool authored_surface{false};
    bool double_sided{false};
};

struct ModelPart final {
    std::string name;
    MeshData mesh;
    std::size_t material_index{0};
};

struct SkeletonJoint final {
    std::string name;
    std::int32_t parent{-1};
    Transform local_bind;
    Matrix4 inverse_bind;
};

struct Skeleton final {
    std::string name;
    std::vector<SkeletonJoint> joints;

    void validate() const;
};

enum class AnimationTarget {
    Translation,
    Rotation,
    Scale,
};

enum class AnimationInterpolation {
    Linear,
    Step,
};

struct AnimationChannel final {
    std::size_t joint_index{0};
    AnimationTarget target{AnimationTarget::Translation};
    AnimationInterpolation interpolation{AnimationInterpolation::Linear};
    std::vector<float> times;
    std::vector<std::array<float, 4>> values;

    void validate(std::size_t joint_count) const;
};

struct AnimationClip final {
    std::string name;
    float duration{0.0F};
    std::vector<AnimationChannel> channels;

    void validate(std::size_t joint_count) const;
    [[nodiscard]] std::vector<Transform> sample(const Skeleton& skeleton,
                                                float time_seconds,
                                                bool loop = true) const;
};

struct ModelData final {
    std::filesystem::path source_path;
    std::vector<ModelMaterial> materials;
    std::vector<ModelPart> parts;
    std::vector<std::string> warnings;
    std::optional<Skeleton> skeleton;
    std::vector<AnimationClip> animations;

    void validate() const;
    [[nodiscard]] std::size_t triangle_count() const noexcept;
};

[[nodiscard]] std::shared_ptr<const ModelData> load_obj(
    const std::filesystem::path& path);
[[nodiscard]] std::shared_ptr<const ModelData> load_gltf(
    const std::filesystem::path& path);

class ModelCache final {
public:
    ModelCache() = default;
    ModelCache(const ModelCache&) = delete;
    ModelCache& operator=(const ModelCache&) = delete;

    [[nodiscard]] std::shared_ptr<const ModelData> load(
        const std::filesystem::path& path);
    [[nodiscard]] std::size_t size() const noexcept;
    void clear() noexcept;

private:
    mutable std::mutex mutex_;
    std::unordered_map<std::string, std::shared_ptr<const ModelData>> models_;
};

} // namespace easy3d
