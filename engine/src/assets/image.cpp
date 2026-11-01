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
    throw AssetError("PNG/JPEG texture decoding requires an Easy3D graphics-enabled build: " +
                     canonical.string());
#endif
}

std::shared_ptr<const ImageData> TextureCache::load(const std::filesystem::path& path,
                                                    const TextureColorSpace color_space) {
    const std::filesystem::path canonical = checked_canonical_path(path);
    const std::string key = cache_key(canonical, color_space);
    std::scoped_lock lock(mutex_);
    const auto found = images_.find(key);
    if (found != images_.end()) {
        return found->second;
    }

    std::shared_ptr<const ImageData> image = load_image(canonical, color_space);
    images_.emplace(key, image);
    return image;
}

std::size_t TextureCache::size() const noexcept {
    std::scoped_lock lock(mutex_);
    return images_.size();
}

void TextureCache::clear() noexcept {
    std::scoped_lock lock(mutex_);
    images_.clear();
}

} // namespace easy3d
