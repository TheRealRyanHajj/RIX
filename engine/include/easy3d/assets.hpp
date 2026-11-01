#pragma once

#include "easy3d/core.hpp"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <mutex>
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
    TextureFilter min_filter{TextureFilter::Linear};
    TextureFilter mag_filter{TextureFilter::Linear};
    TextureFilter mip_filter{TextureFilter::Linear};
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
        TextureColorSpace color_space = TextureColorSpace::Srgb);
    [[nodiscard]] std::size_t size() const noexcept;
    void clear() noexcept;

private:
    mutable std::mutex mutex_;
    std::unordered_map<std::string, std::shared_ptr<const ImageData>> images_;
};

} // namespace easy3d
