#include "renderer/bgfx_renderer.hpp"

#include "easy3d/assets.hpp"
#include "easy3d/core.hpp"
#include "easy3d/renderer.hpp"
#include "easy3d/scene.hpp"

#include <bgfx/bgfx.h>
#include <bimg/bimg.h>
#include <bimg/encode.h>
#include <bx/allocator.h>
#include <glm/ext/matrix_transform.hpp>
#include <glm/gtc/matrix_inverse.hpp>
#include <glm/gtc/type_ptr.hpp>
#include <glm/gtc/quaternion.hpp>

#define STB_TRUETYPE_IMPLEMENTATION
#include <stb_truetype.h>
#include <roboto_regular.ttf.h>

#include "fs_solid_color.sc.bin.h"
#include "fs_textured.sc.bin.h"
#include "fs_postprocess.sc.bin.h"
#include "fs_sky.sc.bin.h"
#include "fs_shadow.sc.bin.h"
#include "fs_point_shadow.sc.bin.h"
#include "fs_ui.sc.bin.h"
#include "vs_solid_color.sc.bin.h"
#include "vs_solid_color_instanced.sc.bin.h"
#include "vs_textured.sc.bin.h"
#include "vs_textured_instanced.sc.bin.h"
#include "vs_postprocess.sc.bin.h"
#include "vs_shadow.sc.bin.h"
#include "vs_shadow_instanced.sc.bin.h"
#include "vs_point_shadow.sc.bin.h"
#include "vs_point_shadow_instanced.sc.bin.h"
#include "vs_ui.sc.bin.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

namespace easy3d::renderer {
namespace {

constexpr bgfx::ViewId shadow_view = 0;
constexpr bgfx::ViewId spot_shadow_view = 1;
constexpr bgfx::ViewId point_shadow_first_view = 2;
constexpr bgfx::ViewId main_view = 8;
constexpr bgfx::ViewId postprocess_view = 9;
constexpr bgfx::ViewId ui_view = 10;
constexpr bgfx::ViewId capture_view = 11;
constexpr bgfx::ViewId capture_blit_view = 12;
constexpr std::size_t max_pending_viewport_readbacks = 8;
constexpr std::size_t max_directional_lights = 4;
constexpr std::size_t max_point_lights = 64;
constexpr std::size_t max_spot_lights = 32;

[[nodiscard]] float srgb_to_linear_channel(const float value) noexcept {
    return value <= 0.04045F
        ? value / 12.92F
        : std::pow((value + 0.055F) / 1.055F, 2.4F);
}

[[nodiscard]] Color render_color(const Color color,
                                 const bool linear_output) noexcept {
    if (!linear_output) return color;
    return {srgb_to_linear_channel(color.r),
            srgb_to_linear_channel(color.g),
            srgb_to_linear_channel(color.b),
            color.a};
}

struct GpuVertex final {
    float position[3];
    float normal[3];
    float uv[2];
    std::uint32_t color;
    float tangent[4];
};

struct PostprocessVertex final {
    float position[3];
    float uv[2];
};

struct UiVertex final {
    float position[3];
    float uv[2];
    std::uint32_t color;
};

class GpuMesh final {
public:
    GpuMesh() = default;

    GpuMesh(const bgfx::VertexBufferHandle vertex_buffer,
            const bgfx::IndexBufferHandle index_buffer,
            const std::uint32_t index_count)
        : vertex_buffer_(vertex_buffer), index_buffer_(index_buffer), index_count_(index_count) {}

    ~GpuMesh() { release(); }

    GpuMesh(const GpuMesh&) = delete;
    GpuMesh& operator=(const GpuMesh&) = delete;

    GpuMesh(GpuMesh&& other) noexcept
        : vertex_buffer_(std::exchange(other.vertex_buffer_, BGFX_INVALID_HANDLE)),
          index_buffer_(std::exchange(other.index_buffer_, BGFX_INVALID_HANDLE)),
          index_count_(std::exchange(other.index_count_, 0)) {}

    GpuMesh& operator=(GpuMesh&& other) noexcept {
        if (this != &other) {
            release();
            vertex_buffer_ = std::exchange(other.vertex_buffer_, BGFX_INVALID_HANDLE);
            index_buffer_ = std::exchange(other.index_buffer_, BGFX_INVALID_HANDLE);
            index_count_ = std::exchange(other.index_count_, 0);
        }
        return *this;
    }

    void bind() const {
        if (!bgfx::isValid(vertex_buffer_) || !bgfx::isValid(index_buffer_)) {
            throw EngineError("attempted to bind a released GPU mesh");
        }
        bgfx::setVertexBuffer(0, vertex_buffer_);
        bgfx::setIndexBuffer(index_buffer_, 0, index_count_);
    }

private:
    void release() noexcept {
        if (bgfx::isValid(index_buffer_)) {
            bgfx::destroy(index_buffer_);
            index_buffer_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(vertex_buffer_)) {
            bgfx::destroy(vertex_buffer_);
            vertex_buffer_ = BGFX_INVALID_HANDLE;
        }
        index_count_ = 0;
    }

    bgfx::VertexBufferHandle vertex_buffer_{BGFX_INVALID_HANDLE};
    bgfx::IndexBufferHandle index_buffer_{BGFX_INVALID_HANDLE};
    std::uint32_t index_count_{0};
};

class MeshLifetimeManager final {
public:
    using Handle = std::size_t;

    explicit MeshLifetimeManager(const bgfx::VertexLayout& layout) : layout_(layout) {}

    [[nodiscard]] Handle upload(const MeshData& mesh) {
        mesh.validate();
        if (mesh.vertices.size() > std::numeric_limits<std::uint32_t>::max() ||
            mesh.indices.size() > std::numeric_limits<std::uint32_t>::max()) {
            throw EngineError("mesh exceeds bgfx's 32-bit buffer limits");
        }

        std::vector<GpuVertex> vertices;
        vertices.reserve(mesh.vertices.size());
        for (const Vertex& vertex : mesh.vertices) {
            vertices.push_back({
                {vertex.position.x, vertex.position.y, vertex.position.z},
                {vertex.normal.x, vertex.normal.y, vertex.normal.z},
                {vertex.uv.x, vertex.uv.y},
                vertex.color.rgba8(),
                {vertex.tangent[0], vertex.tangent[1], vertex.tangent[2], vertex.tangent[3]},
            });
        }

        const bgfx::Memory* vertex_memory =
            bgfx::copy(vertices.data(), static_cast<std::uint32_t>(vertices.size() * sizeof(GpuVertex)));
        const bgfx::Memory* index_memory = bgfx::copy(
            mesh.indices.data(), static_cast<std::uint32_t>(mesh.indices.size() * sizeof(std::uint32_t)));
        const bgfx::VertexBufferHandle vertex_buffer = bgfx::createVertexBuffer(vertex_memory, layout_);
        const bgfx::IndexBufferHandle index_buffer =
            bgfx::createIndexBuffer(index_memory, BGFX_BUFFER_INDEX32);
        if (!bgfx::isValid(vertex_buffer) || !bgfx::isValid(index_buffer)) {
            if (bgfx::isValid(index_buffer)) {
                bgfx::destroy(index_buffer);
            }
            if (bgfx::isValid(vertex_buffer)) {
                bgfx::destroy(vertex_buffer);
            }
            throw EngineError("bgfx failed to allocate an indexed GPU mesh");
        }

        meshes_.emplace_back(vertex_buffer,
                             index_buffer,
                             static_cast<std::uint32_t>(mesh.indices.size()));
        triangle_count_ += mesh.triangle_count();
        return meshes_.size() - 1;
    }

    [[nodiscard]] Handle upload_cached(const MeshData& mesh) {
        const auto found = shared_.find(&mesh);
        if (found != shared_.end()) {
            return found->second;
        }
        const Handle handle = upload(mesh);
        shared_.emplace(&mesh, handle);
        return handle;
    }

    [[nodiscard]] Bounds bounds_cached(const MeshData& mesh) {
        const auto found = bounds_.find(&mesh);
        if (found != bounds_.end()) {
            return found->second;
        }
        const Bounds result = mesh.bounds();
        bounds_.emplace(&mesh, result);
        return result;
    }

    void bind(const Handle handle) const {
        if (handle >= meshes_.size()) {
            throw EngineError("invalid GPU mesh handle");
        }
        meshes_[handle].bind();
    }

    void reset() noexcept {
        meshes_.clear();
        triangle_count_ = 0;
        shared_.clear();
        bounds_.clear();
    }

    [[nodiscard]] std::size_t size() const noexcept { return meshes_.size(); }
    [[nodiscard]] std::size_t triangle_count() const noexcept { return triangle_count_; }

private:
    bgfx::VertexLayout layout_;
    std::vector<GpuMesh> meshes_;
    std::size_t triangle_count_{0};
    std::unordered_map<const MeshData*, Handle> shared_;
    std::unordered_map<const MeshData*, Bounds> bounds_;
};

[[nodiscard]] std::uint64_t texture_flags(const TextureColorSpace color_space,
                                          const TextureSampler& sampler) noexcept {
    std::uint64_t flags = color_space == TextureColorSpace::Srgb ? BGFX_TEXTURE_SRGB : 0;
    if (sampler.min_filter == TextureFilter::Nearest) {
        flags |= BGFX_SAMPLER_MIN_POINT;
    }
    if (sampler.mag_filter == TextureFilter::Nearest) {
        flags |= BGFX_SAMPLER_MAG_POINT;
    }
    if (sampler.mip_filter == TextureFilter::Nearest) {
        flags |= BGFX_SAMPLER_MIP_POINT;
    }
    if (sampler.wrap_u == TextureWrap::Clamp) {
        flags |= BGFX_SAMPLER_U_CLAMP;
    }
    if (sampler.wrap_v == TextureWrap::Clamp) {
        flags |= BGFX_SAMPLER_V_CLAMP;
    }
    return flags;
}

struct TextureUploadData final {
    std::vector<std::uint8_t> bytes;
    bool has_mips{false};
};

[[nodiscard]] TextureUploadData texture_upload_data(const ImageData& image) {
    TextureUploadData result{image.rgba8, false};
    if (image.width == 1 && image.height == 1) {
        return result;
    }
    bx::DefaultAllocator allocator;
    bimg::ImageContainer* base = bimg::imageAlloc(&allocator,
                                                   bimg::TextureFormat::RGBA8,
                                                   image.width,
                                                   image.height,
                                                   0,
                                                   1,
                                                   false,
                                                   false,
                                                   image.rgba8.data());
    if (base == nullptr) {
        return result;
    }
    bimg::ImageContainer* mips = bimg::imageGenerateMips(
        &allocator, *base, image.color_space == TextureColorSpace::Srgb);
    bimg::imageFree(base);
    if (mips == nullptr || mips->m_numMips <= 1) {
        if (mips != nullptr) {
            bimg::imageFree(mips);
        }
        return result;
    }
    const auto* begin = static_cast<const std::uint8_t*>(mips->m_data);
    result.bytes.assign(begin, begin + mips->m_size);
    result.has_mips = true;
    bimg::imageFree(mips);
    return result;
}

class GpuTexture final {
public:
    GpuTexture() = default;
    explicit GpuTexture(const bgfx::TextureHandle texture) : texture_(texture) {}
    ~GpuTexture() { release(); }

    GpuTexture(const GpuTexture&) = delete;
    GpuTexture& operator=(const GpuTexture&) = delete;
    GpuTexture(GpuTexture&& other) noexcept
        : texture_(std::exchange(other.texture_, BGFX_INVALID_HANDLE)) {}
    GpuTexture& operator=(GpuTexture&& other) noexcept {
        if (this != &other) {
            release();
            texture_ = std::exchange(other.texture_, BGFX_INVALID_HANDLE);
        }
        return *this;
    }

    void bind(const std::uint8_t stage, const bgfx::UniformHandle sampler) const {
        if (!bgfx::isValid(texture_)) {
            throw EngineError("attempted to bind a released GPU texture");
        }
        bgfx::setTexture(stage, sampler, texture_);
    }

private:
    void release() noexcept {
        if (bgfx::isValid(texture_)) {
            bgfx::destroy(texture_);
            texture_ = BGFX_INVALID_HANDLE;
        }
    }

    bgfx::TextureHandle texture_{BGFX_INVALID_HANDLE};
};

class TextureLifetimeManager final {
public:
    using Handle = std::size_t;

    [[nodiscard]] Handle upload(const ImageData& image,
                                const TextureSampler& sampler = {}) {
        image.validate();
        if (image.width > std::numeric_limits<std::uint16_t>::max() ||
            image.height > std::numeric_limits<std::uint16_t>::max() ||
            image.byte_size() > std::numeric_limits<std::uint32_t>::max()) {
            throw EngineError("texture exceeds bgfx's 2D RGBA8 resource limits");
        }

        const std::uint64_t flags = texture_flags(image.color_space, sampler);
        const TextureUploadData upload_data = texture_upload_data(image);
        if (upload_data.bytes.size() > std::numeric_limits<std::uint32_t>::max()) {
            throw EngineError("texture mip chain exceeds bgfx's 32-bit upload limit");
        }
        if (!bgfx::isTextureValid(0,
                                  upload_data.has_mips,
                                  1,
                                  bgfx::TextureFormat::RGBA8,
                                  flags)) {
            throw EngineError("active renderer does not support the requested RGBA8 texture flags");
        }
        const bgfx::Memory* memory = bgfx::copy(
            upload_data.bytes.data(),
            static_cast<std::uint32_t>(upload_data.bytes.size()));
        const bgfx::TextureHandle texture = bgfx::createTexture2D(
            static_cast<std::uint16_t>(image.width),
            static_cast<std::uint16_t>(image.height),
            upload_data.has_mips,
            1,
            bgfx::TextureFormat::RGBA8,
            flags,
            memory);
        if (!bgfx::isValid(texture)) {
            throw EngineError("bgfx failed to allocate an RGBA8 GPU texture");
        }
        Handle handle = textures_.size();
        for (Handle candidate = 0; candidate < texture_sizes_.size(); ++candidate) {
            if (texture_sizes_[candidate] == 0) {
                handle = candidate;
                break;
            }
        }
        if (handle == textures_.size()) {
            textures_.emplace_back(texture);
            texture_sizes_.push_back(upload_data.bytes.size());
        } else {
            textures_[handle] = GpuTexture(texture);
            texture_sizes_[handle] = upload_data.bytes.size();
        }
        byte_size_ += upload_data.bytes.size();
        ++active_count_;
        return handle;
    }

    [[nodiscard]] Handle upload_cached(
        const std::shared_ptr<const ImageData>& image,
        const TextureSampler& sampler = {}) {
        if (!image) {
            throw EngineError("cannot upload an empty shared image");
        }
        auto found = shared_.find(image.get());
        if (found != shared_.end()) {
            std::erase_if(found->second, [&](const SharedTexture& cached) {
                if (!cached.owner.expired()) {
                    return false;
                }
                release(cached.handle);
                return true;
            });
            for (SharedTexture& cached : found->second) {
                if (cached.sampler == sampler) {
                    if (cached.revision != image->revision) {
                        replace(cached.handle, *image, sampler);
                        cached.revision = image->revision;
                    }
                    return cached.handle;
                }
            }
            if (found->second.empty()) {
                shared_.erase(found);
            }
        }
        const Handle handle = upload(*image, sampler);
        shared_[image.get()].push_back({image, sampler, handle, image->revision});
        return handle;
    }

    void collect_expired() {
        for (auto found = shared_.begin(); found != shared_.end();) {
            std::erase_if(found->second, [&](const SharedTexture& cached) {
                if (!cached.owner.expired()) {
                    return false;
                }
                release(cached.handle);
                return true;
            });
            if (found->second.empty()) {
                found = shared_.erase(found);
            } else {
                ++found;
            }
        }
    }

    void bind(const Handle handle,
              const bgfx::UniformHandle sampler,
              const std::uint8_t stage = 0) const {
        if (handle >= textures_.size()) {
            throw EngineError("invalid GPU texture handle");
        }
        textures_[handle].bind(stage, sampler);
    }

    void reset() noexcept {
        textures_.clear();
        byte_size_ = 0;
        active_count_ = 0;
        texture_sizes_.clear();
        shared_.clear();
    }

    [[nodiscard]] std::size_t size() const noexcept { return active_count_; }
    [[nodiscard]] std::size_t byte_size() const noexcept { return byte_size_; }

private:
    void release(const Handle handle) {
        if (handle >= textures_.size() || handle >= texture_sizes_.size() ||
            texture_sizes_[handle] == 0) {
            return;
        }
        byte_size_ -= texture_sizes_[handle];
        texture_sizes_[handle] = 0;
        textures_[handle] = GpuTexture{};
        --active_count_;
    }

    void replace(const Handle handle,
                 const ImageData& image,
                 const TextureSampler& sampler) {
        image.validate();
        if (handle >= textures_.size() || handle >= texture_sizes_.size() ||
            image.width > std::numeric_limits<std::uint16_t>::max() ||
            image.height > std::numeric_limits<std::uint16_t>::max() ||
            image.byte_size() > std::numeric_limits<std::uint32_t>::max()) {
            throw EngineError("reloaded texture exceeds bgfx resource limits");
        }
        const std::uint64_t flags = texture_flags(image.color_space, sampler);
        const TextureUploadData upload_data = texture_upload_data(image);
        if (upload_data.bytes.size() > std::numeric_limits<std::uint32_t>::max()) {
            throw EngineError("reloaded texture mip chain exceeds bgfx's upload limit");
        }
        const bgfx::Memory* memory = bgfx::copy(
            upload_data.bytes.data(),
            static_cast<std::uint32_t>(upload_data.bytes.size()));
        const bgfx::TextureHandle texture = bgfx::createTexture2D(
            static_cast<std::uint16_t>(image.width),
            static_cast<std::uint16_t>(image.height),
            upload_data.has_mips,
            1,
            bgfx::TextureFormat::RGBA8,
            flags,
            memory);
        if (!bgfx::isValid(texture)) {
            throw EngineError("bgfx failed to replace a reloaded RGBA8 texture");
        }
        byte_size_ -= texture_sizes_[handle];
        byte_size_ += upload_data.bytes.size();
        texture_sizes_[handle] = upload_data.bytes.size();
        textures_[handle] = GpuTexture(texture);
    }

    struct SharedTexture final {
        std::weak_ptr<const ImageData> owner;
        TextureSampler sampler;
        Handle handle;
        std::uint64_t revision;
    };

    std::vector<GpuTexture> textures_;
    std::vector<std::size_t> texture_sizes_;
    std::size_t byte_size_{0};
    std::size_t active_count_{0};
    std::unordered_map<const ImageData*, std::vector<SharedTexture>> shared_;
};

struct DrawItem final {
    MeshLifetimeManager::Handle mesh;
    Material material;
    glm::mat4 transform{1.0F};
    std::optional<TextureLifetimeManager::Handle> texture;
};

struct SceneBatch final {
    MeshLifetimeManager::Handle mesh;
    Material material;
    struct Textures final {
        std::optional<TextureLifetimeManager::Handle> albedo;
        std::optional<TextureLifetimeManager::Handle> normal;
        std::optional<TextureLifetimeManager::Handle> roughness;
        std::optional<TextureLifetimeManager::Handle> metallic;
        std::optional<TextureLifetimeManager::Handle> emissive;
        std::optional<TextureLifetimeManager::Handle> ambient_occlusion;

        friend bool operator==(const Textures&, const Textures&) = default;
    } textures;
    struct Mapping final {
        std::array<float, 12> scales{};
        std::array<float, 24> atlas{};
        float mode{0.0F};

        friend bool operator==(const Mapping&, const Mapping&) = default;
    } mapping;
    std::vector<glm::mat4> transforms;
    bool instancing_eligible{true};
};

struct ShadowBatch final {
    MeshLifetimeManager::Handle mesh;
    CullMode cull_mode{CullMode::Back};
    std::vector<glm::mat4> transforms;
};

struct LightingState final {
    std::array<float, 4> ambient{0.25F, 0.25F, 0.25F, 1.0F};
    std::array<std::array<float, 4>, max_directional_lights> directional_directions{};
    std::array<std::array<float, 4>, max_directional_lights> directional_colors{};
    std::array<std::array<float, 4>, max_point_lights> point_positions_ranges{};
    std::array<std::array<float, 4>, max_point_lights> point_colors{};
    std::array<std::array<float, 4>, max_spot_lights> spot_positions_ranges{};
    std::array<std::array<float, 4>, max_spot_lights> spot_directions_outer{};
    std::array<std::array<float, 4>, max_spot_lights> spot_colors_inner{};
    std::array<float, 4> counts{};
};

[[nodiscard]] std::uint16_t view_extent(const std::uint32_t value) noexcept {
    return static_cast<std::uint16_t>(
        std::min(value, static_cast<std::uint32_t>(std::numeric_limits<std::uint16_t>::max())));
}

[[nodiscard]] std::uint64_t cull_state(const CullMode mode) noexcept {
    switch (mode) {
    case CullMode::Back:
        // RIX mesh data uses counter-clockwise front faces, so clockwise
        // triangles are the back faces on D3D11.
        return BGFX_STATE_CULL_CW;
    case CullMode::Front:
        return BGFX_STATE_CULL_CCW;
    case CullMode::None:
        return 0;
    }
    return BGFX_STATE_CULL_CW;
}

[[nodiscard]] std::uint64_t render_state(const Material& material) {
    material.validate();
    std::uint64_t state = BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_A;
    if (material.depth_write) {
        state |= BGFX_STATE_WRITE_Z;
    }
    if (material.depth_test) {
        state |= BGFX_STATE_DEPTH_TEST_LESS;
    }
    return state | cull_state(material.cull_mode);
}

[[nodiscard]] CullMode transformed_cull_mode(const CullMode mode,
                                             const Transform& transform) noexcept {
    if (transform.scale.x * transform.scale.y * transform.scale.z >= 0.0F) {
        return mode;
    }
    if (mode == CullMode::Back) return CullMode::Front;
    if (mode == CullMode::Front) return CullMode::Back;
    return CullMode::None;
}

[[nodiscard]] CullMode model_cull_mode(const RenderComponent& component,
                                       const ModelMaterial& material) noexcept {
    if (component.cull_mode_override.has_value()) {
        return *component.cull_mode_override;
    }
    return material.double_sided ? CullMode::None : CullMode::Back;
}

[[nodiscard]] glm::mat4 translated(const float x, const float y, const float z) {
    return glm::translate(glm::mat4(1.0F), glm::vec3(x, y, z));
}

[[nodiscard]] bool has_uniform_scale(const Transform& transform) noexcept {
    const float x = std::abs(transform.scale.x);
    const float y = std::abs(transform.scale.y);
    const float z = std::abs(transform.scale.z);
    constexpr float tolerance = 1.0e-5F;
    return std::abs(x - y) <= tolerance && std::abs(x - z) <= tolerance;
}

[[nodiscard]] TextureMode resolved_texture_mode(const RenderComponent& component) noexcept {
    if (component.texture_settings.mode != TextureMode::Auto) {
        return component.texture_settings.mode;
    }
    switch (component.kind) {
    case RenderKind::Cube:
    case RenderKind::Plane: return TextureMode::Tile;
    case RenderKind::Sphere: return TextureMode::Sphere;
    case RenderKind::Model: return TextureMode::Preserve;
    }
    return TextureMode::Preserve;
}

[[nodiscard]] SceneBatch::Mapping texture_mapping(const RenderComponent& component,
                                                  const Transform& world) {
    SceneBatch::Mapping mapping;
    mapping.scales = {1.0F, 1.0F, 0.0F, 0.0F,
                       1.0F, 1.0F, 0.0F, 0.0F,
                       1.0F, 1.0F, 0.0F, 0.0F};
    const TextureMode mode = resolved_texture_mode(component);
    mapping.mode = mode == TextureMode::Tile ? 1.0F
                 : mode == TextureMode::Atlas ? 2.0F
                 : mode == TextureMode::Sphere ? 3.0F
                 : 0.0F;
    if (!component.texture) {
        return mapping;
    }
    const Vec3 mapping_dimensions =
        mode == TextureMode::Atlas
            ? component.texture_settings.atlas_dimensions
            : Vec3{world.scale.x, world.scale.y, world.scale.z};
    const TextureMappingData calculated = calculate_texture_mapping(
        mode,
        mapping_dimensions,
        component.texture->width,
        component.texture->height,
        component.texture_settings.pixels_per_unit);
    for (std::size_t index = 0; index < calculated.repeat.size(); ++index) {
        mapping.scales[index * 4] = calculated.repeat[index].x;
        mapping.scales[index * 4 + 1] = calculated.repeat[index].y;
    }
    for (std::size_t index = 0; index < calculated.atlas.size(); ++index) {
        std::copy(calculated.atlas[index].begin(),
                  calculated.atlas[index].end(),
                  mapping.atlas.begin() + static_cast<std::ptrdiff_t>(index * 4));
    }
    return mapping;
}

} // namespace

class BgfxRenderer::Impl final {
    struct ViewportTarget final {
        std::uint32_t width{0};
        std::uint32_t height{0};
        bgfx::FrameBufferHandle scene_framebuffer{BGFX_INVALID_HANDLE};
        bgfx::TextureHandle scene_color{BGFX_INVALID_HANDLE};
        bgfx::FrameBufferHandle output_framebuffer{BGFX_INVALID_HANDLE};
        bgfx::TextureHandle output_color{BGFX_INVALID_HANDLE};
    };

    struct PendingViewportReadback final {
        std::uint32_t width{0};
        std::uint32_t height{0};
        std::uint32_t ready_frame{0};
        bgfx::TextureHandle staging{BGFX_INVALID_HANDLE};
        std::shared_ptr<std::vector<std::uint8_t>> pixels;
        bool abandoned{false};
    };

public:
    Impl() {
        for (auto& handle : point_shadow_framebuffers_) handle.idx = bgfx::kInvalidHandle;
    }

    void initialize(void* native_window,
                    const std::uint32_t width,
                    const std::uint32_t height,
                    const bool vsync,
                    const GraphicsPreset graphics_preset,
                    const bool geometry_diagnostic,
                    const Scene* const scene) {
        // Keep device and swap-chain work on the SDL/window thread. Calling
        // renderFrame before init selects bgfx's supported single-threaded mode.
        bgfx::renderFrame();

        bgfx::Init init;
        init.type = bgfx::RendererType::Direct3D11;
        init.fallback = false;
        init.swapChain.nwh = native_window;
        init.swapChain.width = std::max(width, 1U);
        init.swapChain.height = std::max(height, 1U);
        swap_chain_ = init.swapChain;
        reset_flags_ = vsync ? BGFX_RESET_VSYNC : BGFX_RESET_NONE;
        graphics_preset_ = graphics_preset;
        graphics_features_ = graphics_features(graphics_preset);
        init.reset = reset_flags_;

        if (!bgfx::init(init)) {
            throw EngineError("bgfx failed to initialize the Direct3D 11 renderer");
        }
        initialized_ = true;

        try {
            width_ = std::max(width, 1U);
            height_ = std::max(height, 1U);
            render_width_ = width_;
            render_height_ = height_;
            bgfx::setViewClear(main_view,
                               BGFX_CLEAR_COLOR | BGFX_CLEAR_DEPTH,
                               0x28344bff,
                               1.0F,
                               0);
            update_view_rect();

            layout_.begin()
                .add(bgfx::Attrib::Position, 3, bgfx::AttribType::Float)
                .add(bgfx::Attrib::Normal, 3, bgfx::AttribType::Float)
                .add(bgfx::Attrib::TexCoord0, 2, bgfx::AttribType::Float)
                .add(bgfx::Attrib::Color0, 4, bgfx::AttribType::Uint8, true)
                .add(bgfx::Attrib::Tangent, 4, bgfx::AttribType::Float)
                .end();
            postprocess_layout_.begin()
                .add(bgfx::Attrib::Position, 3, bgfx::AttribType::Float)
                .add(bgfx::Attrib::TexCoord0, 2, bgfx::AttribType::Float)
                .end();
            ui_layout_.begin()
                .add(bgfx::Attrib::Position, 3, bgfx::AttribType::Float)
                .add(bgfx::Attrib::TexCoord0, 2, bgfx::AttribType::Float)
                .add(bgfx::Attrib::Color0, 4, bgfx::AttribType::Uint8, true)
                .end();
            mesh_resources_ = std::make_unique<MeshLifetimeManager>(layout_);
            texture_resources_ = std::make_unique<TextureLifetimeManager>();
            ui_sampler_.wrap_u = TextureWrap::Clamp;
            ui_sampler_.wrap_v = TextureWrap::Clamp;
            scene_ = scene;
            create_programs();
            create_postprocess_target();
            create_shadow_target();
            create_material_fallbacks();
            create_font_atlas();
            bgfx::setViewMode(main_view, bgfx::ViewMode::Sequential);
            bgfx::setViewMode(ui_view, bgfx::ViewMode::Sequential);
            if (geometry_diagnostic) {
                create_geometry_diagnostic();
            }
            std::cout << "RIX graphics: enhanced-lighting="
                      << (graphics_features_.enhanced_lighting ? "on" : "off")
                      << ", postprocessing=" << (postprocess_active_ ? "on" : "fallback-off")
                      << ", fxaa="
                      << (postprocess_active_ && graphics_features_.fxaa ? "on" : "off")
                      << ", shadows=" << (shadow_active_ ? "on" : "fallback-off")
                      << std::endl;

            const bgfx::Caps* caps = bgfx::getCaps();
            std::ostringstream message;
            message << "RIX renderer: " << bgfx::getRendererName(bgfx::getRendererType())
                    << ", vendor=0x" << std::hex << std::setw(4) << std::setfill('0')
                    << caps->vendorId << ", device=0x" << std::setw(4) << caps->deviceId
                    << std::dec << ", preset=" << graphics_preset_name(graphics_preset_);
            std::cout << message.str() << std::dec << std::endl;
            if (geometry_diagnostic) {
                std::cout << "RIX geometry: GPU meshes=" << mesh_resources_->size()
                          << ", indexed triangles=" << mesh_resources_->triangle_count()
                          << ", GPU textures=" << texture_resources_->size()
                          << ", texture bytes=" << texture_resources_->byte_size()
                          << ", depth-test=less, sRGB=enabled" << std::endl;
            }
        } catch (...) {
            shutdown();
            throw;
        }
    }

    void shutdown() noexcept {
        if (!initialized_) {
            return;
        }
        draw_items_.clear();
        drain_viewport_readbacks();
        destroy_viewport_targets();
        destroy_capture_target();
        destroy_postprocess_target();
        destroy_shadow_target();
        destroy_spot_shadow_target();
        destroy_point_shadow_target();
        ui_font_image_.reset();
        ui_font_texture_.reset();
        fallback_material_images_.clear();
        fallback_white_texture_.reset();
        fallback_normal_texture_.reset();
        if (texture_resources_) {
            texture_resources_->reset();
            texture_resources_.reset();
        }
        if (mesh_resources_) {
            mesh_resources_->reset();
            mesh_resources_.reset();
        }
        if (bgfx::isValid(textured_instanced_program_)) {
            bgfx::destroy(textured_instanced_program_);
            textured_instanced_program_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(postprocess_program_)) {
            bgfx::destroy(postprocess_program_);
            postprocess_program_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(sky_program_)) {
            bgfx::destroy(sky_program_);
            sky_program_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(ui_program_)) {
            bgfx::destroy(ui_program_);
            ui_program_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(shadow_instanced_program_)) {
            bgfx::destroy(shadow_instanced_program_);
            shadow_instanced_program_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(shadow_program_)) {
            bgfx::destroy(shadow_program_);
            shadow_program_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(point_shadow_instanced_program_)) {
            bgfx::destroy(point_shadow_instanced_program_);
            point_shadow_instanced_program_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(point_shadow_program_)) {
            bgfx::destroy(point_shadow_program_);
            point_shadow_program_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(solid_instanced_program_)) {
            bgfx::destroy(solid_instanced_program_);
            solid_instanced_program_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(textured_program_)) {
            bgfx::destroy(textured_program_);
            textured_program_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(solid_program_)) {
            bgfx::destroy(solid_program_);
            solid_program_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(material_color_)) {
            bgfx::destroy(material_color_);
            material_color_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(material_params_)) {
            bgfx::destroy(material_params_);
            material_params_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(normal_matrix_)) {
            bgfx::destroy(normal_matrix_);
            normal_matrix_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(ambient_light_)) {
            bgfx::destroy(ambient_light_);
            ambient_light_ = BGFX_INVALID_HANDLE;
        }
        for (bgfx::UniformHandle* handle : {
                 &directional_lights_, &directional_colors_,
                 &point_positions_ranges_, &point_colors_,
                 &spot_positions_ranges_, &spot_directions_outer_,
                 &spot_colors_inner_, &light_counts_}) {
            if (bgfx::isValid(*handle)) {
                bgfx::destroy(*handle);
                *handle = BGFX_INVALID_HANDLE;
            }
        }
        if (bgfx::isValid(camera_position_)) {
            bgfx::destroy(camera_position_);
            camera_position_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(render_params_)) {
            bgfx::destroy(render_params_);
            render_params_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(texture_sampler_)) {
            bgfx::destroy(texture_sampler_);
            texture_sampler_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(postprocess_sampler_)) {
            bgfx::destroy(postprocess_sampler_);
            postprocess_sampler_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(postprocess_params_)) {
            bgfx::destroy(postprocess_params_);
            postprocess_params_ = BGFX_INVALID_HANDLE;
        }
        for (bgfx::UniformHandle* handle : {
                 &sky_top_, &sky_horizon_, &sky_bottom_, &sky_params_, &sky_camera_,
                 &sky_panorama_sampler_, &sky_cubemap_sampler_}) {
            if (bgfx::isValid(*handle)) {
                bgfx::destroy(*handle);
                *handle = BGFX_INVALID_HANDLE;
            }
        }
        if (bgfx::isValid(shadow_sampler_)) {
            bgfx::destroy(shadow_sampler_);
            shadow_sampler_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(shadow_matrix_uniform_)) {
            bgfx::destroy(shadow_matrix_uniform_);
            shadow_matrix_uniform_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(shadow_params_)) {
            bgfx::destroy(shadow_params_);
            shadow_params_ = BGFX_INVALID_HANDLE;
        }
        for (bgfx::UniformHandle* handle : {
                 &spot_shadow_sampler_, &point_shadow_sampler_,
                 &spot_shadow_matrix_uniform_, &local_shadow_flags_,
                 &local_shadow_params_, &point_shadow_light_uniform_}) {
            if (bgfx::isValid(*handle)) {
                bgfx::destroy(*handle);
                *handle = BGFX_INVALID_HANDLE;
            }
        }
        for (bgfx::UniformHandle* handle : {
                 &uv_scale_, &uv_atlas_, &texture_params_, &map_flags_,
                 &normal_sampler_, &roughness_sampler_, &metallic_sampler_,
                 &emissive_sampler_, &ambient_occlusion_sampler_}) {
            if (bgfx::isValid(*handle)) {
                bgfx::destroy(*handle);
                *handle = BGFX_INVALID_HANDLE;
            }
        }
        if (bgfx::isValid(fallback_shadow_texture_)) {
            bgfx::destroy(fallback_shadow_texture_);
            fallback_shadow_texture_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(sky_cubemap_texture_)) {
            bgfx::destroy(sky_cubemap_texture_);
            sky_cubemap_texture_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(fallback_sky_cubemap_)) {
            bgfx::destroy(fallback_sky_cubemap_);
            fallback_sky_cubemap_ = BGFX_INVALID_HANDLE;
        }
        // Submit one final frame so queued resource releases are observed
        // before the renderer and its D3D11 device are destroyed.
        (void)advance_frame();
        bgfx::shutdown();
        initialized_ = false;
    }

    void resize(const std::uint32_t width, const std::uint32_t height) {
        width_ = std::max(width, 1U);
        height_ = std::max(height, 1U);
        render_width_ = width_;
        render_height_ = height_;
        linear_output_ = postprocess_active_;
        swap_chain_.width = width_;
        swap_chain_.height = height_;
        bgfx::reset(reset_flags_, &swap_chain_);
        destroy_capture_target();
        create_postprocess_target();
        update_view_rect();
    }

    void render_frame(const bool present_to_window) {
        render_width_ = width_;
        render_height_ = height_;
        linear_output_ = postprocess_active_;
        stats_ = {};
        stats_.enhanced_lighting = graphics_features_.enhanced_lighting;
        stats_.shadows = shadow_active_;
        stats_.postprocessing = postprocess_active_;
        stats_.fxaa = postprocess_active_ && graphics_features_.fxaa;
        stats_.shadow_resolution = shadow_active_ ? shadow_resolution_ : 0;
        bgfx::touch(main_view);
        if (!draw_items_.empty() || scene_ != nullptr) {
            submit_geometry();
        }
        if (present_to_window && postprocess_active_) {
            submit_postprocess(postprocess_view, scene_color_, width_, height_);
        }
        if (present_to_window) {
            submit_ui();
        }
        (void)advance_frame();
        finalize_frame_statistics();
    }

    void finalize_frame_statistics() noexcept {
        texture_resources_->collect_expired();
        stats_.texture_count = texture_resources_->size();
        stats_.texture_memory_bytes = texture_resources_->byte_size();
        if (bgfx::isValid(sky_cubemap_texture_)) {
            ++stats_.texture_count;
            stats_.texture_memory_bytes += sky_cubemap_memory_bytes_;
        }
        if (const bgfx::Stats* frame_stats = bgfx::getStats(); frame_stats != nullptr) {
            if (frame_stats->cpuTimerFreq > 0) {
                stats_.cpu_frame_ms =
                    static_cast<double>(frame_stats->cpuTimeEnd - frame_stats->cpuTimeBegin) *
                    1000.0 / static_cast<double>(frame_stats->cpuTimerFreq);
            }
            if (frame_stats->gpuTimerFreq > 0) {
                stats_.gpu_frame_ms =
                    static_cast<double>(frame_stats->gpuTimeEnd - frame_stats->gpuTimeBegin) *
                    1000.0 / static_cast<double>(frame_stats->gpuTimerFreq);
            }
        }
    }

    void present() { render_frame(true); }

    void render_offscreen() { render_frame(false); }

    [[nodiscard]] std::vector<std::uint8_t> readback_rgba8() {
        if (!postprocess_active_ || !bgfx::isValid(scene_color_)) {
            throw EngineError(
                "Surface readback requires the medium, high, or ultra graphics preset");
        }
        create_capture_target();
        bgfx::setViewFrameBuffer(capture_view, capture_framebuffer_);
        bgfx::setViewRect(capture_view, 0, 0, view_extent(width_), view_extent(height_));
        submit_postprocess(capture_view, scene_color_, width_, height_);
        std::uint32_t current_frame = advance_frame();

        bgfx::blit(capture_blit_view,
                   {.handle = capture_readback_},
                   {.handle = capture_color_});
        std::vector<std::uint8_t> pixels(
            static_cast<std::size_t>(width_) * height_ * 4U);
        const std::uint32_t ready_frame =
            bgfx::read({.handle = capture_readback_}, pixels.data());
        while (current_frame < ready_frame) {
            current_frame = advance_frame();
        }
        return pixels;
    }

    [[nodiscard]] std::uint64_t request_viewport_rgba8(
        const Camera& camera,
        const std::uint32_t width,
        const std::uint32_t height) {
        validate_viewport_size(width, height);
        collect_abandoned_readbacks();
        if (pending_viewport_readbacks_.size() >= max_pending_viewport_readbacks) {
            throw EngineError(
                "too many pending viewport readbacks; poll or close existing Viewports");
        }

        ViewportTarget& target = viewport_target(width, height);
        stats_ = {};
        stats_.enhanced_lighting = graphics_features_.enhanced_lighting;
        stats_.shadows = shadow_active_;
        stats_.postprocessing = true;
        stats_.fxaa = graphics_features_.fxaa;
        stats_.shadow_resolution = shadow_active_ ? shadow_resolution_ : 0;

        bgfx::TextureHandle staging = BGFX_INVALID_HANDLE;
        try {
            render_width_ = width;
            render_height_ = height;
            linear_output_ = true;
            bgfx::setViewFrameBuffer(main_view, target.scene_framebuffer);
            bgfx::setViewRect(main_view, 0, 0, view_extent(width), view_extent(height));
            bgfx::touch(main_view);
            submit_geometry(&camera);

            bgfx::setViewFrameBuffer(capture_view, target.output_framebuffer);
            bgfx::setViewRect(capture_view, 0, 0, view_extent(width), view_extent(height));
            submit_postprocess(capture_view, target.scene_color, width, height);
            (void)advance_frame();
            finalize_frame_statistics();

            constexpr std::uint64_t readback_flags =
                BGFX_TEXTURE_BLIT_DST | BGFX_TEXTURE_READ_BACK;
            staging = bgfx::createTexture2D(
                view_extent(width),
                view_extent(height),
                false,
                1,
                bgfx::TextureFormat::RGBA8,
                readback_flags);
            if (!bgfx::isValid(staging)) {
                throw EngineError("bgfx failed to allocate a Viewport readback buffer");
            }

            auto pixels = std::make_shared<std::vector<std::uint8_t>>(
                static_cast<std::size_t>(width) * height * 4U);
            bgfx::blit(capture_blit_view,
                       {.handle = staging},
                       {.handle = target.output_color});
            const std::uint32_t ready_frame =
                bgfx::read({.handle = staging}, pixels->data());
            const std::uint64_t request_id = next_viewport_request_id_++;
            pending_viewport_readbacks_.emplace(
                request_id,
                PendingViewportReadback{
                    width, height, ready_frame, staging, std::move(pixels), false});
            staging = BGFX_INVALID_HANDLE;
            restore_main_target();
            return request_id;
        } catch (...) {
            if (bgfx::isValid(staging)) bgfx::destroy(staging);
            restore_main_target();
            throw;
        }
    }

    [[nodiscard]] std::optional<std::vector<std::uint8_t>> poll_viewport_rgba8(
        const std::uint64_t request_id) {
        const auto found = pending_viewport_readbacks_.find(request_id);
        if (found == pending_viewport_readbacks_.end()) {
            throw EngineError("unknown or already-consumed Viewport readback request");
        }
        if (last_frame_ < found->second.ready_frame) {
            // A Viewport can be the only rendered output in a Pygame Surface-mode
            // application.  Advance one renderer frame while polling so its async
            // readback can make progress even when World.render() is not called.
            // This retains the buffered API (at most one frame is pumped here)
            // while avoiding a request that can otherwise remain pending forever.
            (void)advance_frame();
            if (last_frame_ < found->second.ready_frame) {
                return std::nullopt;
            }
        }
        std::vector<std::uint8_t> pixels = *found->second.pixels;
        destroy_pending_readback(found->second);
        pending_viewport_readbacks_.erase(found);
        return pixels;
    }

    [[nodiscard]] std::vector<std::uint8_t> wait_viewport_rgba8(
        const std::uint64_t request_id) {
        auto found = pending_viewport_readbacks_.find(request_id);
        if (found == pending_viewport_readbacks_.end()) {
            throw EngineError("unknown or already-consumed Viewport readback request");
        }
        while (last_frame_ < found->second.ready_frame) {
            (void)advance_frame();
            found = pending_viewport_readbacks_.find(request_id);
        }
        std::vector<std::uint8_t> pixels = *found->second.pixels;
        destroy_pending_readback(found->second);
        pending_viewport_readbacks_.erase(found);
        return pixels;
    }

    [[nodiscard]] std::vector<std::uint8_t> render_viewport_rgba8(
        const Camera& camera,
        const std::uint32_t width,
        const std::uint32_t height) {
        return wait_viewport_rgba8(request_viewport_rgba8(camera, width, height));
    }

    void cancel_viewport_rgba8(const std::uint64_t request_id) noexcept {
        const auto found = pending_viewport_readbacks_.find(request_id);
        if (found == pending_viewport_readbacks_.end()) return;
        if (last_frame_ >= found->second.ready_frame) {
            destroy_pending_readback(found->second);
            pending_viewport_readbacks_.erase(found);
            return;
        }
        found->second.abandoned = true;
    }

    [[nodiscard]] RendererStats stats() const noexcept { return stats_; }

private:
    static void validate_viewport_size(const std::uint32_t width,
                                       const std::uint32_t height) {
        if (width == 0 || height == 0 ||
            width > std::numeric_limits<std::uint16_t>::max() ||
            height > std::numeric_limits<std::uint16_t>::max()) {
            throw std::invalid_argument(
                "Viewport dimensions must be positive and fit in 16 bits");
        }
        constexpr std::size_t channels = 4;
        if (static_cast<std::size_t>(width) >
            std::numeric_limits<std::size_t>::max() /
                (static_cast<std::size_t>(height) * channels)) {
            throw std::invalid_argument("Viewport pixel buffer size overflows address space");
        }
    }

    [[nodiscard]] static std::uint64_t viewport_target_key(
        const std::uint32_t width,
        const std::uint32_t height) noexcept {
        return (static_cast<std::uint64_t>(width) << 32U) | height;
    }

    void destroy_viewport_target(ViewportTarget& target) noexcept {
        if (bgfx::isValid(target.scene_framebuffer)) {
            bgfx::destroy(target.scene_framebuffer);
        }
        if (bgfx::isValid(target.output_framebuffer)) {
            bgfx::destroy(target.output_framebuffer);
        }
        target = {};
    }

    void destroy_viewport_targets() noexcept {
        for (auto& [key, target] : viewport_targets_) {
            (void)key;
            destroy_viewport_target(target);
        }
        viewport_targets_.clear();
        bgfx::setViewFrameBuffer(capture_view, BGFX_INVALID_HANDLE);
    }

    [[nodiscard]] ViewportTarget& viewport_target(const std::uint32_t width,
                                                  const std::uint32_t height) {
        const std::uint64_t key = viewport_target_key(width, height);
        if (const auto found = viewport_targets_.find(key);
            found != viewport_targets_.end()) {
            return found->second;
        }

        constexpr std::uint64_t render_flags =
            BGFX_TEXTURE_RT | BGFX_SAMPLER_U_CLAMP | BGFX_SAMPLER_V_CLAMP;
        constexpr std::uint64_t depth_flags = BGFX_TEXTURE_RT;
        const std::uint16_t extent_width = view_extent(width);
        const std::uint16_t extent_height = view_extent(height);
        if (!bgfx::isTextureValid(
                0, false, 1, bgfx::TextureFormat::RGBA16F, render_flags) ||
            !bgfx::isTextureValid(
                0, false, 1, bgfx::TextureFormat::D24S8, depth_flags) ||
            !bgfx::isTextureValid(
                0, false, 1, bgfx::TextureFormat::RGBA8, render_flags)) {
            throw EngineError("active renderer does not support Viewport render targets");
        }

        ViewportTarget target;
        target.width = width;
        target.height = height;
        const bgfx::TextureHandle scene_color = bgfx::createTexture2D(
            extent_width, extent_height, false, 1,
            bgfx::TextureFormat::RGBA16F, render_flags);
        const bgfx::TextureHandle scene_depth = bgfx::createTexture2D(
            extent_width, extent_height, false, 1,
            bgfx::TextureFormat::D24S8, depth_flags);
        if (!bgfx::isValid(scene_color) || !bgfx::isValid(scene_depth)) {
            if (bgfx::isValid(scene_color)) bgfx::destroy(scene_color);
            if (bgfx::isValid(scene_depth)) bgfx::destroy(scene_depth);
            throw EngineError("bgfx failed to allocate a Viewport scene target");
        }
        const std::array<bgfx::TextureHandle, 2> scene_attachments{
            scene_color, scene_depth};
        target.scene_framebuffer = bgfx::createFrameBuffer(
            static_cast<std::uint8_t>(scene_attachments.size()),
            scene_attachments.data(),
            true);
        if (!bgfx::isValid(target.scene_framebuffer)) {
            bgfx::destroy(scene_color);
            bgfx::destroy(scene_depth);
            throw EngineError("bgfx failed to create a Viewport scene framebuffer");
        }
        target.scene_color = scene_color;

        const bgfx::TextureHandle output_color = bgfx::createTexture2D(
            extent_width, extent_height, false, 1,
            bgfx::TextureFormat::RGBA8, render_flags);
        if (!bgfx::isValid(output_color)) {
            destroy_viewport_target(target);
            throw EngineError("bgfx failed to allocate a Viewport output target");
        }
        target.output_framebuffer = bgfx::createFrameBuffer(1, &output_color, true);
        if (!bgfx::isValid(target.output_framebuffer)) {
            bgfx::destroy(output_color);
            destroy_viewport_target(target);
            throw EngineError("bgfx failed to create a Viewport output framebuffer");
        }
        target.output_color = output_color;
        return viewport_targets_.emplace(key, target).first->second;
    }

    void restore_main_target() noexcept {
        render_width_ = width_;
        render_height_ = height_;
        linear_output_ = postprocess_active_;
        bgfx::FrameBufferHandle target = scene_framebuffer_;
        if (!postprocess_active_) target = BGFX_INVALID_HANDLE;
        bgfx::setViewFrameBuffer(main_view, target);
        bgfx::setViewRect(main_view, 0, 0, view_extent(width_), view_extent(height_));
    }

    void destroy_pending_readback(PendingViewportReadback& pending) noexcept {
        if (bgfx::isValid(pending.staging)) {
            bgfx::destroy(pending.staging);
        }
        pending.staging = BGFX_INVALID_HANDLE;
        pending.pixels.reset();
    }

    void collect_abandoned_readbacks() noexcept {
        for (auto iterator = pending_viewport_readbacks_.begin();
             iterator != pending_viewport_readbacks_.end();) {
            if (iterator->second.abandoned && last_frame_ >= iterator->second.ready_frame) {
                destroy_pending_readback(iterator->second);
                iterator = pending_viewport_readbacks_.erase(iterator);
            } else {
                ++iterator;
            }
        }
    }

    [[nodiscard]] std::uint32_t advance_frame() noexcept {
        last_frame_ = bgfx::frame();
        collect_abandoned_readbacks();
        return last_frame_;
    }

    void drain_viewport_readbacks() noexcept {
        std::uint32_t maximum_ready_frame = last_frame_;
        for (const auto& [request, pending] : pending_viewport_readbacks_) {
            (void)request;
            maximum_ready_frame = std::max(maximum_ready_frame, pending.ready_frame);
        }
        while (last_frame_ < maximum_ready_frame) {
            last_frame_ = bgfx::frame();
        }
        for (auto& [request, pending] : pending_viewport_readbacks_) {
            (void)request;
            destroy_pending_readback(pending);
        }
        pending_viewport_readbacks_.clear();
    }

    [[nodiscard]] static bgfx::ProgramHandle make_program(const std::uint8_t* vertex_bytes,
                                                          const std::uint32_t vertex_size,
                                                          const std::uint8_t* fragment_bytes,
                                                          const std::uint32_t fragment_size,
                                                          const char* label) {
        const bgfx::ShaderHandle vertex_shader = bgfx::createShader(
            bgfx::makeRef(vertex_bytes, vertex_size));
        const bgfx::ShaderHandle fragment_shader = bgfx::createShader(
            bgfx::makeRef(fragment_bytes, fragment_size));
        if (!bgfx::isValid(vertex_shader) || !bgfx::isValid(fragment_shader)) {
            if (bgfx::isValid(vertex_shader)) {
                bgfx::destroy(vertex_shader);
            }
            if (bgfx::isValid(fragment_shader)) {
                bgfx::destroy(fragment_shader);
            }
            throw EngineError(std::string("bgfx failed to create RIX ") + label + " shaders");
        }
        const bgfx::ProgramHandle program = bgfx::createProgram(vertex_shader, fragment_shader, true);
        if (!bgfx::isValid(program)) {
            throw EngineError(std::string("bgfx failed to link the RIX ") + label +
                              " shader program");
        }
        return program;
    }

    void create_programs() {
        solid_program_ = make_program(vs_solid_color_dxbc,
                                      static_cast<std::uint32_t>(sizeof(vs_solid_color_dxbc)),
                                      fs_solid_color_dxbc,
                                      static_cast<std::uint32_t>(sizeof(fs_solid_color_dxbc)),
                                      "solid-color");
        textured_program_ = make_program(vs_textured_dxbc,
                                         static_cast<std::uint32_t>(sizeof(vs_textured_dxbc)),
                                         fs_textured_dxbc,
                                         static_cast<std::uint32_t>(sizeof(fs_textured_dxbc)),
                                         "textured");
        solid_instanced_program_ = make_program(
            vs_solid_color_instanced_dxbc,
            static_cast<std::uint32_t>(sizeof(vs_solid_color_instanced_dxbc)),
            fs_solid_color_dxbc,
            static_cast<std::uint32_t>(sizeof(fs_solid_color_dxbc)),
            "instanced solid-color");
        textured_instanced_program_ = make_program(
            vs_textured_instanced_dxbc,
            static_cast<std::uint32_t>(sizeof(vs_textured_instanced_dxbc)),
            fs_textured_dxbc,
            static_cast<std::uint32_t>(sizeof(fs_textured_dxbc)),
            "instanced textured");
        postprocess_program_ = make_program(
            vs_postprocess_dxbc,
            static_cast<std::uint32_t>(sizeof(vs_postprocess_dxbc)),
            fs_postprocess_dxbc,
            static_cast<std::uint32_t>(sizeof(fs_postprocess_dxbc)),
            "postprocess");
        sky_program_ = make_program(
            vs_postprocess_dxbc,
            static_cast<std::uint32_t>(sizeof(vs_postprocess_dxbc)),
            fs_sky_dxbc,
            static_cast<std::uint32_t>(sizeof(fs_sky_dxbc)),
            "sky");
        shadow_program_ = make_program(
            vs_shadow_dxbc,
            static_cast<std::uint32_t>(sizeof(vs_shadow_dxbc)),
            fs_shadow_dxbc,
            static_cast<std::uint32_t>(sizeof(fs_shadow_dxbc)),
            "shadow");
        shadow_instanced_program_ = make_program(
            vs_shadow_instanced_dxbc,
            static_cast<std::uint32_t>(sizeof(vs_shadow_instanced_dxbc)),
            fs_shadow_dxbc,
            static_cast<std::uint32_t>(sizeof(fs_shadow_dxbc)),
            "instanced shadow");
        point_shadow_program_ = make_program(
            vs_point_shadow_dxbc,
            static_cast<std::uint32_t>(sizeof(vs_point_shadow_dxbc)),
            fs_point_shadow_dxbc,
            static_cast<std::uint32_t>(sizeof(fs_point_shadow_dxbc)),
            "point shadow");
        point_shadow_instanced_program_ = make_program(
            vs_point_shadow_instanced_dxbc,
            static_cast<std::uint32_t>(sizeof(vs_point_shadow_instanced_dxbc)),
            fs_point_shadow_dxbc,
            static_cast<std::uint32_t>(sizeof(fs_point_shadow_dxbc)),
            "instanced point shadow");
        ui_program_ = make_program(vs_ui_dxbc,
                                   static_cast<std::uint32_t>(sizeof(vs_ui_dxbc)),
                                   fs_ui_dxbc,
                                   static_cast<std::uint32_t>(sizeof(fs_ui_dxbc)),
                                   "UI");
        material_color_ = bgfx::createUniform("u_materialColor", bgfx::UniformType::Vec4);
        material_params_ = bgfx::createUniform("u_materialParams", bgfx::UniformType::Vec4);
        normal_matrix_ = bgfx::createUniform("u_normalMatrix", bgfx::UniformType::Vec4, 3);
        ambient_light_ = bgfx::createUniform("u_ambientLight", bgfx::UniformType::Vec4);
        directional_lights_ = bgfx::createUniform(
            "u_directionalLights", bgfx::UniformType::Vec4,
            static_cast<std::uint16_t>(max_directional_lights));
        directional_colors_ = bgfx::createUniform(
            "u_directionalColors", bgfx::UniformType::Vec4,
            static_cast<std::uint16_t>(max_directional_lights));
        point_positions_ranges_ = bgfx::createUniform(
            "u_pointPositionsRanges", bgfx::UniformType::Vec4,
            static_cast<std::uint16_t>(max_point_lights));
        point_colors_ = bgfx::createUniform(
            "u_pointColors", bgfx::UniformType::Vec4,
            static_cast<std::uint16_t>(max_point_lights));
        spot_positions_ranges_ = bgfx::createUniform(
            "u_spotPositionsRanges", bgfx::UniformType::Vec4,
            static_cast<std::uint16_t>(max_spot_lights));
        spot_directions_outer_ = bgfx::createUniform(
            "u_spotDirectionsOuter", bgfx::UniformType::Vec4,
            static_cast<std::uint16_t>(max_spot_lights));
        spot_colors_inner_ = bgfx::createUniform(
            "u_spotColorsInner", bgfx::UniformType::Vec4,
            static_cast<std::uint16_t>(max_spot_lights));
        light_counts_ = bgfx::createUniform("u_lightCounts", bgfx::UniformType::Vec4);
        camera_position_ =
            bgfx::createUniform("u_cameraPosition", bgfx::UniformType::Vec4);
        render_params_ = bgfx::createUniform("u_renderParams", bgfx::UniformType::Vec4);
        texture_sampler_ = bgfx::createUniform("s_texColor", bgfx::UniformType::Sampler);
        postprocess_sampler_ =
            bgfx::createUniform("s_sceneColor", bgfx::UniformType::Sampler);
        postprocess_params_ =
            bgfx::createUniform("u_postParams", bgfx::UniformType::Vec4);
        sky_top_ = bgfx::createUniform("u_skyTop", bgfx::UniformType::Vec4);
        sky_horizon_ = bgfx::createUniform("u_skyHorizon", bgfx::UniformType::Vec4);
        sky_bottom_ = bgfx::createUniform("u_skyBottom", bgfx::UniformType::Vec4);
        sky_params_ = bgfx::createUniform("u_skyParams", bgfx::UniformType::Vec4);
        sky_camera_ = bgfx::createUniform("u_skyCamera", bgfx::UniformType::Vec4, 3);
        sky_panorama_sampler_ =
            bgfx::createUniform("s_skyPanorama", bgfx::UniformType::Sampler);
        sky_cubemap_sampler_ =
            bgfx::createUniform("s_skyCubemap", bgfx::UniformType::Sampler);
        shadow_sampler_ = bgfx::createUniform("s_shadowMap", bgfx::UniformType::Sampler);
        shadow_matrix_uniform_ =
            bgfx::createUniform("u_shadowMatrix", bgfx::UniformType::Mat4);
        shadow_params_ = bgfx::createUniform("u_shadowParams", bgfx::UniformType::Vec4);
        spot_shadow_sampler_ =
            bgfx::createUniform("s_spotShadowMap", bgfx::UniformType::Sampler);
        point_shadow_sampler_ =
            bgfx::createUniform("s_pointShadowMap", bgfx::UniformType::Sampler);
        spot_shadow_matrix_uniform_ =
            bgfx::createUniform("u_spotShadowMatrix", bgfx::UniformType::Mat4);
        local_shadow_flags_ =
            bgfx::createUniform("u_localShadowFlags", bgfx::UniformType::Vec4);
        local_shadow_params_ =
            bgfx::createUniform("u_localShadowParams", bgfx::UniformType::Vec4);
        point_shadow_light_uniform_ =
            bgfx::createUniform("u_pointShadowLight", bgfx::UniformType::Vec4);
        uv_scale_ = bgfx::createUniform("u_uvScale", bgfx::UniformType::Vec4, 3);
        uv_atlas_ = bgfx::createUniform("u_uvAtlas", bgfx::UniformType::Vec4, 6);
        texture_params_ = bgfx::createUniform("u_textureParams", bgfx::UniformType::Vec4);
        map_flags_ = bgfx::createUniform("u_mapFlags", bgfx::UniformType::Vec4);
        normal_sampler_ = bgfx::createUniform("s_normalMap", bgfx::UniformType::Sampler);
        roughness_sampler_ =
            bgfx::createUniform("s_roughnessMap", bgfx::UniformType::Sampler);
        metallic_sampler_ =
            bgfx::createUniform("s_metallicMap", bgfx::UniformType::Sampler);
        emissive_sampler_ =
            bgfx::createUniform("s_emissiveMap", bgfx::UniformType::Sampler);
        ambient_occlusion_sampler_ =
            bgfx::createUniform("s_aoMap", bgfx::UniformType::Sampler);
        if (!bgfx::isValid(material_color_) || !bgfx::isValid(material_params_) ||
            !bgfx::isValid(normal_matrix_) || !bgfx::isValid(ambient_light_) ||
            !bgfx::isValid(directional_lights_) || !bgfx::isValid(directional_colors_) ||
            !bgfx::isValid(point_positions_ranges_) || !bgfx::isValid(point_colors_) ||
            !bgfx::isValid(spot_positions_ranges_) ||
            !bgfx::isValid(spot_directions_outer_) ||
            !bgfx::isValid(spot_colors_inner_) || !bgfx::isValid(light_counts_) ||
            !bgfx::isValid(camera_position_) || !bgfx::isValid(render_params_) ||
            !bgfx::isValid(texture_sampler_) || !bgfx::isValid(postprocess_sampler_) ||
            !bgfx::isValid(postprocess_params_) || !bgfx::isValid(shadow_sampler_) ||
            !bgfx::isValid(sky_program_) || !bgfx::isValid(sky_top_) ||
            !bgfx::isValid(sky_horizon_) || !bgfx::isValid(sky_bottom_) ||
            !bgfx::isValid(sky_params_) || !bgfx::isValid(sky_camera_) ||
            !bgfx::isValid(sky_panorama_sampler_) ||
            !bgfx::isValid(sky_cubemap_sampler_) ||
            !bgfx::isValid(shadow_matrix_uniform_) || !bgfx::isValid(shadow_params_) ||
            !bgfx::isValid(point_shadow_program_) ||
            !bgfx::isValid(point_shadow_instanced_program_) ||
            !bgfx::isValid(spot_shadow_sampler_) ||
            !bgfx::isValid(point_shadow_sampler_) ||
            !bgfx::isValid(spot_shadow_matrix_uniform_) ||
            !bgfx::isValid(local_shadow_flags_) ||
            !bgfx::isValid(local_shadow_params_) ||
            !bgfx::isValid(point_shadow_light_uniform_) ||
            !bgfx::isValid(uv_scale_) || !bgfx::isValid(uv_atlas_) ||
            !bgfx::isValid(texture_params_) || !bgfx::isValid(map_flags_) ||
            !bgfx::isValid(normal_sampler_) || !bgfx::isValid(roughness_sampler_) ||
            !bgfx::isValid(metallic_sampler_) || !bgfx::isValid(emissive_sampler_) ||
            !bgfx::isValid(ambient_occlusion_sampler_)) {
            throw EngineError("bgfx failed to create RIX material uniforms");
        }
    }

    void create_material_fallbacks() {
        const auto make_pixel = [](const std::string& name,
                                   const std::array<std::uint8_t, 4> rgba) {
            auto image = std::make_shared<ImageData>();
            image->source_path = name;
            image->width = 1;
            image->height = 1;
            image->color_space = TextureColorSpace::Linear;
            image->rgba8.assign(rgba.begin(), rgba.end());
            image->validate();
            return image;
        };
        const auto white = make_pixel("<RIX material white>", {255, 255, 255, 255});
        const auto normal = make_pixel("<RIX neutral normal>", {128, 128, 255, 255});
        fallback_white_texture_ = texture_resources_->upload(*white);
        fallback_normal_texture_ = texture_resources_->upload(*normal);
        fallback_material_images_ = {white, normal};
        constexpr std::array<std::uint8_t, 24> cube_pixels{
            255,255,255,255, 255,255,255,255, 255,255,255,255,
            255,255,255,255, 255,255,255,255, 255,255,255,255};
        fallback_sky_cubemap_ = bgfx::createTextureCube(
            1, false, 1, bgfx::TextureFormat::RGBA8,
            BGFX_SAMPLER_UVW_CLAMP,
            bgfx::copy(cube_pixels.data(), static_cast<std::uint32_t>(cube_pixels.size())));
        if (!bgfx::isValid(fallback_sky_cubemap_)) {
            throw EngineError("bgfx failed to create the sky cubemap fallback");
        }
    }

    void create_font_atlas() {
        constexpr int atlas_width = 512;
        constexpr int atlas_height = 512;
        constexpr float baked_size = 48.0F;
        std::vector<std::uint8_t> alpha(
            static_cast<std::size_t>(atlas_width * atlas_height));
        if (stbtt_BakeFontBitmap(s_robotoRegularTtf,
                                 0,
                                 baked_size,
                                 alpha.data(),
                                 atlas_width,
                                 atlas_height,
                                 32,
                                 static_cast<int>(font_glyphs_.size()),
                                 font_glyphs_.data()) <= 0) {
            throw EngineError("RIX could not bake the built-in UI font atlas");
        }
        auto image = std::make_shared<ImageData>();
        image->source_path = "<RIX built-in Roboto Regular>";
        image->width = atlas_width;
        image->height = atlas_height;
        image->color_space = TextureColorSpace::Linear;
        image->rgba8.resize(static_cast<std::size_t>(atlas_width * atlas_height * 4));
        for (std::size_t index = 0; index < alpha.size(); ++index) {
            image->rgba8[index * 4] = 255;
            image->rgba8[index * 4 + 1] = 255;
            image->rgba8[index * 4 + 2] = 255;
            image->rgba8[index * 4 + 3] = alpha[index];
        }
        ui_font_image_ = std::move(image);
        ui_font_texture_ = texture_resources_->upload(*ui_font_image_, ui_sampler_);
    }

    struct UiRect final {
        float x;
        float y;
        float width;
        float height;
    };

    [[nodiscard]] UiRect resolve_ui_rect(const UiElement& element) const noexcept {
        float factor_x = 0.0F;
        float factor_y = 0.0F;
        switch (element.anchor) {
        case UiAnchor::Top: factor_x = 0.5F; break;
        case UiAnchor::TopRight: factor_x = 1.0F; break;
        case UiAnchor::Left: factor_y = 0.5F; break;
        case UiAnchor::Center: factor_x = 0.5F; factor_y = 0.5F; break;
        case UiAnchor::Right: factor_x = 1.0F; factor_y = 0.5F; break;
        case UiAnchor::BottomLeft: factor_y = 1.0F; break;
        case UiAnchor::Bottom: factor_x = 0.5F; factor_y = 1.0F; break;
        case UiAnchor::BottomRight: factor_x = 1.0F; factor_y = 1.0F; break;
        case UiAnchor::TopLeft: break;
        }
        return {
            static_cast<float>(width_) * factor_x + element.x - element.width * factor_x,
            static_cast<float>(height_) * factor_y + element.y - element.height * factor_y,
            element.width,
            element.height,
        };
    }

    [[nodiscard]] float ui_ndc_x(const float value) const noexcept {
        return value * 2.0F / static_cast<float>(width_) - 1.0F;
    }

    [[nodiscard]] float ui_ndc_y(const float value) const noexcept {
        return 1.0F - value * 2.0F / static_cast<float>(height_);
    }

    void append_ui_quad(std::vector<UiVertex>& vertices,
                        const float left,
                        const float top,
                        const float right,
                        const float bottom,
                        const float u0,
                        const float v0,
                        const float u1,
                        const float v1,
                        const Color color) const {
        const float x0 = ui_ndc_x(left);
        const float x1 = ui_ndc_x(right);
        const float y0 = ui_ndc_y(top);
        const float y1 = ui_ndc_y(bottom);
        const std::uint32_t packed = color.rgba8();
        vertices.insert(vertices.end(), {
            {{x0, y0, 0.0F}, {u0, v0}, packed},
            {{x1, y0, 0.0F}, {u1, v0}, packed},
            {{x1, y1, 0.0F}, {u1, v1}, packed},
            {{x0, y0, 0.0F}, {u0, v0}, packed},
            {{x1, y1, 0.0F}, {u1, v1}, packed},
            {{x0, y1, 0.0F}, {u0, v1}, packed},
        });
    }

    void submit_ui_vertices(
        const std::vector<UiVertex>& vertices,
        const std::optional<TextureLifetimeManager::Handle> texture) {
        if (vertices.empty() ||
            bgfx::getAvailTransientVertexBuffer(
                static_cast<std::uint32_t>(vertices.size()), ui_layout_) < vertices.size()) {
            return;
        }
        bgfx::TransientVertexBuffer buffer;
        bgfx::allocTransientVertexBuffer(
            &buffer, static_cast<std::uint32_t>(vertices.size()), ui_layout_);
        std::memcpy(buffer.data, vertices.data(), vertices.size() * sizeof(UiVertex));
        bgfx::setVertexBuffer(0, &buffer);
        if (texture.has_value()) {
            texture_resources_->bind(*texture, texture_sampler_);
        } else {
            bgfx::setTexture(0, texture_sampler_, fallback_shadow_texture_);
        }
        bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_A |
                       BGFX_STATE_BLEND_ALPHA);
        bgfx::submit(ui_view, ui_program_);
        ++stats_.draw_calls;
        ++stats_.ui_draw_calls;
    }

    [[nodiscard]] float text_width(const std::string& text,
                                   const float font_size) const noexcept {
        constexpr float baked_size = 48.0F;
        const float scale = font_size / baked_size;
        float line = 0.0F;
        float maximum = 0.0F;
        for (std::size_t index = 0; index < text.size(); ++index) {
            const unsigned char value = static_cast<unsigned char>(text[index]);
            if (value == '\n') {
                maximum = std::max(maximum, line);
                line = 0.0F;
                continue;
            }
            unsigned char glyph = value;
            if (glyph < 32 || glyph > 126) {
                glyph = '?';
                while (index + 1 < text.size() &&
                       (static_cast<unsigned char>(text[index + 1]) & 0xc0U) == 0x80U) {
                    ++index;
                }
            }
            line += font_glyphs_[glyph - 32].xadvance * scale;
        }
        return std::max(maximum, line);
    }

    void append_ui_text(std::vector<UiVertex>& vertices,
                        const UiElement& element,
                        const UiRect& rect) const {
        constexpr float baked_size = 48.0F;
        constexpr float atlas_size = 512.0F;
        const float scale = element.font_size / baked_size;
        float origin_x = rect.x;
        float baseline = rect.y + element.font_size;
        if (element.kind == UiElementKind::Button) {
            origin_x = rect.x + (rect.width - text_width(element.text, element.font_size)) * 0.5F;
            baseline = rect.y + (rect.height + element.font_size * 0.72F) * 0.5F;
        }
        float cursor_x = origin_x / scale;
        float cursor_y = baseline / scale;
        for (std::size_t index = 0; index < element.text.size(); ++index) {
            unsigned char value = static_cast<unsigned char>(element.text[index]);
            if (value == '\n') {
                cursor_x = origin_x / scale;
                cursor_y += baked_size * 1.25F;
                continue;
            }
            if (value < 32 || value > 126) {
                value = '?';
                while (index + 1 < element.text.size() &&
                       (static_cast<unsigned char>(element.text[index + 1]) & 0xc0U) == 0x80U) {
                    ++index;
                }
            }
            stbtt_aligned_quad quad{};
            stbtt_GetBakedQuad(font_glyphs_.data(),
                               static_cast<int>(atlas_size),
                               static_cast<int>(atlas_size),
                               value - 32,
                               &cursor_x,
                               &cursor_y,
                               &quad,
                               1);
            append_ui_quad(vertices,
                           quad.x0 * scale,
                           quad.y0 * scale,
                           quad.x1 * scale,
                           quad.y1 * scale,
                           quad.s0,
                           quad.t0,
                           quad.s1,
                           quad.t1,
                           element.text_color);
        }
    }

    void submit_ui() {
        if (scene_ == nullptr || !scene_->active() || scene_->ui_elements().empty()) {
            return;
        }
        std::vector<const UiElement*> elements;
        elements.reserve(scene_->ui_elements().size());
        for (const UiElement& element : scene_->ui_elements()) {
            if (element.visible) {
                elements.push_back(&element);
            }
        }
        std::stable_sort(elements.begin(), elements.end(),
                         [](const UiElement* left, const UiElement* right) {
                             if (left->z_index != right->z_index) {
                                 return left->z_index < right->z_index;
                             }
                             return left->id < right->id;
                         });
        bgfx::touch(ui_view);
        for (const UiElement* element : elements) {
            const UiRect rect = resolve_ui_rect(*element);
            if (element->kind == UiElementKind::Panel ||
                element->kind == UiElementKind::Sprite ||
                element->kind == UiElementKind::Button) {
                std::vector<UiVertex> vertices;
                vertices.reserve(6);
                append_ui_quad(vertices,
                               rect.x,
                               rect.y,
                               rect.x + rect.width,
                               rect.y + rect.height,
                               0.0F,
                               0.0F,
                               1.0F,
                               1.0F,
                               element->color);
                std::optional<TextureLifetimeManager::Handle> texture;
                if (element->texture) {
                    texture = texture_resources_->upload_cached(
                        element->texture, ui_sampler_);
                }
                submit_ui_vertices(vertices, texture);
            }
            if (element->kind == UiElementKind::Text ||
                element->kind == UiElementKind::Button) {
                std::vector<UiVertex> vertices;
                vertices.reserve(element->text.size() * 6);
                append_ui_text(vertices, *element, rect);
                submit_ui_vertices(vertices, ui_font_texture_);
            }
            ++stats_.ui_elements;
        }
    }

    void destroy_postprocess_target() noexcept {
        if (bgfx::isValid(scene_framebuffer_)) {
            bgfx::destroy(scene_framebuffer_);
        }
        scene_framebuffer_ = BGFX_INVALID_HANDLE;
        scene_color_ = BGFX_INVALID_HANDLE;
        postprocess_active_ = false;
        bgfx::setViewFrameBuffer(main_view, BGFX_INVALID_HANDLE);
    }

    void destroy_capture_target() noexcept {
        if (bgfx::isValid(capture_framebuffer_)) {
            bgfx::destroy(capture_framebuffer_);
        }
        if (bgfx::isValid(capture_readback_)) {
            bgfx::destroy(capture_readback_);
        }
        capture_framebuffer_ = BGFX_INVALID_HANDLE;
        capture_color_ = BGFX_INVALID_HANDLE;
        capture_readback_ = BGFX_INVALID_HANDLE;
    }

    void create_capture_target() {
        if (bgfx::isValid(capture_framebuffer_) &&
            bgfx::isValid(capture_readback_)) {
            return;
        }
        destroy_capture_target();
        constexpr std::uint64_t render_flags =
            BGFX_TEXTURE_RT | BGFX_SAMPLER_U_CLAMP | BGFX_SAMPLER_V_CLAMP;
        constexpr std::uint64_t readback_flags =
            BGFX_TEXTURE_BLIT_DST | BGFX_TEXTURE_READ_BACK;
        const std::uint16_t width = view_extent(width_);
        const std::uint16_t height = view_extent(height_);
        capture_color_ = bgfx::createTexture2D(
            width, height, false, 1, bgfx::TextureFormat::RGBA8, render_flags);
        capture_readback_ = bgfx::createTexture2D(
            width, height, false, 1, bgfx::TextureFormat::RGBA8, readback_flags);
        if (!bgfx::isValid(capture_color_) || !bgfx::isValid(capture_readback_)) {
            destroy_capture_target();
            throw EngineError("active renderer does not support RGBA8 Surface readback");
        }
        const bgfx::TextureHandle attachment = capture_color_;
        capture_framebuffer_ = bgfx::createFrameBuffer(1, &attachment, false);
        if (!bgfx::isValid(capture_framebuffer_)) {
            destroy_capture_target();
            throw EngineError("bgfx failed to allocate the Surface readback target");
        }
    }

    void create_postprocess_target() {
        destroy_postprocess_target();
        if (!graphics_features_.postprocessing) {
            return;
        }
        constexpr std::uint64_t color_flags =
            BGFX_TEXTURE_RT | BGFX_SAMPLER_U_CLAMP | BGFX_SAMPLER_V_CLAMP;
        constexpr std::uint64_t depth_flags = BGFX_TEXTURE_RT;
        if (!bgfx::isTextureValid(0, false, 1, bgfx::TextureFormat::RGBA16F, color_flags) ||
            !bgfx::isTextureValid(0, false, 1, bgfx::TextureFormat::D24S8, depth_flags)) {
            return;
        }
        const bgfx::TextureHandle color = bgfx::createTexture2D(
            view_extent(width_),
            view_extent(height_),
            false,
            1,
            bgfx::TextureFormat::RGBA16F,
            color_flags);
        const bgfx::TextureHandle depth = bgfx::createTexture2D(
            view_extent(width_),
            view_extent(height_),
            false,
            1,
            bgfx::TextureFormat::D24S8,
            depth_flags);
        if (!bgfx::isValid(color) || !bgfx::isValid(depth)) {
            if (bgfx::isValid(color)) {
                bgfx::destroy(color);
            }
            if (bgfx::isValid(depth)) {
                bgfx::destroy(depth);
            }
            return;
        }
        const std::array<bgfx::TextureHandle, 2> attachments{color, depth};
        const bgfx::FrameBufferHandle framebuffer =
            bgfx::createFrameBuffer(static_cast<std::uint8_t>(attachments.size()),
                                    attachments.data(),
                                    true);
        if (!bgfx::isValid(framebuffer)) {
            bgfx::destroy(color);
            bgfx::destroy(depth);
            return;
        }
        scene_color_ = color;
        scene_framebuffer_ = framebuffer;
        postprocess_active_ = true;
        bgfx::setViewFrameBuffer(main_view, scene_framebuffer_);
    }

    void destroy_shadow_target() noexcept {
        if (bgfx::isValid(shadow_framebuffer_)) {
            bgfx::destroy(shadow_framebuffer_);
        }
        shadow_framebuffer_ = BGFX_INVALID_HANDLE;
        shadow_texture_ = BGFX_INVALID_HANDLE;
        shadow_resolution_ = 0;
        shadow_active_ = false;
        bgfx::setViewFrameBuffer(shadow_view, BGFX_INVALID_HANDLE);
    }

    void create_shadow_target(const std::uint16_t requested_resolution = 0) {
        destroy_shadow_target();
        if (!bgfx::isValid(fallback_shadow_texture_)) {
            const std::array<std::uint8_t, 4> white{255, 255, 255, 255};
            fallback_shadow_texture_ = bgfx::createTexture2D(
                1, 1, false, 1, bgfx::TextureFormat::RGBA8,
                BGFX_SAMPLER_U_CLAMP | BGFX_SAMPLER_V_CLAMP,
                bgfx::copy(white.data(), static_cast<std::uint32_t>(white.size())));
        }
        if (!bgfx::isValid(fallback_shadow_texture_)) {
            throw EngineError("bgfx failed to create the shadow fallback texture");
        }
        if (!graphics_features_.shadows) {
            return;
        }
        const bgfx::Caps* caps = bgfx::getCaps();
        const std::uint16_t resolution = static_cast<std::uint16_t>(std::min(
            static_cast<std::uint32_t>(requested_resolution != 0
                ? requested_resolution : graphics_features_.shadow_resolution),
            caps->limits.maxTextureSize));
        constexpr std::uint64_t color_flags =
            BGFX_TEXTURE_RT | BGFX_SAMPLER_U_CLAMP | BGFX_SAMPLER_V_CLAMP |
            BGFX_SAMPLER_MIN_POINT | BGFX_SAMPLER_MAG_POINT;
        constexpr std::uint64_t depth_flags = BGFX_TEXTURE_RT;
        if (resolution == 0 ||
            !bgfx::isTextureValid(0, false, 1, bgfx::TextureFormat::R32F, color_flags) ||
            !bgfx::isTextureValid(0, false, 1, bgfx::TextureFormat::D24S8, depth_flags)) {
            return;
        }
        const bgfx::TextureHandle color = bgfx::createTexture2D(
            resolution, resolution, false, 1, bgfx::TextureFormat::R32F, color_flags);
        const bgfx::TextureHandle depth = bgfx::createTexture2D(
            resolution, resolution, false, 1, bgfx::TextureFormat::D24S8, depth_flags);
        if (!bgfx::isValid(color) || !bgfx::isValid(depth)) {
            if (bgfx::isValid(color)) {
                bgfx::destroy(color);
            }
            if (bgfx::isValid(depth)) {
                bgfx::destroy(depth);
            }
            return;
        }
        const std::array<bgfx::TextureHandle, 2> attachments{color, depth};
        const bgfx::FrameBufferHandle framebuffer =
            bgfx::createFrameBuffer(static_cast<std::uint8_t>(attachments.size()),
                                    attachments.data(),
                                    true);
        if (!bgfx::isValid(framebuffer)) {
            bgfx::destroy(color);
            bgfx::destroy(depth);
            return;
        }
        shadow_resolution_ = resolution;
        shadow_texture_ = color;
        shadow_framebuffer_ = framebuffer;
        shadow_active_ = true;
        bgfx::setViewFrameBuffer(shadow_view, shadow_framebuffer_);
        bgfx::setViewRect(shadow_view, 0, 0, resolution, resolution);
        bgfx::setViewClear(
            shadow_view, BGFX_CLEAR_COLOR | BGFX_CLEAR_DEPTH, 0xffffffff, 1.0F, 0);
    }

    void destroy_spot_shadow_target() noexcept {
        if (bgfx::isValid(spot_shadow_framebuffer_)) bgfx::destroy(spot_shadow_framebuffer_);
        spot_shadow_framebuffer_ = BGFX_INVALID_HANDLE;
        spot_shadow_texture_ = BGFX_INVALID_HANDLE;
        spot_shadow_resolution_ = 0;
        bgfx::setViewFrameBuffer(spot_shadow_view, BGFX_INVALID_HANDLE);
    }

    void create_spot_shadow_target(const std::uint16_t resolution) {
        if (resolution == spot_shadow_resolution_ &&
            bgfx::isValid(spot_shadow_framebuffer_)) return;
        destroy_spot_shadow_target();
        constexpr std::uint64_t color_flags =
            BGFX_TEXTURE_RT | BGFX_SAMPLER_U_CLAMP | BGFX_SAMPLER_V_CLAMP |
            BGFX_SAMPLER_MIN_POINT | BGFX_SAMPLER_MAG_POINT;
        const auto color = bgfx::createTexture2D(
            resolution, resolution, false, 1, bgfx::TextureFormat::R32F, color_flags);
        const auto depth = bgfx::createTexture2D(
            resolution, resolution, false, 1, bgfx::TextureFormat::D24S8,
            BGFX_TEXTURE_RT);
        if (!bgfx::isValid(color) || !bgfx::isValid(depth)) {
            if (bgfx::isValid(color)) bgfx::destroy(color);
            if (bgfx::isValid(depth)) bgfx::destroy(depth);
            return;
        }
        const std::array<bgfx::TextureHandle, 2> attachments{color, depth};
        spot_shadow_framebuffer_ = bgfx::createFrameBuffer(
            static_cast<std::uint8_t>(attachments.size()), attachments.data(), true);
        if (!bgfx::isValid(spot_shadow_framebuffer_)) {
            bgfx::destroy(color);
            bgfx::destroy(depth);
            return;
        }
        spot_shadow_texture_ = color;
        spot_shadow_resolution_ = resolution;
        bgfx::setViewFrameBuffer(spot_shadow_view, spot_shadow_framebuffer_);
        bgfx::setViewRect(spot_shadow_view, 0, 0, resolution, resolution);
        bgfx::setViewClear(spot_shadow_view,
                           BGFX_CLEAR_COLOR | BGFX_CLEAR_DEPTH,
                           0xffffffff, 1.0F, 0);
    }

    void destroy_point_shadow_target() noexcept {
        for (std::size_t face = 0; face < point_shadow_framebuffers_.size(); ++face) {
            if (bgfx::isValid(point_shadow_framebuffers_[face]))
                bgfx::destroy(point_shadow_framebuffers_[face]);
            point_shadow_framebuffers_[face] = BGFX_INVALID_HANDLE;
            bgfx::setViewFrameBuffer(
                static_cast<bgfx::ViewId>(point_shadow_first_view + face),
                BGFX_INVALID_HANDLE);
        }
        if (bgfx::isValid(point_shadow_texture_)) bgfx::destroy(point_shadow_texture_);
        point_shadow_texture_ = BGFX_INVALID_HANDLE;
        point_shadow_resolution_ = 0;
    }

    void create_point_shadow_target(const std::uint16_t resolution) {
        if (resolution == point_shadow_resolution_ &&
            bgfx::isValid(point_shadow_texture_)) return;
        destroy_point_shadow_target();
        constexpr std::uint64_t color_flags =
            BGFX_TEXTURE_RT | BGFX_SAMPLER_UVW_CLAMP |
            BGFX_SAMPLER_MIN_POINT | BGFX_SAMPLER_MAG_POINT;
        point_shadow_texture_ = bgfx::createTextureCube(
            resolution, false, 1, bgfx::TextureFormat::R32F, color_flags);
        if (!bgfx::isValid(point_shadow_texture_)) {
            std::cerr << "RIX warning: point-shadow cubemap allocation failed\n";
            return;
        }
        for (std::size_t face = 0; face < point_shadow_framebuffers_.size(); ++face) {
            std::array<bgfx::Attachment, 1> attachments;
            attachments[0].init(point_shadow_texture_, bgfx::Access::Write,
                                static_cast<std::uint16_t>(face), 1, 0, 0);
            point_shadow_framebuffers_[face] = bgfx::createFrameBuffer(
                static_cast<std::uint8_t>(attachments.size()), attachments.data(), false);
            if (!bgfx::isValid(point_shadow_framebuffers_[face])) {
                std::cerr << "RIX warning: point-shadow framebuffer face "
                          << face << " allocation failed\n";
                destroy_point_shadow_target();
                return;
            }
            const auto view = static_cast<bgfx::ViewId>(point_shadow_first_view + face);
            bgfx::setViewFrameBuffer(view, point_shadow_framebuffers_[face]);
            bgfx::setViewRect(view, 0, 0, resolution, resolution);
            bgfx::setViewClear(view, BGFX_CLEAR_COLOR, 0xffffffff, 1.0F, 0);
        }
        point_shadow_resolution_ = resolution;
    }

    void submit_postprocess(const bgfx::ViewId view,
                            const bgfx::TextureHandle source,
                            const std::uint32_t width,
                            const std::uint32_t height) {
        constexpr std::array<PostprocessVertex, 3> vertices{{
            {{-1.0F, -1.0F, 0.0F}, {0.0F, 1.0F}},
            {{3.0F, -1.0F, 0.0F}, {2.0F, 1.0F}},
            {{-1.0F, 3.0F, 0.0F}, {0.0F, -1.0F}},
        }};
        if (bgfx::getAvailTransientVertexBuffer(
                static_cast<std::uint32_t>(vertices.size()), postprocess_layout_) <
            vertices.size()) {
            return;
        }
        bgfx::TransientVertexBuffer buffer;
        bgfx::allocTransientVertexBuffer(
            &buffer, static_cast<std::uint32_t>(vertices.size()), postprocess_layout_);
        std::memcpy(buffer.data, vertices.data(), sizeof(vertices));
        const std::array<float, 4> params{
            1.0F / static_cast<float>(width),
            1.0F / static_cast<float>(height),
            1.0F,
            graphics_features_.fxaa ? 1.0F : 0.0F,
        };
        bgfx::touch(view);
        bgfx::setVertexBuffer(0, &buffer);
        bgfx::setTexture(0, postprocess_sampler_, source);
        bgfx::setUniform(postprocess_params_, params.data());
        bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_A);
        bgfx::submit(view, postprocess_program_);
        ++stats_.draw_calls;
    }

    void update_sky_cubemap(const SkyboxConfig& sky) {
        bool changed = !bgfx::isValid(sky_cubemap_texture_);
        for (std::size_t index = 0; index < sky.cubemap.size(); ++index) {
            changed = changed || sky_cubemap_identity_[index] != sky.cubemap[index].get() ||
                      sky_cubemap_revisions_[index] != sky.cubemap[index]->revision;
        }
        if (!changed) return;
        const std::uint32_t size = sky.cubemap[0]->width;
        const std::size_t face_bytes = static_cast<std::size_t>(size) * size * 4U;
        if (size > std::numeric_limits<std::uint16_t>::max() ||
            face_bytes > std::numeric_limits<std::uint32_t>::max() / 6U) {
            throw EngineError("sky cubemap exceeds bgfx upload limits");
        }
        std::vector<std::uint8_t> pixels;
        pixels.reserve(face_bytes * 6U);
        for (const auto& face : sky.cubemap) {
            pixels.insert(pixels.end(), face->rgba8.begin(), face->rgba8.end());
        }
        const std::uint64_t flags = BGFX_TEXTURE_SRGB | BGFX_SAMPLER_UVW_CLAMP;
        const bgfx::TextureHandle replacement = bgfx::createTextureCube(
            static_cast<std::uint16_t>(size), false, 1, bgfx::TextureFormat::RGBA8,
            flags,
            bgfx::copy(pixels.data(), static_cast<std::uint32_t>(pixels.size())));
        if (!bgfx::isValid(replacement)) {
            throw EngineError("bgfx failed to upload the sky cubemap");
        }
        if (bgfx::isValid(sky_cubemap_texture_)) bgfx::destroy(sky_cubemap_texture_);
        sky_cubemap_texture_ = replacement;
        sky_cubemap_memory_bytes_ = pixels.size();
        for (std::size_t index = 0; index < sky.cubemap.size(); ++index) {
            sky_cubemap_identity_[index] = sky.cubemap[index].get();
            sky_cubemap_revisions_[index] = sky.cubemap[index]->revision;
        }
    }

    void submit_sky(const Camera& active_camera) {
        if (scene_ == nullptr || !scene_->active() || !scene_->skybox().has_value()) {
            if (bgfx::isValid(sky_cubemap_texture_)) {
                bgfx::destroy(sky_cubemap_texture_);
                sky_cubemap_texture_ = BGFX_INVALID_HANDLE;
                sky_cubemap_identity_.fill(nullptr);
                sky_cubemap_revisions_.fill(0);
                sky_cubemap_memory_bytes_ = 0;
            }
            return;
        }
        constexpr std::array<PostprocessVertex, 3> vertices{{
            {{-1.0F, -1.0F, 0.0F}, {0.0F, 1.0F}},
            {{3.0F, -1.0F, 0.0F}, {2.0F, 1.0F}},
            {{-1.0F, 3.0F, 0.0F}, {0.0F, -1.0F}},
        }};
        if (bgfx::getAvailTransientVertexBuffer(
                static_cast<std::uint32_t>(vertices.size()), postprocess_layout_) <
            vertices.size()) return;
        const SkyboxConfig& sky = *scene_->skybox();
        if (sky.kind != SkyboxKind::Cubemap && bgfx::isValid(sky_cubemap_texture_)) {
            bgfx::destroy(sky_cubemap_texture_);
            sky_cubemap_texture_ = BGFX_INVALID_HANDLE;
            sky_cubemap_identity_.fill(nullptr);
            sky_cubemap_revisions_.fill(0);
            sky_cubemap_memory_bytes_ = 0;
        }
        bgfx::TransientVertexBuffer buffer;
        bgfx::allocTransientVertexBuffer(
            &buffer, static_cast<std::uint32_t>(vertices.size()), postprocess_layout_);
        std::memcpy(buffer.data, vertices.data(), sizeof(vertices));
        const float half_fov = active_camera.vertical_fov_degrees *
                               0.00872664625997164788F;
        const float vertical = std::tan(half_fov);
        const float horizontal = vertical * Camera::aspect_ratio(render_width_, render_height_);
        const Color sky_top = render_color(sky.top, linear_output_);
        const Color sky_horizon = render_color(sky.horizon, linear_output_);
        const Color sky_bottom = render_color(sky.bottom, linear_output_);
        const std::array<float, 4> top{
            sky_top.r, sky_top.g, sky_top.b, sky.brightness};
        const std::array<float, 4> horizon{
            sky_horizon.r, sky_horizon.g, sky_horizon.b, sky_horizon.a};
        const std::array<float, 4> bottom{
            sky_bottom.r, sky_bottom.g, sky_bottom.b, sky_bottom.a};
        const std::array<float, 4> params{
            static_cast<float>(sky.kind),
            sky.rotation_degrees * 0.01745329251994329577F,
            horizontal, vertical};
        const Vec3 right = active_camera.right();
        const Vec3 up = active_camera.up();
        const Vec3 forward = active_camera.forward();
        const std::array<float, 12> camera{
            right.x, right.y, right.z, 0.0F,
            up.x, up.y, up.z, 0.0F,
            forward.x, forward.y, forward.z, 0.0F};
        bgfx::setVertexBuffer(0, &buffer);
        bgfx::setUniform(sky_top_, top.data());
        bgfx::setUniform(sky_horizon_, horizon.data());
        bgfx::setUniform(sky_bottom_, bottom.data());
        bgfx::setUniform(sky_params_, params.data());
        bgfx::setUniform(sky_camera_, camera.data(), 3);
        texture_resources_->bind(*fallback_white_texture_, sky_panorama_sampler_, 7);
        bgfx::setTexture(8, sky_cubemap_sampler_, fallback_sky_cubemap_);
        if (sky.kind == SkyboxKind::Panorama) {
            TextureSampler sampler;
            sampler.min_filter = TextureFilter::Linear;
            sampler.mag_filter = TextureFilter::Linear;
            sampler.mip_filter = TextureFilter::Linear;
            sampler.wrap_u = TextureWrap::Repeat;
            sampler.wrap_v = TextureWrap::Clamp;
            const auto texture = texture_resources_->upload_cached(sky.panorama, sampler);
            texture_resources_->bind(texture, sky_panorama_sampler_, 7);
        } else if (sky.kind == SkyboxKind::Cubemap) {
            update_sky_cubemap(sky);
            bgfx::setTexture(8, sky_cubemap_sampler_, sky_cubemap_texture_);
        }
        bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_A);
        bgfx::submit(main_view, sky_program_);
        ++stats_.draw_calls;
    }

    [[nodiscard]] static ImageData checker_image() {
        ImageData image;
        image.source_path = "<RIX procedural checker>";
        image.width = 8;
        image.height = 8;
        image.color_space = TextureColorSpace::Srgb;
        image.rgba8.reserve(image.width * image.height * 4);
        for (std::uint32_t y = 0; y < image.height; ++y) {
            for (std::uint32_t x = 0; x < image.width; ++x) {
                const bool bright = (x + y) % 2 == 0;
                std::uint8_t red = bright ? 235 : 35;
                std::uint8_t green = bright ? 235 : 90;
                std::uint8_t blue = bright ? 235 : 170;
                // Asymmetric 2x2 corner markers make UV origin/orientation
                // visually testable: red, green, yellow, then magenta.
                if (x < 2 && y < 2) {
                    red = 255;
                    green = 35;
                    blue = 35;
                } else if (x >= 6 && y < 2) {
                    red = 35;
                    green = 220;
                    blue = 75;
                } else if (x < 2 && y >= 6) {
                    red = 255;
                    green = 210;
                    blue = 35;
                } else if (x >= 6 && y >= 6) {
                    red = 220;
                    green = 35;
                    blue = 220;
                }
                image.rgba8.insert(image.rgba8.end(), {red, green, blue, 255});
            }
        }
        image.validate();
        return image;
    }

    void create_geometry_diagnostic() {
        const auto triangle = mesh_resources_->upload(make_triangle_mesh());
        const auto cube = mesh_resources_->upload(make_cube_mesh());
        const auto plane = mesh_resources_->upload(make_plane_mesh(8.0F, 8.0F));
        const auto sphere = mesh_resources_->upload(make_uv_sphere_mesh());
        TextureSampler checker_sampler;
        checker_sampler.min_filter = TextureFilter::Nearest;
        checker_sampler.mag_filter = TextureFilter::Nearest;
        const auto checker = texture_resources_->upload(checker_image(), checker_sampler);

        draw_items_ = {
            {triangle, {{0.95F, 0.35F, 0.25F, 1.0F}}, translated(-2.0F, 0.2F, 0.0F), std::nullopt},
            {cube, {{0.25F, 0.75F, 0.95F, 1.0F}}, translated(0.0F, 0.0F, 0.0F), std::nullopt},
            {plane, {{1.0F, 1.0F, 1.0F, 1.0F}}, translated(0.0F, -0.75F, 0.0F), checker},
            {sphere, {{0.95F, 0.75F, 0.20F, 1.0F}}, translated(2.0F, 0.0F, 0.0F), std::nullopt},
        };
        camera_ = Camera::look_at({0.0F, 2.7F, 7.0F}, {0.0F, 0.0F, 0.0F});
        camera_.vertical_fov_degrees = 55.0F;
        camera_.near_plane = 0.1F;
        camera_.far_plane = 100.0F;
    }

    void update_view_rect() const {
        bgfx::setViewRect(main_view, 0, 0, view_extent(width_), view_extent(height_));
        bgfx::setViewRect(postprocess_view,
                          0,
                          0,
                          view_extent(width_),
                          view_extent(height_));
        bgfx::setViewRect(ui_view, 0, 0, view_extent(width_), view_extent(height_));
    }

    [[nodiscard]] static glm::mat4 model_matrix(const Transform& transform) {
        const glm::quat rotation{transform.rotation.w,
                                 transform.rotation.x,
                                 transform.rotation.y,
                                 transform.rotation.z};
        return glm::translate(glm::mat4(1.0F),
                              {transform.position.x,
                               transform.position.y,
                               transform.position.z}) *
               glm::mat4_cast(rotation) *
               glm::scale(glm::mat4(1.0F),
                          {transform.scale.x, transform.scale.y, transform.scale.z});
    }

    void update_scene_lighting(const Camera& active_camera, const Frustum& frustum) {
        lighting_ = {};
        directional_shadow_enabled_ = false;
        if (scene_ == nullptr || !scene_->active()) {
            return;
        }

        bool has_ambient = false;
        struct Candidate final {
            EntityHandle handle;
            const LightComponent* light;
            Transform transform;
            float score;
        };
        std::vector<Candidate> directionals;
        std::vector<Candidate> points;
        std::vector<Candidate> spots;
        for (const EntityHandle handle : scene_->entity_handles()) {
            if (!scene_->entity_enabled(handle) || !scene_->has_light_component(handle)) {
                continue;
            }
            const LightComponent& light = scene_->light_component(handle);
            const Color light_color = render_color(light.color, linear_output_);
            if (light.kind == LightKind::Ambient) {
                if (!has_ambient) {
                    lighting_.ambient = {0.0F, 0.0F, 0.0F, 1.0F};
                    has_ambient = true;
                }
                lighting_.ambient[0] += light_color.r * light.intensity;
                lighting_.ambient[1] += light_color.g * light.intensity;
                lighting_.ambient[2] += light_color.b * light.intensity;
                continue;
            }
            const Transform transform = scene_->world_transform(handle);
            const Vec3 offset = transform.position - active_camera.position;
            const float distance_squared = offset.length_squared();
            const float score = (light.casts_shadows ? 1.0e9F : 0.0F) +
                                light.intensity / (1.0F + distance_squared);
            Candidate candidate{handle, &light, transform, score};
            if (light.kind == LightKind::Directional) {
                directionals.push_back(candidate);
                continue;
            }
            bool relevant = false;
            if (light.kind == LightKind::Point) {
                const Transform volume{transform.position,
                                       {},
                                       {light.range, light.range, light.range}};
                relevant = frustum.intersects({{-1.0F, -1.0F, -1.0F},
                                               {1.0F, 1.0F, 1.0F}},
                                              volume);
            } else {
                constexpr float degrees_to_radians = 0.01745329251994329577F;
                const float cone_radius = light.range * std::tan(
                    light.outer_angle_degrees * 0.5F * degrees_to_radians);
                const Transform volume{transform.position, transform.rotation, {1, 1, 1}};
                relevant = frustum.intersects(
                    {{-cone_radius, -cone_radius, -light.range},
                     {cone_radius, cone_radius, 0.0F}},
                    volume);
            }
            if (!relevant) {
                ++stats_.culled_lights;
                continue;
            }
            (light.kind == LightKind::Point ? points : spots).push_back(candidate);
        }
        const auto priority = [](const Candidate& left, const Candidate& right) {
            if (left.score != right.score) return left.score > right.score;
            return left.handle.id() < right.handle.id();
        };
        std::stable_sort(directionals.begin(), directionals.end(), priority);
        std::stable_sort(points.begin(), points.end(), priority);
        std::stable_sort(spots.begin(), spots.end(), priority);

        const std::size_t directional_count = std::min<std::size_t>(
            directionals.size(), graphics_features_.max_directional_lights);
        const std::size_t point_count = std::min<std::size_t>(
            points.size(), graphics_features_.max_point_lights);
        const std::size_t spot_count = std::min<std::size_t>(
            spots.size(), graphics_features_.max_spot_lights);
        stats_.culled_lights += static_cast<std::uint32_t>(
            directionals.size() - directional_count + points.size() - point_count +
            spots.size() - spot_count);
        for (std::size_t index = 0; index < directional_count; ++index) {
            const Candidate& candidate = directionals[index];
            const Color color = render_color(candidate.light->color, linear_output_);
            const Vec3 direction = candidate.transform.rotation
                                       .rotate({0.0F, 0.0F, -1.0F})
                                       .normalized();
            lighting_.directional_directions[index] = {
                direction.x, direction.y, direction.z, 0.0F};
            lighting_.directional_colors[index] = {
                color.r * candidate.light->intensity,
                color.g * candidate.light->intensity,
                color.b * candidate.light->intensity,
                1.0F};
        }
        for (std::size_t index = 0; index < point_count; ++index) {
            const Candidate& candidate = points[index];
            const Color color = render_color(candidate.light->color, linear_output_);
            lighting_.point_positions_ranges[index] = {
                candidate.transform.position.x, candidate.transform.position.y,
                candidate.transform.position.z, candidate.light->range};
            lighting_.point_colors[index] = {
                color.r * candidate.light->intensity,
                color.g * candidate.light->intensity,
                color.b * candidate.light->intensity, 1.0F};
        }
        constexpr float degrees_to_radians = 0.01745329251994329577F;
        for (std::size_t index = 0; index < spot_count; ++index) {
            const Candidate& candidate = spots[index];
            const Color color = render_color(candidate.light->color, linear_output_);
            const Vec3 direction = candidate.transform.rotation
                                       .rotate({0.0F, 0.0F, -1.0F})
                                       .normalized();
            lighting_.spot_positions_ranges[index] = {
                candidate.transform.position.x, candidate.transform.position.y,
                candidate.transform.position.z, candidate.light->range};
            lighting_.spot_directions_outer[index] = {
                direction.x, direction.y, direction.z,
                std::cos(candidate.light->outer_angle_degrees * 0.5F *
                         degrees_to_radians)};
            lighting_.spot_colors_inner[index] = {
                color.r * candidate.light->intensity,
                color.g * candidate.light->intensity,
                color.b * candidate.light->intensity,
                std::cos(candidate.light->inner_angle_degrees * 0.5F *
                         degrees_to_radians)};
        }
        lighting_.counts = {static_cast<float>(directional_count),
                            static_cast<float>(point_count),
                            static_cast<float>(spot_count), 0.0F};
        stats_.active_directional_lights = static_cast<std::uint32_t>(directional_count);
        stats_.active_point_lights = static_cast<std::uint32_t>(point_count);
        stats_.active_spot_lights = static_cast<std::uint32_t>(spot_count);
        directional_shadow_enabled_ = graphics_features_.shadows &&
                                      directional_count > 0 &&
                                      directionals.front().light->casts_shadows;
        point_shadow_enabled_ = graphics_features_.shadows && point_count > 0 &&
                                points.front().light->casts_shadows;
        spot_shadow_enabled_ = graphics_features_.shadows && spot_count > 0 &&
                               spots.front().light->casts_shadows;
        const std::uint16_t max_texture = static_cast<std::uint16_t>(std::min(
            bgfx::getCaps()->limits.maxTextureSize,
            static_cast<std::uint32_t>(std::numeric_limits<std::uint16_t>::max())));
        if (directional_shadow_enabled_) {
            const LightComponent& selected = *directionals.front().light;
            directional_shadow_bias_ = selected.shadow_bias;
            const std::uint16_t requested = selected.shadow_resolution != 0
                ? selected.shadow_resolution : graphics_features_.shadow_resolution;
            const std::uint16_t resolution = std::min(requested, max_texture);
            if (resolution != shadow_resolution_) create_shadow_target(resolution);
            directional_shadow_enabled_ = shadow_active_;
        }
        if (point_shadow_enabled_) {
            const Candidate& selected = points.front();
            point_shadow_light_ = {
                selected.transform.position.x, selected.transform.position.y,
                selected.transform.position.z, selected.light->range};
            point_shadow_bias_ = selected.light->shadow_bias;
            const std::uint16_t requested = selected.light->shadow_resolution != 0
                ? selected.light->shadow_resolution
                : static_cast<std::uint16_t>(std::max<std::uint32_t>(
                      512U, graphics_features_.shadow_resolution / 4U));
            create_point_shadow_target(std::min(requested, max_texture));
            point_shadow_enabled_ = bgfx::isValid(point_shadow_texture_);
        } else {
            destroy_point_shadow_target();
        }
        if (spot_shadow_enabled_) {
            const Candidate& selected = spots.front();
            spot_shadow_position_ = selected.transform.position;
            spot_shadow_direction_ = selected.transform.rotation
                                         .rotate({0.0F, 0.0F, -1.0F})
                                         .normalized();
            spot_shadow_range_ = selected.light->range;
            spot_shadow_angle_ = selected.light->outer_angle_degrees;
            spot_shadow_bias_ = selected.light->shadow_bias;
            const std::uint16_t requested = selected.light->shadow_resolution != 0
                ? selected.light->shadow_resolution
                : static_cast<std::uint16_t>(std::max<std::uint32_t>(
                      512U, graphics_features_.shadow_resolution / 2U));
            create_spot_shadow_target(std::min(requested, max_texture));
            spot_shadow_enabled_ = bgfx::isValid(spot_shadow_texture_);
        } else {
            destroy_spot_shadow_target();
        }
        const auto requested_shadows = [](const std::vector<Candidate>& values) {
            return static_cast<std::uint32_t>(std::count_if(
                values.begin(), values.end(),
                [](const Candidate& value) { return value.light->casts_shadows; }));
        };
        const std::uint32_t requested_count = requested_shadows(directionals) +
                                              requested_shadows(points) +
                                              requested_shadows(spots);
        stats_.active_shadow_casters =
            static_cast<std::uint32_t>(directional_shadow_enabled_) +
            static_cast<std::uint32_t>(point_shadow_enabled_) +
            static_cast<std::uint32_t>(spot_shadow_enabled_);
        stats_.dropped_shadow_casters =
            requested_count > stats_.active_shadow_casters
                ? requested_count - stats_.active_shadow_casters : 0U;
        stats_.shadow_passes = static_cast<std::uint32_t>(directional_shadow_enabled_) +
                               static_cast<std::uint32_t>(spot_shadow_enabled_) +
                               (point_shadow_enabled_ ? 6U : 0U);
        stats_.shadow_memory_bytes =
            (directional_shadow_enabled_
                 ? static_cast<std::uint64_t>(shadow_resolution_) * shadow_resolution_ * 8U
                 : 0U) +
            (spot_shadow_enabled_
                 ? static_cast<std::uint64_t>(spot_shadow_resolution_) *
                       spot_shadow_resolution_ * 8U
                 : 0U) +
            (point_shadow_enabled_
                 ? static_cast<std::uint64_t>(point_shadow_resolution_) *
                       point_shadow_resolution_ * 24U
                 : 0U);
    }

    void apply_draw_uniforms(const Material& material,
                             const glm::mat4& transform,
                             const SceneBatch::Textures& textures,
                             const SceneBatch::Mapping& mapping) {
        const Color shader_color = render_color(material.color, linear_output_);
        const std::array<float, 4> color = {
            shader_color.r, shader_color.g, shader_color.b, shader_color.a};
        const std::array<float, 4> material_params = {
            material.lit ? 1.0F : 0.0F,
            material.metallic,
            material.roughness,
            material.emission};
        const std::array<float, 4> render_params = {
            graphics_features_.enhanced_lighting ? 1.0F : 0.0F,
            shadow_active_ && directional_shadow_enabled_ && material.receives_shadows
                ? 1.0F
                : 0.0F,
            0.0F,
            0.0F};
        const float inverse_shadow_size =
            shadow_active_ ? 1.0F / static_cast<float>(shadow_resolution_) : 1.0F;
        const std::array<float, 4> shadow_params = {
            inverse_shadow_size, inverse_shadow_size, directional_shadow_bias_, 0.0F};
        const glm::mat3 normal = glm::inverseTranspose(glm::mat3(transform));
        const std::array<float, 12> normal_rows = {
            normal[0][0], normal[1][0], normal[2][0], 0.0F,
            normal[0][1], normal[1][1], normal[2][1], 0.0F,
            normal[0][2], normal[1][2], normal[2][2], 0.0F,
        };
        bgfx::setTransform(glm::value_ptr(transform));
        bgfx::setUniform(material_color_, color.data());
        bgfx::setUniform(material_params_, material_params.data());
        bgfx::setUniform(normal_matrix_, normal_rows.data(), 3);
        bgfx::setUniform(ambient_light_, lighting_.ambient.data());
        bgfx::setUniform(directional_lights_, lighting_.directional_directions.data(),
                         static_cast<std::uint16_t>(max_directional_lights));
        bgfx::setUniform(directional_colors_, lighting_.directional_colors.data(),
                         static_cast<std::uint16_t>(max_directional_lights));
        bgfx::setUniform(point_positions_ranges_, lighting_.point_positions_ranges.data(),
                         static_cast<std::uint16_t>(max_point_lights));
        bgfx::setUniform(point_colors_, lighting_.point_colors.data(),
                         static_cast<std::uint16_t>(max_point_lights));
        bgfx::setUniform(spot_positions_ranges_, lighting_.spot_positions_ranges.data(),
                         static_cast<std::uint16_t>(max_spot_lights));
        bgfx::setUniform(spot_directions_outer_, lighting_.spot_directions_outer.data(),
                         static_cast<std::uint16_t>(max_spot_lights));
        bgfx::setUniform(spot_colors_inner_, lighting_.spot_colors_inner.data(),
                         static_cast<std::uint16_t>(max_spot_lights));
        bgfx::setUniform(light_counts_, lighting_.counts.data());
        bgfx::setUniform(camera_position_, camera_position_value_.data());
        bgfx::setUniform(render_params_, render_params.data());
        bgfx::setUniform(shadow_matrix_uniform_, glm::value_ptr(shadow_matrix_));
        bgfx::setUniform(shadow_params_, shadow_params.data());
        const std::array<float, 4> local_shadow_flags = {
            spot_shadow_enabled_ && material.receives_shadows ? 1.0F : 0.0F,
            point_shadow_enabled_ && material.receives_shadows ? 1.0F : 0.0F,
            0.0F, 0.0F};
        const float inverse_spot_size = spot_shadow_resolution_ > 0
            ? 1.0F / static_cast<float>(spot_shadow_resolution_) : 1.0F;
        const std::array<float, 4> local_shadow_params = {
            inverse_spot_size, inverse_spot_size,
            spot_shadow_bias_, point_shadow_bias_};
        bgfx::setUniform(spot_shadow_matrix_uniform_, glm::value_ptr(spot_shadow_matrix_));
        bgfx::setUniform(local_shadow_flags_, local_shadow_flags.data());
        bgfx::setUniform(local_shadow_params_, local_shadow_params.data());
        bgfx::setUniform(point_shadow_light_uniform_, point_shadow_light_.data());
        const std::array<float, 4> texture_params = {
            mapping.mode,
            material.normal_strength,
            textures.normal.has_value() ? 1.0F : 0.0F,
            textures.ambient_occlusion.has_value() ? 1.0F : 0.0F,
        };
        const std::array<float, 4> map_flags = {
            textures.roughness.has_value() ? 1.0F : 0.0F,
            textures.metallic.has_value() ? 1.0F : 0.0F,
            textures.emissive.has_value() ? 1.0F : 0.0F,
            material.packed_metallic_roughness ? 1.0F : 0.0F,
        };
        bgfx::setUniform(uv_scale_, mapping.scales.data(), 3);
        bgfx::setUniform(uv_atlas_, mapping.atlas.data(), 6);
        bgfx::setUniform(texture_params_, texture_params.data());
        bgfx::setUniform(map_flags_, map_flags.data());
        bgfx::setTexture(1,
                         shadow_sampler_,
                         shadow_active_ ? shadow_texture_ : fallback_shadow_texture_);
        bgfx::setTexture(7, spot_shadow_sampler_,
                         spot_shadow_enabled_ ? spot_shadow_texture_
                                              : fallback_shadow_texture_);
        bgfx::setTexture(8, point_shadow_sampler_,
                         point_shadow_enabled_ ? point_shadow_texture_
                                               : fallback_sky_cubemap_);
    }

    void apply_draw_uniforms(const Material& material, const glm::mat4& transform) {
        static const SceneBatch::Textures textures{};
        static const SceneBatch::Mapping mapping{
            {1.0F, 1.0F, 0.0F, 0.0F,
             1.0F, 1.0F, 0.0F, 0.0F,
             1.0F, 1.0F, 0.0F, 0.0F},
            {},
            0.0F};
        apply_draw_uniforms(material, transform, textures, mapping);
    }

    void bind_material_textures(const SceneBatch::Textures& textures) {
        if (textures.albedo.has_value()) {
            texture_resources_->bind(*textures.albedo, texture_sampler_, 0);
        }
        const auto bind_or_fallback = [&](const std::optional<TextureLifetimeManager::Handle> value,
                                          const TextureLifetimeManager::Handle fallback,
                                          const bgfx::UniformHandle sampler,
                                          const std::uint8_t stage) {
            texture_resources_->bind(value.value_or(fallback), sampler, stage);
        };
        bind_or_fallback(textures.normal,
                         *fallback_normal_texture_,
                         normal_sampler_,
                         2);
        bind_or_fallback(textures.roughness,
                         *fallback_white_texture_,
                         roughness_sampler_,
                         3);
        bind_or_fallback(textures.metallic,
                         *fallback_white_texture_,
                         metallic_sampler_,
                         4);
        bind_or_fallback(textures.emissive,
                         *fallback_white_texture_,
                         emissive_sampler_,
                         5);
        bind_or_fallback(textures.ambient_occlusion,
                         *fallback_white_texture_,
                         ambient_occlusion_sampler_,
                         6);
    }

    void submit_draw(const MeshLifetimeManager::Handle mesh,
                     const Material& material,
                     const glm::mat4& transform,
                     const SceneBatch::Textures& textures,
                     const SceneBatch::Mapping& mapping) {
        apply_draw_uniforms(material, transform, textures, mapping);
        mesh_resources_->bind(mesh);
        if (textures.albedo.has_value()) {
            bind_material_textures(textures);
        }
        bgfx::setState(render_state(material));
        bgfx::submit(main_view,
                     textures.albedo.has_value() ? textured_program_ : solid_program_);
        ++stats_.draw_calls;
    }

    void submit_draw(const MeshLifetimeManager::Handle mesh,
                     const Material& material,
                     const glm::mat4& transform,
                     const std::optional<TextureLifetimeManager::Handle> texture) {
        SceneBatch::Textures textures;
        textures.albedo = texture;
        static const SceneBatch::Mapping mapping{
            {1.0F, 1.0F, 0.0F, 0.0F,
             1.0F, 1.0F, 0.0F, 0.0F,
             1.0F, 1.0F, 0.0F, 0.0F},
            {},
            0.0F};
        submit_draw(mesh, material, transform, textures, mapping);
    }

    static void add_to_batch(std::vector<SceneBatch>& batches,
                             const MeshLifetimeManager::Handle mesh,
                             const Material& material,
                             const SceneBatch::Textures& textures,
                             const SceneBatch::Mapping& mapping,
                             const glm::mat4& transform,
                             const bool instancing_eligible) {
        const auto found = std::find_if(
            batches.begin(), batches.end(),
            [&](const SceneBatch& batch) {
                return batch.mesh == mesh && batch.material == material &&
                       batch.textures == textures && batch.mapping == mapping &&
                       batch.instancing_eligible == instancing_eligible;
            });
        if (found != batches.end()) {
            found->transforms.push_back(transform);
            return;
        }
        SceneBatch batch{mesh, material, textures, mapping, {}, instancing_eligible};
        batch.transforms.push_back(transform);
        batches.push_back(std::move(batch));
    }

    static void add_to_shadow_batch(std::vector<ShadowBatch>& batches,
                                    const MeshLifetimeManager::Handle mesh,
                                    const CullMode cull_mode,
                                    const glm::mat4& transform) {
        const auto found = std::find_if(
            batches.begin(), batches.end(),
            [mesh, cull_mode](const ShadowBatch& batch) {
                return batch.mesh == mesh && batch.cull_mode == cull_mode;
            });
        if (found != batches.end()) {
            found->transforms.push_back(transform);
            return;
        }
        batches.push_back({mesh, cull_mode, {transform}});
    }

    void submit_shadow_batch(const ShadowBatch& batch,
                             const bgfx::ViewId view,
                             const bgfx::ProgramHandle program,
                             const bgfx::ProgramHandle instanced_program,
                             const bool radial = false) {
        constexpr std::uint16_t instance_stride = sizeof(float) * 16;
        if (batch.transforms.size() == 1) {
            bgfx::setTransform(glm::value_ptr(batch.transforms.front()));
            mesh_resources_->bind(batch.mesh);
            bgfx::setState(BGFX_STATE_WRITE_RGB | cull_state(batch.cull_mode) |
                           (radial ? BGFX_STATE_BLEND_DARKEN
                                   : BGFX_STATE_WRITE_Z | BGFX_STATE_DEPTH_TEST_LESS));
            bgfx::submit(view, program);
            ++stats_.draw_calls;
            return;
        }
        std::size_t offset = 0;
        while (offset < batch.transforms.size()) {
            const auto requested = static_cast<std::uint32_t>(std::min(
                batch.transforms.size() - offset,
                static_cast<std::size_t>(std::numeric_limits<std::uint32_t>::max())));
            const std::uint32_t available =
                bgfx::getAvailInstanceDataBuffer(requested, instance_stride);
            if (available == 0) {
                return;
            }
            bgfx::InstanceDataBuffer instances;
            bgfx::allocInstanceDataBuffer(&instances, available, instance_stride);
            std::uint8_t* destination = instances.data;
            for (std::uint32_t index = 0; index < available; ++index) {
                std::memcpy(destination,
                            glm::value_ptr(batch.transforms[offset + index]),
                            instance_stride);
                destination += instance_stride;
            }
            mesh_resources_->bind(batch.mesh);
            bgfx::setInstanceDataBuffer(&instances);
            bgfx::setState(BGFX_STATE_WRITE_RGB | cull_state(batch.cull_mode) |
                           (radial ? BGFX_STATE_BLEND_DARKEN
                                   : BGFX_STATE_WRITE_Z | BGFX_STATE_DEPTH_TEST_LESS));
            bgfx::submit(view, instanced_program);
            ++stats_.draw_calls;
            ++stats_.instanced_draw_calls;
            offset += available;
        }
    }

    void submit_directional_shadow(const Camera& active_camera) {
        if (!shadow_active_ || !directional_shadow_enabled_) {
            shadow_matrix_ = glm::mat4(1.0F);
            return;
        }
        const Vec3 direction{lighting_.directional_directions[0][0],
                             lighting_.directional_directions[0][1],
                             lighting_.directional_directions[0][2]};
        const Vec3 target = active_camera.position + active_camera.forward() * 12.0F;
        Camera light_camera = Camera::look_at(target - direction * 45.0F, target);
        light_camera.projection = CameraProjection::Orthographic;
        light_camera.orthographic_height = 50.0F;
        light_camera.near_plane = 0.1F;
        light_camera.far_plane = 100.0F;
        const Matrix4 view = light_camera.view_matrix();
        const Matrix4 projection = light_camera.projection_matrix(
            1.0F, bgfx::getCaps()->homogeneousDepth);
        bgfx::setViewTransform(shadow_view, view.data(), projection.data());
        bgfx::touch(shadow_view);

        const float sy = bgfx::getCaps()->originBottomLeft ? 0.5F : -0.5F;
        const float sz = bgfx::getCaps()->homogeneousDepth ? 0.5F : 1.0F;
        const float tz = bgfx::getCaps()->homogeneousDepth ? 0.5F : 0.0F;
        glm::mat4 bias{1.0F};
        bias[0][0] = 0.5F;
        bias[1][1] = sy;
        bias[2][2] = sz;
        bias[3][0] = 0.5F;
        bias[3][1] = 0.5F;
        bias[3][2] = tz;
        shadow_matrix_ = bias * glm::make_mat4(projection.data()) *
                         glm::make_mat4(view.data());

        std::vector<ShadowBatch> batches;
        for (const DrawItem& item : draw_items_) {
            if (item.material.casts_shadows) {
                add_to_shadow_batch(
                    batches, item.mesh, item.material.cull_mode, item.transform);
            }
        }
        if (scene_ != nullptr && scene_->active()) {
            for (const EntityHandle handle : scene_->entity_handles()) {
                if (!scene_->entity_enabled(handle) || !scene_->entity_visible(handle) ||
                    !scene_->has_render_component(handle)) {
                    continue;
                }
                const RenderComponent& component = scene_->render_component(handle);
                if (!component.material.casts_shadows) {
                    continue;
                }
                const Transform world_transform = scene_->world_transform(handle);
                const glm::mat4 transform = model_matrix(world_transform);
                if (component.mesh) {
                    add_to_shadow_batch(
                        batches,
                        mesh_resources_->upload_cached(*component.mesh),
                        transformed_cull_mode(component.material.cull_mode, world_transform),
                        transform);
                } else if (component.model) {
                    for (const ModelPart& part : component.model->parts) {
                        const ModelMaterial& source =
                            component.model->materials[part.material_index];
                        add_to_shadow_batch(
                            batches,
                            mesh_resources_->upload_cached(part.mesh),
                            transformed_cull_mode(
                                model_cull_mode(component, source), world_transform),
                            transform);
                    }
                }
            }
        }
        for (const ShadowBatch& batch : batches) {
            submit_shadow_batch(
                batch, shadow_view, shadow_program_, shadow_instanced_program_);
        }
    }

    [[nodiscard]] std::vector<ShadowBatch> collect_shadow_batches() {
        std::vector<ShadowBatch> batches;
        for (const DrawItem& item : draw_items_) {
            if (item.material.casts_shadows) {
                add_to_shadow_batch(
                    batches, item.mesh, item.material.cull_mode, item.transform);
            }
        }
        if (scene_ == nullptr || !scene_->active()) return batches;
        for (const EntityHandle handle : scene_->entity_handles()) {
            if (!scene_->entity_enabled(handle) || !scene_->entity_visible(handle) ||
                !scene_->has_render_component(handle)) continue;
            const RenderComponent& component = scene_->render_component(handle);
            if (!component.material.casts_shadows) continue;
            const Transform world_transform = scene_->world_transform(handle);
            const glm::mat4 transform = model_matrix(world_transform);
            if (component.mesh) {
                add_to_shadow_batch(
                    batches, mesh_resources_->upload_cached(*component.mesh),
                    transformed_cull_mode(component.material.cull_mode, world_transform),
                    transform);
            } else if (component.model) {
                for (const ModelPart& part : component.model->parts) {
                    const ModelMaterial& source =
                        component.model->materials[part.material_index];
                    add_to_shadow_batch(
                        batches, mesh_resources_->upload_cached(part.mesh),
                        transformed_cull_mode(
                            model_cull_mode(component, source), world_transform),
                        transform);
                }
            }
        }
        return batches;
    }

    [[nodiscard]] static glm::mat4 shadow_bias_matrix() {
        const float sy = bgfx::getCaps()->originBottomLeft ? 0.5F : -0.5F;
        const float sz = bgfx::getCaps()->homogeneousDepth ? 0.5F : 1.0F;
        const float tz = bgfx::getCaps()->homogeneousDepth ? 0.5F : 0.0F;
        glm::mat4 bias{1.0F};
        bias[0][0] = 0.5F;
        bias[1][1] = sy;
        bias[2][2] = sz;
        bias[3][0] = 0.5F;
        bias[3][1] = 0.5F;
        bias[3][2] = tz;
        return bias;
    }

    void submit_local_shadows() {
        if (!spot_shadow_enabled_ && !point_shadow_enabled_) {
            spot_shadow_matrix_ = glm::mat4(1.0F);
            return;
        }
        const std::vector<ShadowBatch> batches = collect_shadow_batches();
        if (spot_shadow_enabled_) {
            Camera camera = Camera::look_at(
                spot_shadow_position_, spot_shadow_position_ + spot_shadow_direction_);
            camera.vertical_fov_degrees = spot_shadow_angle_;
            camera.near_plane = std::min(0.05F, spot_shadow_range_ * 0.01F);
            camera.far_plane = spot_shadow_range_;
            const Matrix4 view = camera.view_matrix();
            const Matrix4 projection = camera.projection_matrix(
                1.0F, bgfx::getCaps()->homogeneousDepth);
            bgfx::setViewTransform(spot_shadow_view, view.data(), projection.data());
            bgfx::touch(spot_shadow_view);
            spot_shadow_matrix_ = shadow_bias_matrix() *
                                  glm::make_mat4(projection.data()) *
                                  glm::make_mat4(view.data());
            for (const ShadowBatch& batch : batches) {
                submit_shadow_batch(batch, spot_shadow_view,
                                    shadow_program_, shadow_instanced_program_);
            }
        } else {
            spot_shadow_matrix_ = glm::mat4(1.0F);
        }
        if (!point_shadow_enabled_) return;
        const Vec3 position{point_shadow_light_[0], point_shadow_light_[1],
                            point_shadow_light_[2]};
        constexpr std::array<Vec3, 6> directions{{
            {1,0,0}, {-1,0,0}, {0,1,0}, {0,-1,0}, {0,0,1}, {0,0,-1}}};
        constexpr std::array<Vec3, 6> ups{{
            {0,1,0}, {0,1,0}, {0,0,-1}, {0,0,1}, {0,1,0}, {0,1,0}}};
        bgfx::setUniform(point_shadow_light_uniform_, point_shadow_light_.data());
        for (std::size_t face = 0; face < directions.size(); ++face) {
            Camera camera = Camera::look_at(position, position + directions[face], ups[face]);
            camera.vertical_fov_degrees = 90.0F;
            camera.near_plane = std::min(0.05F, point_shadow_light_[3] * 0.01F);
            camera.far_plane = point_shadow_light_[3];
            const Matrix4 view = camera.view_matrix();
            const Matrix4 projection = camera.projection_matrix(
                1.0F, bgfx::getCaps()->homogeneousDepth);
            const auto view_id =
                static_cast<bgfx::ViewId>(point_shadow_first_view + face);
            bgfx::setViewTransform(view_id, view.data(), projection.data());
            bgfx::touch(view_id);
            for (const ShadowBatch& batch : batches) {
                submit_shadow_batch(batch, view_id,
                                    point_shadow_program_,
                                    point_shadow_instanced_program_, true);
            }
        }
    }

    void submit_shadows(const Camera& active_camera) {
        submit_directional_shadow(active_camera);
        submit_local_shadows();
    }

    void submit_instanced_batch(const SceneBatch& batch) {
        constexpr std::uint16_t instance_stride = sizeof(float) * 16;
        std::size_t offset = 0;
        while (offset < batch.transforms.size()) {
            const auto requested = static_cast<std::uint32_t>(std::min(
                batch.transforms.size() - offset,
                static_cast<std::size_t>(std::numeric_limits<std::uint32_t>::max())));
            const std::uint32_t available =
                bgfx::getAvailInstanceDataBuffer(requested, instance_stride);
            if (available < 2) {
                for (; offset < batch.transforms.size(); ++offset) {
                    submit_draw(batch.mesh,
                                batch.material,
                                batch.transforms[offset],
                                batch.textures,
                                batch.mapping);
                }
                return;
            }

            bgfx::InstanceDataBuffer instances;
            bgfx::allocInstanceDataBuffer(&instances, available, instance_stride);
            std::uint8_t* destination = instances.data;
            for (std::uint32_t index = 0; index < available; ++index) {
                std::memcpy(destination,
                            glm::value_ptr(batch.transforms[offset + index]),
                            instance_stride);
                destination += instance_stride;
            }

            const glm::mat4 identity{1.0F};
            apply_draw_uniforms(batch.material, identity, batch.textures, batch.mapping);
            mesh_resources_->bind(batch.mesh);
            if (batch.textures.albedo.has_value()) {
                bind_material_textures(batch.textures);
            }
            bgfx::setInstanceDataBuffer(&instances);
            bgfx::setState(render_state(batch.material));
            bgfx::submit(main_view,
                         batch.textures.albedo.has_value() ? textured_instanced_program_
                                                           : solid_instanced_program_);
            ++stats_.draw_calls;
            ++stats_.instanced_draw_calls;
            offset += available;
        }
    }

    void submit_scene(const Frustum& frustum) {
        if (scene_ == nullptr || !scene_->active()) {
            return;
        }
        std::vector<SceneBatch> batches;
        const std::vector<EntityHandle> handles = scene_->entity_handles();
        bool has_model = false;
        for (const EntityHandle handle : handles) {
            if (!scene_->entity_enabled(handle) || !scene_->entity_visible(handle) ||
                !scene_->has_render_component(handle)) {
                continue;
            }
            const RenderComponent& component = scene_->render_component(handle);
            const Transform world_transform = scene_->world_transform(handle);
            const glm::mat4 transform = model_matrix(world_transform);
            const bool instancing_eligible = has_uniform_scale(world_transform);
            if (component.mesh) {
                if (!frustum.intersects(mesh_resources_->bounds_cached(*component.mesh),
                                        world_transform)) {
                    ++stats_.culled_instances;
                    continue;
                }
                ++stats_.visible_instances;
                const auto mesh = mesh_resources_->upload_cached(*component.mesh);
                SceneBatch::Textures textures;
                if (component.texture) {
                    textures.albedo = texture_resources_->upload_cached(
                        component.texture, component.sampler);
                }
                if (component.normal_map) {
                    textures.normal = texture_resources_->upload_cached(
                        component.normal_map, component.sampler);
                }
                if (component.roughness_map) {
                    textures.roughness = texture_resources_->upload_cached(
                        component.roughness_map, component.sampler);
                }
                if (component.metallic_map) {
                    textures.metallic = texture_resources_->upload_cached(
                        component.metallic_map, component.sampler);
                }
                if (component.emissive_map) {
                    textures.emissive = texture_resources_->upload_cached(
                        component.emissive_map, component.sampler);
                }
                if (component.ambient_occlusion_map) {
                    textures.ambient_occlusion = texture_resources_->upload_cached(
                        component.ambient_occlusion_map, component.sampler);
                }
                Material material = component.material;
                material.cull_mode = transformed_cull_mode(
                    material.cull_mode, world_transform);
                add_to_batch(batches,
                             mesh,
                             material,
                             textures,
                             texture_mapping(component, world_transform),
                             transform,
                             instancing_eligible);
                continue;
            }
            if (!component.model) {
                throw EngineError("render component has no mesh or model resource");
            }
            has_model = true;
            for (const ModelPart& part : component.model->parts) {
                if (!frustum.intersects(mesh_resources_->bounds_cached(part.mesh),
                                        world_transform)) {
                    ++stats_.culled_instances;
                    continue;
                }
                ++stats_.visible_instances;
                Material material = component.material;
                const ModelMaterial& source = component.model->materials[part.material_index];
                material.color = {
                    material.color.r * source.diffuse_color.r,
                    material.color.g * source.diffuse_color.g,
                    material.color.b * source.diffuse_color.b,
                    material.color.a * source.diffuse_color.a,
                };
                if (source.authored_surface) {
                    material.metallic = source.metallic;
                    material.roughness = source.roughness;
                    material.emission = source.emission;
                }
                material.normal_strength = source.normal_strength;
                material.packed_metallic_roughness =
                    source.packed_metallic_roughness;
                material.cull_mode = transformed_cull_mode(
                    model_cull_mode(component, source), world_transform);
                SceneBatch::Textures textures;
                if (source.diffuse_texture.has_value()) {
                    const auto image = scene_textures_.load(*source.diffuse_texture);
                    textures.albedo = texture_resources_->upload_cached(image);
                }
                if (source.normal_texture.has_value()) {
                    const auto image = scene_textures_.load(
                        *source.normal_texture, TextureColorSpace::Linear);
                    textures.normal = texture_resources_->upload_cached(image);
                }
                if (source.roughness_texture.has_value()) {
                    const auto image = scene_textures_.load(
                        *source.roughness_texture, TextureColorSpace::Linear);
                    textures.roughness = texture_resources_->upload_cached(image);
                }
                if (source.metallic_texture.has_value()) {
                    const auto image = scene_textures_.load(
                        *source.metallic_texture, TextureColorSpace::Linear);
                    textures.metallic = texture_resources_->upload_cached(image);
                }
                if (source.emissive_texture.has_value()) {
                    const auto image = scene_textures_.load(
                        *source.emissive_texture, TextureColorSpace::Srgb);
                    textures.emissive = texture_resources_->upload_cached(image);
                }
                if (source.ambient_occlusion_texture.has_value()) {
                    const auto image = scene_textures_.load(
                        *source.ambient_occlusion_texture, TextureColorSpace::Linear);
                    textures.ambient_occlusion = texture_resources_->upload_cached(image);
                }
                SceneBatch::Mapping mapping;
                mapping.scales = {1.0F, 1.0F, 0.0F, 0.0F,
                                  1.0F, 1.0F, 0.0F, 0.0F,
                                  1.0F, 1.0F, 0.0F, 0.0F};
                add_to_batch(batches,
                             mesh_resources_->upload_cached(part.mesh),
                             material,
                             textures,
                             mapping,
                             transform,
                             instancing_eligible);
            }
        }

        if (!has_model) {
            scene_textures_.clear();
        }

        for (const SceneBatch& batch : batches) {
            if (batch.instancing_eligible && batch.transforms.size() > 1) {
                submit_instanced_batch(batch);
                continue;
            }
            for (const glm::mat4& transform : batch.transforms) {
                submit_draw(batch.mesh,
                            batch.material,
                            transform,
                            batch.textures,
                            batch.mapping);
            }
        }
    }

    void submit_debug_batch(const std::vector<GpuVertex>& vertices,
                            const bool depth_test) {
        if (vertices.empty() || vertices.size() > std::numeric_limits<std::uint32_t>::max()) {
            return;
        }
        const auto vertex_count = static_cast<std::uint32_t>(vertices.size());
        if (bgfx::getAvailTransientVertexBuffer(vertex_count, layout_) < vertex_count) {
            return;
        }
        bgfx::TransientVertexBuffer buffer;
        bgfx::allocTransientVertexBuffer(&buffer, vertex_count, layout_);
        std::copy(vertices.begin(), vertices.end(),
                  reinterpret_cast<GpuVertex*>(buffer.data));

        Material material;
        material.lit = false;
        material.depth_test = depth_test;
        material.depth_write = false;
        material.cull_mode = CullMode::None;
        const glm::mat4 identity{1.0F};
        apply_draw_uniforms(material, identity);
        bgfx::setVertexBuffer(0, &buffer, 0, vertex_count);
        bgfx::setState(render_state(material) | BGFX_STATE_PT_LINES);
        bgfx::submit(main_view, solid_program_);
        ++stats_.draw_calls;
    }

    void submit_debug_lines() {
        if (scene_ == nullptr || !scene_->active() || scene_->debug_lines().empty()) {
            return;
        }
        std::vector<GpuVertex> depth_lines;
        std::vector<GpuVertex> overlay_lines;
        depth_lines.reserve(scene_->debug_lines().size() * 2);
        overlay_lines.reserve(scene_->debug_lines().size() * 2);
        for (const DebugLine& line : scene_->debug_lines()) {
            std::vector<GpuVertex>& destination =
                line.depth_test ? depth_lines : overlay_lines;
            const std::uint32_t color = line.color.rgba8();
            destination.push_back({{line.start.x, line.start.y, line.start.z},
                                   {0.0F, 1.0F, 0.0F},
                                   {0.0F, 0.0F},
                                   color});
            destination.push_back({{line.end.x, line.end.y, line.end.z},
                                   {0.0F, 1.0F, 0.0F},
                                   {0.0F, 0.0F},
                                   color});
        }
        submit_debug_batch(depth_lines, true);
        submit_debug_batch(overlay_lines, false);
    }

    void submit_geometry(const Camera* const camera_override = nullptr) {
        if (scene_ != nullptr) {
            (void)scene_->poll_texture_changes();
        }
        (void)scene_textures_.poll_changes();
        const Camera& active_camera = camera_override != nullptr
            ? *camera_override
            : (scene_ == nullptr ? camera_ : scene_->camera());
        camera_position_value_ = {
            active_camera.position.x,
            active_camera.position.y,
            active_camera.position.z,
            1.0F};
        const Matrix4 view = active_camera.view_matrix();
        const Matrix4 projection = active_camera.projection_matrix(
            Camera::aspect_ratio(render_width_, render_height_),
            bgfx::getCaps()->homogeneousDepth);
        const Frustum frustum = Frustum::from_view_projection(
            projection * view, bgfx::getCaps()->homogeneousDepth);
        update_scene_lighting(active_camera, frustum);
        submit_shadows(active_camera);
        bgfx::setViewTransform(main_view, view.data(), projection.data());
        submit_sky(active_camera);

        for (const DrawItem& item : draw_items_) {
            ++stats_.visible_instances;
            submit_draw(item.mesh, item.material, item.transform, item.texture);
        }
        submit_scene(frustum);
        submit_debug_lines();
    }

    bool initialized_{false};
    GraphicsPreset graphics_preset_{GraphicsPreset::Medium};
    GraphicsFeatures graphics_features_{};
    std::uint32_t reset_flags_{BGFX_RESET_NONE};
    std::uint32_t width_{1};
    std::uint32_t height_{1};
    std::uint32_t render_width_{1};
    std::uint32_t render_height_{1};
    std::uint32_t last_frame_{0};
    std::uint64_t next_viewport_request_id_{1};
    bgfx::SwapChain swap_chain_{};
    bgfx::VertexLayout layout_{};
    bgfx::VertexLayout postprocess_layout_{};
    bgfx::VertexLayout ui_layout_{};
    bgfx::ProgramHandle solid_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle textured_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle solid_instanced_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle textured_instanced_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle postprocess_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle sky_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle shadow_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle shadow_instanced_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle point_shadow_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle point_shadow_instanced_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle ui_program_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle material_color_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle material_params_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle normal_matrix_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle ambient_light_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle directional_lights_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle directional_colors_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle point_positions_ranges_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle point_colors_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle spot_positions_ranges_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle spot_directions_outer_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle spot_colors_inner_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle light_counts_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle camera_position_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle render_params_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle texture_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle postprocess_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle postprocess_params_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle sky_top_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle sky_horizon_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle sky_bottom_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle sky_params_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle sky_camera_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle sky_panorama_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle sky_cubemap_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle shadow_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle shadow_matrix_uniform_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle shadow_params_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle spot_shadow_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle point_shadow_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle spot_shadow_matrix_uniform_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle local_shadow_flags_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle local_shadow_params_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle point_shadow_light_uniform_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle uv_scale_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle uv_atlas_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle texture_params_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle map_flags_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle normal_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle roughness_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle metallic_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle emissive_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle ambient_occlusion_sampler_{BGFX_INVALID_HANDLE};
    bgfx::FrameBufferHandle scene_framebuffer_{BGFX_INVALID_HANDLE};
    bgfx::TextureHandle scene_color_{BGFX_INVALID_HANDLE};
    bgfx::FrameBufferHandle capture_framebuffer_{BGFX_INVALID_HANDLE};
    bgfx::TextureHandle capture_color_{BGFX_INVALID_HANDLE};
    bgfx::TextureHandle capture_readback_{BGFX_INVALID_HANDLE};
    std::unordered_map<std::uint64_t, ViewportTarget> viewport_targets_;
    std::unordered_map<std::uint64_t, PendingViewportReadback>
        pending_viewport_readbacks_;
    bool postprocess_active_{false};
    bool linear_output_{false};
    bgfx::FrameBufferHandle shadow_framebuffer_{BGFX_INVALID_HANDLE};
    bgfx::TextureHandle shadow_texture_{BGFX_INVALID_HANDLE};
    bgfx::TextureHandle fallback_shadow_texture_{BGFX_INVALID_HANDLE};
    bgfx::TextureHandle sky_cubemap_texture_{BGFX_INVALID_HANDLE};
    bgfx::TextureHandle fallback_sky_cubemap_{BGFX_INVALID_HANDLE};
    std::array<const ImageData*, 6> sky_cubemap_identity_{};
    std::array<std::uint64_t, 6> sky_cubemap_revisions_{};
    std::size_t sky_cubemap_memory_bytes_{0};
    std::uint16_t shadow_resolution_{0};
    bool shadow_active_{false};
    bool directional_shadow_enabled_{false};
    float directional_shadow_bias_{0.002F};
    glm::mat4 shadow_matrix_{1.0F};
    bgfx::FrameBufferHandle spot_shadow_framebuffer_{BGFX_INVALID_HANDLE};
    bgfx::TextureHandle spot_shadow_texture_{BGFX_INVALID_HANDLE};
    std::uint16_t spot_shadow_resolution_{0};
    bool spot_shadow_enabled_{false};
    Vec3 spot_shadow_position_{};
    Vec3 spot_shadow_direction_{0.0F, -1.0F, 0.0F};
    float spot_shadow_range_{10.0F};
    float spot_shadow_angle_{45.0F};
    float spot_shadow_bias_{0.002F};
    glm::mat4 spot_shadow_matrix_{1.0F};
    std::array<bgfx::FrameBufferHandle, 6> point_shadow_framebuffers_{};
    bgfx::TextureHandle point_shadow_texture_{BGFX_INVALID_HANDLE};
    std::uint16_t point_shadow_resolution_{0};
    bool point_shadow_enabled_{false};
    std::array<float, 4> point_shadow_light_{0.0F, 0.0F, 0.0F, 1.0F};
    float point_shadow_bias_{0.002F};
    std::unique_ptr<MeshLifetimeManager> mesh_resources_;
    std::unique_ptr<TextureLifetimeManager> texture_resources_;
    std::vector<DrawItem> draw_items_;
    Camera camera_{};
    LightingState lighting_{};
    std::array<float, 4> camera_position_value_{0.0F, 0.0F, 0.0F, 1.0F};
    std::array<stbtt_bakedchar, 96> font_glyphs_{};
    std::shared_ptr<const ImageData> ui_font_image_;
    std::optional<TextureLifetimeManager::Handle> ui_font_texture_;
    std::vector<std::shared_ptr<const ImageData>> fallback_material_images_;
    std::optional<TextureLifetimeManager::Handle> fallback_white_texture_;
    std::optional<TextureLifetimeManager::Handle> fallback_normal_texture_;
    TextureSampler ui_sampler_{};
    RendererStats stats_{};
    const Scene* scene_{nullptr};
    TextureCache scene_textures_;
};

BgfxRenderer::BgfxRenderer(void* native_window,
                           const std::uint32_t width,
                           const std::uint32_t height,
                           const bool vsync,
                           const GraphicsPreset graphics_preset,
                           const bool geometry_diagnostic,
                           const Scene* const scene)
    : impl_(std::make_unique<Impl>()) {
    impl_->initialize(native_window,
                      width,
                      height,
                      vsync,
                      graphics_preset,
                      geometry_diagnostic,
                      scene);
}

BgfxRenderer::~BgfxRenderer() {
    impl_->shutdown();
}

void BgfxRenderer::resize(const std::uint32_t width, const std::uint32_t height) {
    impl_->resize(width, height);
}

void BgfxRenderer::present() {
    impl_->present();
}

void BgfxRenderer::render_offscreen() {
    impl_->render_offscreen();
}

std::vector<std::uint8_t> BgfxRenderer::readback_rgba8() {
    return impl_->readback_rgba8();
}

std::vector<std::uint8_t> BgfxRenderer::render_viewport_rgba8(
    const Camera& camera,
    const std::uint32_t width,
    const std::uint32_t height) {
    return impl_->render_viewport_rgba8(camera, width, height);
}

std::uint64_t BgfxRenderer::request_viewport_rgba8(
    const Camera& camera,
    const std::uint32_t width,
    const std::uint32_t height) {
    return impl_->request_viewport_rgba8(camera, width, height);
}

std::optional<std::vector<std::uint8_t>> BgfxRenderer::poll_viewport_rgba8(
    const std::uint64_t request_id) {
    return impl_->poll_viewport_rgba8(request_id);
}

std::vector<std::uint8_t> BgfxRenderer::wait_viewport_rgba8(
    const std::uint64_t request_id) {
    return impl_->wait_viewport_rgba8(request_id);
}

void BgfxRenderer::cancel_viewport_rgba8(const std::uint64_t request_id) noexcept {
    impl_->cancel_viewport_rgba8(request_id);
}

RendererStats BgfxRenderer::stats() const noexcept {
    return impl_->stats();
}

} // namespace easy3d::renderer
