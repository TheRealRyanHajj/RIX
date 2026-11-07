#include "easy3d/assets.hpp"

#if defined(EASY3D_HAS_GRAPHICS)
#include <bimg/bimg.h>
#include <bimg/decode.h>
#include <bx/allocator.h>
#include <bx/error.h>
#endif

#include <algorithm>
#include <cctype>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <system_error>

namespace easy3d {
namespace {

[[nodiscard]] std::string lowercase(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](const unsigned char character) {
        return static_cast<char>(std::tolower(character));
    });
    return value;
}

[[nodiscard]] std::filesystem::path checked_canonical_path(
    const std::filesystem::path& path) {
    if (path.empty()) {
        throw MissingAssetError("texture asset path is empty");
    }

    std::error_code error;
    const bool exists = std::filesystem::is_regular_file(path, error);
    if (error || !exists) {
        throw MissingAssetError("texture asset does not exist or is not a file: " +
                                path.string());
    }

    std::filesystem::path canonical = std::filesystem::weakly_canonical(path, error);
    if (error) {
        throw AssetError("failed to resolve texture asset path '" + path.string() +
                         "': " + error.message());
    }
    return canonical;
}

[[nodiscard]] std::string cache_key(const std::filesystem::path& canonical,
                                    const TextureColorSpace color_space) {
    std::string path = canonical.generic_string();
#if defined(_WIN32)
    path = lowercase(std::move(path));
#endif
    path.push_back('|');
    path.push_back(color_space == TextureColorSpace::Srgb ? 's' : 'l');
    return path;
}

void validate_extension(const std::filesystem::path& path) {
    const std::string extension = lowercase(path.extension().string());
    if (extension != ".png" && extension != ".jpg" && extension != ".jpeg") {
        throw AssetError("unsupported texture format '" + extension +
                         "' for asset: " + path.string() +
                         " (supported: .png, .jpg, .jpeg)");
    }
}

[[nodiscard]] std::vector<std::uint8_t> read_asset(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) {
        throw AssetError("failed to open texture asset: " + path.string());
    }

    const std::streamoff length = stream.tellg();
    if (length <= 0) {
        throw AssetError("texture asset is empty: " + path.string());
    }
    if (static_cast<std::uintmax_t>(length) >
        static_cast<std::uintmax_t>(std::numeric_limits<std::uint32_t>::max())) {
        throw AssetError("texture asset exceeds the 4 GiB decoder limit: " + path.string());
    }

    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(length));
    stream.seekg(0, std::ios::beg);
    if (!stream.read(reinterpret_cast<char*>(bytes.data()), length)) {
        throw AssetError("failed to read texture asset: " + path.string());
    }
    return bytes;
}

} // namespace

void ImageData::validate() const {
    if (width == 0 || height == 0) {
        throw AssetError("decoded texture dimensions must be nonzero");
    }
    const std::uint64_t expected =
        static_cast<std::uint64_t>(width) * static_cast<std::uint64_t>(height) * 4ULL;
    if (expected != rgba8.size()) {
        throw AssetError("decoded texture must contain exactly width * height * 4 RGBA8 bytes");
    }
    if (revision == 0) {
        throw AssetError("decoded texture revision must be nonzero");
    }
}

std::size_t ImageData::byte_size() const noexcept {
    return rgba8.size();
}

std::shared_ptr<const ImageData> load_image(const std::filesystem::path& path,
                                            const TextureColorSpace color_space) {
    const std::filesystem::path canonical = checked_canonical_path(path);
    validate_extension(canonical);
    const std::vector<std::uint8_t> bytes = read_asset(canonical);

#if defined(EASY3D_HAS_GRAPHICS)
    bx::DefaultAllocator allocator;
    bx::Error error;
    bimg::ImageContainer* decoded = bimg::imageParse(
        &allocator,
        bytes.data(),
        static_cast<std::uint32_t>(bytes.size()),
        bimg::TextureFormat::RGBA8,
        &error);
    if (decoded == nullptr) {
        const bx::StringLiteral& detail = error.getMessage();
        const std::string message(detail.getCPtr(),
                                  static_cast<std::size_t>(detail.getLength()));
        throw AssetError("failed to decode texture asset '" + canonical.string() +
                         "' as PNG/JPEG" + (message.empty() ? std::string{} : ": " + message));
    }

    try {
        const std::uint64_t expected = static_cast<std::uint64_t>(decoded->m_width) *
                                       static_cast<std::uint64_t>(decoded->m_height) * 4ULL;
        if (decoded->m_format != bimg::TextureFormat::RGBA8 || expected != decoded->m_size ||
            expected > std::numeric_limits<std::size_t>::max()) {
            throw AssetError("decoder returned an unexpected pixel layout for texture asset: " +
                             canonical.string());
        }

        auto image = std::make_shared<ImageData>();
        image->source_path = canonical;
        image->width = decoded->m_width;
        image->height = decoded->m_height;
        image->color_space = color_space;
        const auto* begin = static_cast<const std::uint8_t*>(decoded->m_data);
        image->rgba8.assign(begin, begin + decoded->m_size);
        image->validate();
        bimg::imageFree(decoded);
        return image;
    } catch (...) {
        bimg::imageFree(decoded);
        throw;
    }
#else
    (void)bytes;
    (void)color_space;
    throw AssetError("PNG/JPEG texture decoding requires an RIX graphics-enabled build: " +
                     canonical.string());
#endif
}

std::shared_ptr<const ImageData> TextureCache::load(const std::filesystem::path& path,
                                                    const TextureColorSpace color_space,
                                                    const bool hot_reload) {
    const std::filesystem::path canonical = checked_canonical_path(path);
    const std::string key = cache_key(canonical, color_space);
    std::scoped_lock lock(mutex_);
    const auto found = images_.find(key);
    if (found != images_.end()) {
        found->second.hot_reload = found->second.hot_reload || hot_reload;
        return found->second.image;
    }

    const auto decoded = load_image(canonical, color_space);
    auto image = std::make_shared<ImageData>(*decoded);
    std::error_code error;
    const auto modified = std::filesystem::last_write_time(canonical, error);
    images_.emplace(key, Entry{image, error ? std::filesystem::file_time_type{} : modified,
                               hot_reload});
    return image;
}

std::size_t TextureCache::poll_changes(
    const std::chrono::milliseconds minimum_interval) const noexcept {
    try {
        const auto now = std::chrono::steady_clock::now();
        std::scoped_lock lock(mutex_);
        if (last_poll_ != std::chrono::steady_clock::time_point{} &&
            now - last_poll_ < minimum_interval) {
            return 0;
        }
        last_poll_ = now;
        std::size_t updated = 0;
        for (auto& [key, entry] : images_) {
            (void)key;
            if (!entry.hot_reload || !entry.image) {
                continue;
            }
            std::error_code error;
            const auto modified =
                std::filesystem::last_write_time(entry.image->source_path, error);
            if (error || modified == entry.modified) {
                continue;
            }
            // Remember this write even if decoding fails. A later editor save
            // changes the timestamp and retries while the previous valid image
            // remains active.
            entry.modified = modified;
            try {
                const auto decoded =
                    load_image(entry.image->source_path, entry.image->color_space);
                const std::uint64_t revision = entry.image->revision + 1;
                *entry.image = *decoded;
                entry.image->revision = revision == 0 ? 1 : revision;
                ++updated;
            } catch (const std::exception& reload_error) {
                std::cerr << "RIX texture reload kept previous image for '"
                          << entry.image->source_path.string() << "': "
                          << reload_error.what() << '\n';
            }
        }
        return updated;
    } catch (...) {
        return 0;
    }
}

std::size_t TextureCache::size() const noexcept {
    std::scoped_lock lock(mutex_);
    return images_.size();
}

void TextureCache::clear() noexcept {
    std::scoped_lock lock(mutex_);
    images_.clear();
    last_poll_ = {};
}

} // namespace easy3d
