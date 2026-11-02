#include "renderer/bgfx_renderer.hpp"

#include "easy3d/assets.hpp"
#include "easy3d/core.hpp"
#include "easy3d/renderer.hpp"
#include "easy3d/scene.hpp"

#include <bgfx/bgfx.h>
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
#include "fs_shadow.sc.bin.h"
#include "fs_ui.sc.bin.h"
#include "vs_solid_color.sc.bin.h"
#include "vs_solid_color_instanced.sc.bin.h"
#include "vs_textured.sc.bin.h"
#include "vs_textured_instanced.sc.bin.h"
#include "vs_postprocess.sc.bin.h"
#include "vs_shadow.sc.bin.h"
#include "vs_shadow_instanced.sc.bin.h"
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
constexpr bgfx::ViewId main_view = 1;
constexpr bgfx::ViewId postprocess_view = 2;
constexpr bgfx::ViewId ui_view = 3;

struct GpuVertex final {
    float position[3];
    float normal[3];
    float uv[2];
    std::uint32_t color;
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

    void bind(const bgfx::UniformHandle sampler) const {
        if (!bgfx::isValid(texture_)) {
            throw EngineError("attempted to bind a released GPU texture");
        }
        bgfx::setTexture(0, sampler, texture_);
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
        if (!bgfx::isTextureValid(0, false, 1, bgfx::TextureFormat::RGBA8, flags)) {
            throw EngineError("active renderer does not support the requested RGBA8 texture flags");
        }
        const bgfx::Memory* memory = bgfx::copy(
            image.rgba8.data(), static_cast<std::uint32_t>(image.byte_size()));
        const bgfx::TextureHandle texture = bgfx::createTexture2D(
            static_cast<std::uint16_t>(image.width),
            static_cast<std::uint16_t>(image.height),
            false,
            1,
            bgfx::TextureFormat::RGBA8,
            flags,
            memory);
        if (!bgfx::isValid(texture)) {
            throw EngineError("bgfx failed to allocate an RGBA8 GPU texture");
        }
        textures_.emplace_back(texture);
        byte_size_ += image.byte_size();
        return textures_.size() - 1;
    }

    [[nodiscard]] Handle upload_cached(const ImageData& image,
                                       const TextureSampler& sampler = {}) {
        const auto found = shared_.find(&image);
        if (found != shared_.end()) {
            for (const auto& [cached_sampler, handle] : found->second) {
                if (cached_sampler == sampler) {
                    return handle;
                }
            }
        }
        const Handle handle = upload(image, sampler);
        shared_[&image].emplace_back(sampler, handle);
        return handle;
    }

    [[nodiscard]] Handle upload_cached(
        const std::shared_ptr<const ImageData>& image,
        const TextureSampler& sampler = {}) {
        if (!image) {
            throw EngineError("cannot upload an empty shared image");
        }
        const Handle handle = upload_cached(*image, sampler);
        if (std::none_of(owners_.begin(), owners_.end(),
                         [&](const auto& owner) { return owner.get() == image.get(); })) {
            owners_.push_back(image);
        }
        return handle;
    }

    void bind(const Handle handle, const bgfx::UniformHandle sampler) const {
        if (handle >= textures_.size()) {
            throw EngineError("invalid GPU texture handle");
        }
        textures_[handle].bind(sampler);
    }

    void reset() noexcept {
        textures_.clear();
        byte_size_ = 0;
        shared_.clear();
        owners_.clear();
    }

    [[nodiscard]] std::size_t size() const noexcept { return textures_.size(); }
    [[nodiscard]] std::size_t byte_size() const noexcept { return byte_size_; }

private:
    std::vector<GpuTexture> textures_;
    std::size_t byte_size_{0};
    std::unordered_map<const ImageData*,
                       std::vector<std::pair<TextureSampler, Handle>>> shared_;
    std::vector<std::shared_ptr<const ImageData>> owners_;
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
    std::optional<TextureLifetimeManager::Handle> texture;
    std::vector<glm::mat4> transforms;
    bool instancing_eligible{true};
};

struct ShadowBatch final {
    MeshLifetimeManager::Handle mesh;
    std::vector<glm::mat4> transforms;
};

struct LightingState final {
    std::array<float, 4> ambient{0.25F, 0.25F, 0.25F, 1.0F};
    std::array<float, 4> directional_direction{0.45F, -1.0F, 0.25F, 0.0F};
    std::array<float, 4> directional_color{0.75F, 0.75F, 0.75F, 1.0F};
};

[[nodiscard]] std::uint16_t view_extent(const std::uint32_t value) noexcept {
    return static_cast<std::uint16_t>(
        std::min(value, static_cast<std::uint32_t>(std::numeric_limits<std::uint16_t>::max())));
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
    if (material.cull_back_faces) {
        // Easy3D mesh data uses counter-clockwise front faces.
        state |= BGFX_STATE_CULL_CW;
    }
    return state;
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

} // namespace

class BgfxRenderer::Impl final {
public:
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
            create_font_atlas();
            bgfx::setViewMode(ui_view, bgfx::ViewMode::Sequential);
            if (geometry_diagnostic) {
                create_geometry_diagnostic();
            }
            std::cout << "Easy3D graphics: enhanced-lighting="
                      << (graphics_features_.enhanced_lighting ? "on" : "off")
                      << ", postprocessing=" << (postprocess_active_ ? "on" : "fallback-off")
                      << ", fxaa="
                      << (postprocess_active_ && graphics_features_.fxaa ? "on" : "off")
                      << ", shadows=" << (shadow_active_ ? "on" : "fallback-off")
                      << std::endl;

            const bgfx::Caps* caps = bgfx::getCaps();
            std::ostringstream message;
            message << "Easy3D renderer: " << bgfx::getRendererName(bgfx::getRendererType())
                    << ", vendor=0x" << std::hex << std::setw(4) << std::setfill('0')
                    << caps->vendorId << ", device=0x" << std::setw(4) << caps->deviceId
                    << std::dec << ", preset=" << graphics_preset_name(graphics_preset_);
            std::cout << message.str() << std::dec << std::endl;
            if (geometry_diagnostic) {
                std::cout << "Easy3D geometry: GPU meshes=" << mesh_resources_->size()
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
        destroy_postprocess_target();
        destroy_shadow_target();
        ui_font_image_.reset();
        ui_font_texture_.reset();
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
        if (bgfx::isValid(directional_light_)) {
            bgfx::destroy(directional_light_);
            directional_light_ = BGFX_INVALID_HANDLE;
        }
        if (bgfx::isValid(directional_color_)) {
            bgfx::destroy(directional_color_);
            directional_color_ = BGFX_INVALID_HANDLE;
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
        if (bgfx::isValid(fallback_shadow_texture_)) {
            bgfx::destroy(fallback_shadow_texture_);
            fallback_shadow_texture_ = BGFX_INVALID_HANDLE;
        }
        // Submit one final frame so queued resource releases are observed
        // before the renderer and its D3D11 device are destroyed.
        bgfx::frame();
        bgfx::shutdown();
        initialized_ = false;
    }

    void resize(const std::uint32_t width, const std::uint32_t height) {
        width_ = std::max(width, 1U);
        height_ = std::max(height, 1U);
        swap_chain_.width = width_;
        swap_chain_.height = height_;
        bgfx::reset(reset_flags_, &swap_chain_);
        create_postprocess_target();
        update_view_rect();
    }

    void present() {
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
        if (postprocess_active_) {
            submit_postprocess();
        }
        submit_ui();
        bgfx::frame();
    }

    [[nodiscard]] RendererStats stats() const noexcept { return stats_; }

private:
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
            throw EngineError(std::string("bgfx failed to create Easy3D ") + label + " shaders");
        }
        const bgfx::ProgramHandle program = bgfx::createProgram(vertex_shader, fragment_shader, true);
        if (!bgfx::isValid(program)) {
            throw EngineError(std::string("bgfx failed to link the Easy3D ") + label +
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
        ui_program_ = make_program(vs_ui_dxbc,
                                   static_cast<std::uint32_t>(sizeof(vs_ui_dxbc)),
                                   fs_ui_dxbc,
                                   static_cast<std::uint32_t>(sizeof(fs_ui_dxbc)),
                                   "UI");
        material_color_ = bgfx::createUniform("u_materialColor", bgfx::UniformType::Vec4);
        material_params_ = bgfx::createUniform("u_materialParams", bgfx::UniformType::Vec4);
        normal_matrix_ = bgfx::createUniform("u_normalMatrix", bgfx::UniformType::Vec4, 3);
        ambient_light_ = bgfx::createUniform("u_ambientLight", bgfx::UniformType::Vec4);
        directional_light_ =
            bgfx::createUniform("u_directionalLight", bgfx::UniformType::Vec4);
        directional_color_ =
            bgfx::createUniform("u_directionalColor", bgfx::UniformType::Vec4);
        camera_position_ =
            bgfx::createUniform("u_cameraPosition", bgfx::UniformType::Vec4);
        render_params_ = bgfx::createUniform("u_renderParams", bgfx::UniformType::Vec4);
        texture_sampler_ = bgfx::createUniform("s_texColor", bgfx::UniformType::Sampler);
        postprocess_sampler_ =
            bgfx::createUniform("s_sceneColor", bgfx::UniformType::Sampler);
        postprocess_params_ =
            bgfx::createUniform("u_postParams", bgfx::UniformType::Vec4);
        shadow_sampler_ = bgfx::createUniform("s_shadowMap", bgfx::UniformType::Sampler);
        shadow_matrix_uniform_ =
            bgfx::createUniform("u_shadowMatrix", bgfx::UniformType::Mat4);
        shadow_params_ = bgfx::createUniform("u_shadowParams", bgfx::UniformType::Vec4);
        if (!bgfx::isValid(material_color_) || !bgfx::isValid(material_params_) ||
            !bgfx::isValid(normal_matrix_) || !bgfx::isValid(ambient_light_) ||
            !bgfx::isValid(directional_light_) || !bgfx::isValid(directional_color_) ||
            !bgfx::isValid(camera_position_) || !bgfx::isValid(render_params_) ||
            !bgfx::isValid(texture_sampler_) || !bgfx::isValid(postprocess_sampler_) ||
            !bgfx::isValid(postprocess_params_) || !bgfx::isValid(shadow_sampler_) ||
            !bgfx::isValid(shadow_matrix_uniform_) || !bgfx::isValid(shadow_params_)) {
            throw EngineError("bgfx failed to create Easy3D material uniforms");
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
            throw EngineError("Easy3D could not bake the built-in UI font atlas");
        }
        auto image = std::make_shared<ImageData>();
        image->source_path = "<Easy3D built-in Roboto Regular>";
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
        ui_font_texture_ = texture_resources_->upload_cached(*ui_font_image_, ui_sampler_);
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
        shadow_active_ = false;
        bgfx::setViewFrameBuffer(shadow_view, BGFX_INVALID_HANDLE);
    }

    void create_shadow_target() {
        destroy_shadow_target();
        const std::array<std::uint8_t, 4> white{255, 255, 255, 255};
        fallback_shadow_texture_ = bgfx::createTexture2D(
            1,
            1,
            false,
            1,
            bgfx::TextureFormat::RGBA8,
            BGFX_SAMPLER_U_CLAMP | BGFX_SAMPLER_V_CLAMP,
            bgfx::copy(white.data(), static_cast<std::uint32_t>(white.size())));
        if (!bgfx::isValid(fallback_shadow_texture_)) {
            throw EngineError("bgfx failed to create the shadow fallback texture");
        }
        if (!graphics_features_.shadows) {
            return;
        }
        const bgfx::Caps* caps = bgfx::getCaps();
        const std::uint16_t resolution = static_cast<std::uint16_t>(std::min(
            static_cast<std::uint32_t>(graphics_features_.shadow_resolution),
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

    void submit_postprocess() {
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
            1.0F / static_cast<float>(width_),
            1.0F / static_cast<float>(height_),
            1.0F,
            graphics_features_.fxaa ? 1.0F : 0.0F,
        };
        bgfx::touch(postprocess_view);
        bgfx::setVertexBuffer(0, &buffer);
        bgfx::setTexture(0, postprocess_sampler_, scene_color_);
        bgfx::setUniform(postprocess_params_, params.data());
        bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_A);
        bgfx::submit(postprocess_view, postprocess_program_);
        ++stats_.draw_calls;
    }

    [[nodiscard]] static ImageData checker_image() {
        ImageData image;
        image.source_path = "<Easy3D procedural checker>";
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

    void update_scene_lighting() {
        lighting_ = {};
        if (scene_ == nullptr || !scene_->active()) {
            return;
        }

        bool has_ambient = false;
        bool has_directional = false;
        for (const EntityHandle handle : scene_->entity_handles()) {
            if (!scene_->entity_enabled(handle) || !scene_->has_light_component(handle)) {
                continue;
            }
            const LightComponent& light = scene_->light_component(handle);
            if (light.kind == LightKind::Ambient) {
                if (!has_ambient) {
                    lighting_.ambient = {0.0F, 0.0F, 0.0F, 1.0F};
                    has_ambient = true;
                }
                lighting_.ambient[0] += light.color.r * light.intensity;
                lighting_.ambient[1] += light.color.g * light.intensity;
                lighting_.ambient[2] += light.color.b * light.intensity;
            } else if (!has_directional) {
                const Vec3 direction = scene_->world_transform(handle)
                                           .rotation.rotate({0.0F, 0.0F, -1.0F})
                                           .normalized();
                lighting_.directional_direction = {
                    direction.x, direction.y, direction.z, 0.0F};
                lighting_.directional_color = {
                    light.color.r * light.intensity,
                    light.color.g * light.intensity,
                    light.color.b * light.intensity,
                    1.0F,
                };
                has_directional = true;
            }
        }
    }

    void apply_draw_uniforms(const Material& material, const glm::mat4& transform) {
        const std::array<float, 4> color = {
            material.color.r, material.color.g, material.color.b, material.color.a};
        const std::array<float, 4> material_params = {
            material.lit ? 1.0F : 0.0F,
            material.metallic,
            material.roughness,
            material.emission};
        const std::array<float, 4> render_params = {
            graphics_features_.enhanced_lighting ? 1.0F : 0.0F,
            shadow_active_ && material.receives_shadows ? 1.0F : 0.0F,
            0.0F,
            0.0F};
        const float inverse_shadow_size =
            shadow_active_ ? 1.0F / static_cast<float>(shadow_resolution_) : 1.0F;
        const std::array<float, 4> shadow_params = {
            inverse_shadow_size, inverse_shadow_size, 0.0015F, 0.0F};
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
        bgfx::setUniform(directional_light_, lighting_.directional_direction.data());
        bgfx::setUniform(directional_color_, lighting_.directional_color.data());
        bgfx::setUniform(camera_position_, camera_position_value_.data());
        bgfx::setUniform(render_params_, render_params.data());
        bgfx::setUniform(shadow_matrix_uniform_, glm::value_ptr(shadow_matrix_));
        bgfx::setUniform(shadow_params_, shadow_params.data());
        bgfx::setTexture(1,
                         shadow_sampler_,
                         shadow_active_ ? shadow_texture_ : fallback_shadow_texture_);
    }

    void submit_draw(const MeshLifetimeManager::Handle mesh,
                     const Material& material,
                     const glm::mat4& transform,
                     const std::optional<TextureLifetimeManager::Handle> texture) {
        apply_draw_uniforms(material, transform);
        mesh_resources_->bind(mesh);
        if (texture.has_value()) {
            texture_resources_->bind(*texture, texture_sampler_);
        }
        bgfx::setState(render_state(material));
        bgfx::submit(main_view, texture.has_value() ? textured_program_ : solid_program_);
        ++stats_.draw_calls;
    }

    static void add_to_batch(std::vector<SceneBatch>& batches,
                             const MeshLifetimeManager::Handle mesh,
                             const Material& material,
                             const std::optional<TextureLifetimeManager::Handle> texture,
                             const glm::mat4& transform,
                             const bool instancing_eligible) {
        const auto found = std::find_if(
            batches.begin(), batches.end(),
            [&](const SceneBatch& batch) {
                return batch.mesh == mesh && batch.material == material &&
                       batch.texture == texture &&
                       batch.instancing_eligible == instancing_eligible;
            });
        if (found != batches.end()) {
            found->transforms.push_back(transform);
            return;
        }
        SceneBatch batch{mesh, material, texture, {}, instancing_eligible};
        batch.transforms.push_back(transform);
        batches.push_back(std::move(batch));
    }

    static void add_to_shadow_batch(std::vector<ShadowBatch>& batches,
                                    const MeshLifetimeManager::Handle mesh,
                                    const glm::mat4& transform) {
        const auto found = std::find_if(
            batches.begin(), batches.end(),
            [mesh](const ShadowBatch& batch) { return batch.mesh == mesh; });
        if (found != batches.end()) {
            found->transforms.push_back(transform);
            return;
        }
        batches.push_back({mesh, {transform}});
    }

    void submit_shadow_batch(const ShadowBatch& batch) {
        constexpr std::uint16_t instance_stride = sizeof(float) * 16;
        if (batch.transforms.size() == 1) {
            bgfx::setTransform(glm::value_ptr(batch.transforms.front()));
            mesh_resources_->bind(batch.mesh);
            bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_Z |
                           BGFX_STATE_DEPTH_TEST_LESS | BGFX_STATE_CULL_CW);
            bgfx::submit(shadow_view, shadow_program_);
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
            bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_Z |
                           BGFX_STATE_DEPTH_TEST_LESS | BGFX_STATE_CULL_CW);
            bgfx::submit(shadow_view, shadow_instanced_program_);
            ++stats_.draw_calls;
            ++stats_.instanced_draw_calls;
            offset += available;
        }
    }

    void submit_shadows(const Camera& active_camera) {
        if (!shadow_active_) {
            shadow_matrix_ = glm::mat4(1.0F);
            return;
        }
        const Vec3 direction{lighting_.directional_direction[0],
                             lighting_.directional_direction[1],
                             lighting_.directional_direction[2]};
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
                add_to_shadow_batch(batches, item.mesh, item.transform);
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
                const glm::mat4 transform = model_matrix(scene_->world_transform(handle));
                if (component.mesh) {
                    add_to_shadow_batch(
                        batches, mesh_resources_->upload_cached(*component.mesh), transform);
                } else if (component.model) {
                    for (const ModelPart& part : component.model->parts) {
                        add_to_shadow_batch(
                            batches, mesh_resources_->upload_cached(part.mesh), transform);
                    }
                }
            }
        }
        for (const ShadowBatch& batch : batches) {
            submit_shadow_batch(batch);
        }
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
                                batch.texture);
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
            apply_draw_uniforms(batch.material, identity);
            mesh_resources_->bind(batch.mesh);
            if (batch.texture.has_value()) {
                texture_resources_->bind(*batch.texture, texture_sampler_);
            }
            bgfx::setInstanceDataBuffer(&instances);
            bgfx::setState(render_state(batch.material));
            bgfx::submit(main_view,
                         batch.texture.has_value() ? textured_instanced_program_
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
        for (const EntityHandle handle : scene_->entity_handles()) {
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
                std::optional<TextureLifetimeManager::Handle> texture;
                if (component.texture) {
                    texture = texture_resources_->upload_cached(
                        *component.texture, component.sampler);
                }
                add_to_batch(batches,
                             mesh,
                             component.material,
                             texture,
                             transform,
                             instancing_eligible);
                continue;
            }
            if (!component.model) {
                throw EngineError("render component has no mesh or model resource");
            }
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
                std::optional<TextureLifetimeManager::Handle> texture;
                if (source.diffuse_texture.has_value()) {
                    const auto image = scene_textures_.load(*source.diffuse_texture);
                    texture = texture_resources_->upload_cached(*image);
                }
                add_to_batch(batches,
                             mesh_resources_->upload_cached(part.mesh),
                             material,
                             texture,
                             transform,
                             instancing_eligible);
            }
        }

        for (const SceneBatch& batch : batches) {
            if (batch.instancing_eligible && batch.transforms.size() > 1) {
                submit_instanced_batch(batch);
                continue;
            }
            for (const glm::mat4& transform : batch.transforms) {
                submit_draw(batch.mesh, batch.material, transform, batch.texture);
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
        material.cull_back_faces = false;
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

    void submit_geometry() {
        update_scene_lighting();
        const Camera& active_camera = scene_ == nullptr ? camera_ : scene_->camera();
        camera_position_value_ = {
            active_camera.position.x,
            active_camera.position.y,
            active_camera.position.z,
            1.0F};
        submit_shadows(active_camera);
        const Matrix4 view = active_camera.view_matrix();
        const Matrix4 projection = active_camera.projection_matrix(
            Camera::aspect_ratio(width_, height_), bgfx::getCaps()->homogeneousDepth);
        bgfx::setViewTransform(main_view, view.data(), projection.data());
        const Frustum frustum = Frustum::from_view_projection(
            projection * view, bgfx::getCaps()->homogeneousDepth);

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
    bgfx::SwapChain swap_chain_{};
    bgfx::VertexLayout layout_{};
    bgfx::VertexLayout postprocess_layout_{};
    bgfx::VertexLayout ui_layout_{};
    bgfx::ProgramHandle solid_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle textured_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle solid_instanced_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle textured_instanced_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle postprocess_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle shadow_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle shadow_instanced_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle ui_program_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle material_color_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle material_params_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle normal_matrix_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle ambient_light_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle directional_light_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle directional_color_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle camera_position_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle render_params_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle texture_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle postprocess_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle postprocess_params_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle shadow_sampler_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle shadow_matrix_uniform_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle shadow_params_{BGFX_INVALID_HANDLE};
    bgfx::FrameBufferHandle scene_framebuffer_{BGFX_INVALID_HANDLE};
    bgfx::TextureHandle scene_color_{BGFX_INVALID_HANDLE};
    bool postprocess_active_{false};
    bgfx::FrameBufferHandle shadow_framebuffer_{BGFX_INVALID_HANDLE};
    bgfx::TextureHandle shadow_texture_{BGFX_INVALID_HANDLE};
    bgfx::TextureHandle fallback_shadow_texture_{BGFX_INVALID_HANDLE};
    std::uint16_t shadow_resolution_{0};
    bool shadow_active_{false};
    glm::mat4 shadow_matrix_{1.0F};
    std::unique_ptr<MeshLifetimeManager> mesh_resources_;
    std::unique_ptr<TextureLifetimeManager> texture_resources_;
    std::vector<DrawItem> draw_items_;
    Camera camera_{};
    LightingState lighting_{};
    std::array<float, 4> camera_position_value_{0.0F, 0.0F, 0.0F, 1.0F};
    std::array<stbtt_bakedchar, 96> font_glyphs_{};
    std::shared_ptr<const ImageData> ui_font_image_;
    std::optional<TextureLifetimeManager::Handle> ui_font_texture_;
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

RendererStats BgfxRenderer::stats() const noexcept {
    return impl_->stats();
}

} // namespace easy3d::renderer
