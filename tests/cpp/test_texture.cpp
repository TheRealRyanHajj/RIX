#include "easy3d/assets.hpp"

#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

namespace {

constexpr std::array<std::uint8_t, 130> png_bytes{
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d,
    0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x02,
    0x08, 0x06, 0x00, 0x00, 0x00, 0x72, 0xb6, 0x0d, 0x24, 0x00, 0x00, 0x00, 0x01,
    0x73, 0x52, 0x47, 0x42, 0x00, 0xae, 0xce, 0x1c, 0xe9, 0x00, 0x00, 0x00, 0x04,
    0x67, 0x41, 0x4d, 0x41, 0x00, 0x00, 0xb1, 0x8f, 0x0b, 0xfc, 0x61, 0x05, 0x00,
    0x00, 0x00, 0x09, 0x70, 0x48, 0x59, 0x73, 0x00, 0x00, 0x0e, 0xc3, 0x00, 0x00,
    0x0e, 0xc3, 0x01, 0xc7, 0x6f, 0xa8, 0x64, 0x00, 0x00, 0x00, 0x17, 0x49, 0x44,
    0x41, 0x54, 0x18, 0x57, 0x63, 0xf8, 0xcf, 0xc0, 0xf0, 0x9f, 0xa1, 0x81, 0xe1,
    0x3f, 0x03, 0x03, 0xc3, 0x7f, 0x30, 0x00, 0x00, 0x43, 0xd4, 0x09, 0x78, 0x4e,
    0x54, 0x9d, 0x95, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44, 0xae, 0x42,
    0x60, 0x82,
};

class TemporaryDirectory final {
public:
    TemporaryDirectory()
        : path_(std::filesystem::temp_directory_path() /
                ("easy3d_texture_test_" + std::to_string(++sequence_))) {
        std::filesystem::create_directories(path_);
    }

    ~TemporaryDirectory() { std::filesystem::remove_all(path_); }

    [[nodiscard]] const std::filesystem::path& path() const noexcept { return path_; }

private:
    static inline std::uint64_t sequence_{0};
    std::filesystem::path path_;
};

void write_bytes(const std::filesystem::path& path,
                 const std::uint8_t* data,
                 const std::size_t size) {
    std::ofstream stream(path, std::ios::binary);
    stream.write(reinterpret_cast<const char*>(data), static_cast<std::streamsize>(size));
    if (!stream) {
        throw std::runtime_error("failed to create texture test fixture");
    }
}

[[nodiscard]] bool expect_asset_error(const std::filesystem::path& path) {
    try {
        (void)easy3d::load_image(path);
    } catch (const easy3d::AssetError&) {
        return true;
    }
    return false;
}

} // namespace

int main() {
    try {
        TemporaryDirectory temporary;
        const std::filesystem::path png = temporary.path() / "pixel.png";
        write_bytes(png, png_bytes.data(), png_bytes.size());

        const auto direct = easy3d::load_image(png);
        if (direct->width != 2 || direct->height != 2 || direct->byte_size() != 16 ||
            direct->color_space != easy3d::TextureColorSpace::Srgb) {
            std::cerr << "decoded PNG metadata or RGBA8 layout is incorrect\n";
            return 1;
        }

        easy3d::TextureCache cache;
        const auto first = cache.load(png);
        const auto second = cache.load(temporary.path() / "." / "pixel.png");
        const auto linear = cache.load(png, easy3d::TextureColorSpace::Linear);
        if (first.get() != second.get() || first.get() == linear.get() || cache.size() != 2) {
            std::cerr << "canonical path/color-space texture cache keys are incorrect\n";
            return 2;
        }
        cache.clear();
        if (cache.size() != 0 || first->byte_size() != 16) {
            std::cerr << "clearing the cache invalidated a referenced image\n";
            return 3;
        }

        bool missing_failed = false;
        try {
            (void)cache.load(temporary.path() / "missing.png");
        } catch (const easy3d::MissingAssetError& error) {
            missing_failed = std::string(error.what()).find("missing.png") != std::string::npos;
        }
        if (!missing_failed) {
            std::cerr << "missing asset did not produce an actionable MissingAssetError\n";
            return 4;
        }

        const std::array<std::uint8_t, 4> malformed{0xde, 0xad, 0xbe, 0xef};
        const std::filesystem::path malformed_png = temporary.path() / "malformed.png";
        write_bytes(malformed_png, malformed.data(), malformed.size());
        const std::filesystem::path unsupported = temporary.path() / "pixel.bmp";
        write_bytes(unsupported, png_bytes.data(), png_bytes.size());
        if (!expect_asset_error(malformed_png) || !expect_asset_error(unsupported)) {
            std::cerr << "malformed or unsupported textures were not rejected\n";
            return 5;
        }

        std::cout << "easy3d_texture_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "easy3d_texture_tests: FAIL: " << error.what() << '\n';
        return 10;
    }
}
