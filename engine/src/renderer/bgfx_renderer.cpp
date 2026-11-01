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

#include "fs_solid_color.sc.bin.h"
#include "fs_textured.sc.bin.h"
#include "vs_solid_color.sc.bin.h"
#include "vs_textured.sc.bin.h"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
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

constexpr bgfx::ViewId main_view = 0;

struct GpuVertex final {
    float position[3];
    float normal[3];
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
    }

    [[nodiscard]] std::size_t size() const noexcept { return meshes_.size(); }
    [[nodiscard]] std::size_t triangle_count() const noexcept { return triangle_count_; }

private:
    bgfx::VertexLayout layout_;
    std::vector<GpuMesh> meshes_;
    std::size_t triangle_count_{0};
    std::unordered_map<const MeshData*, Handle> shared_;
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
    }

    [[nodiscard]] std::size_t size() const noexcept { return textures_.size(); }
    [[nodiscard]] std::size_t byte_size() const noexcept { return byte_size_; }

private:
    std::vector<GpuTexture> textures_;
    std::size_t byte_size_{0};
    std::unordered_map<const ImageData*,
                       std::vector<std::pair<TextureSampler, Handle>>> shared_;
};

struct DrawItem final {
    MeshLifetimeManager::Handle mesh;
    Material material;
    glm::mat4 transform{1.0F};
    std::optional<TextureLifetimeManager::Handle> texture;
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

} // namespace

class BgfxRenderer::Impl final {
public:
    void initialize(void* native_window,
                    const std::uint32_t width,
                    const std::uint32_t height,
                    const bool vsync,
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
            mesh_resources_ = std::make_unique<MeshLifetimeManager>(layout_);
            texture_resources_ = std::make_unique<TextureLifetimeManager>();
            scene_ = scene;
            create_programs();
            if (geometry_diagnostic) {
                create_geometry_diagnostic();
            }

            const bgfx::Caps* caps = bgfx::getCaps();
            std::ostringstream message;
            message << "Easy3D renderer: " << bgfx::getRendererName(bgfx::getRendererType())
                    << ", vendor=0x" << std::hex << std::setw(4) << std::setfill('0')
                    << caps->vendorId << ", device=0x" << std::setw(4) << caps->deviceId;
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
        if (texture_resources_) {
            texture_resources_->reset();
            texture_resources_.reset();
        }
        if (mesh_resources_) {
            mesh_resources_->reset();
            mesh_resources_.reset();
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
        if (bgfx::isValid(texture_sampler_)) {
            bgfx::destroy(texture_sampler_);
            texture_sampler_ = BGFX_INVALID_HANDLE;
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
        update_view_rect();
    }

    void present() {
        bgfx::touch(main_view);
        if (!draw_items_.empty() || scene_ != nullptr) {
            submit_geometry();
        }
        bgfx::frame();
    }

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
        material_color_ = bgfx::createUniform("u_materialColor", bgfx::UniformType::Vec4);
        material_params_ = bgfx::createUniform("u_materialParams", bgfx::UniformType::Vec4);
        normal_matrix_ = bgfx::createUniform("u_normalMatrix", bgfx::UniformType::Vec4, 3);
        ambient_light_ = bgfx::createUniform("u_ambientLight", bgfx::UniformType::Vec4);
        directional_light_ =
            bgfx::createUniform("u_directionalLight", bgfx::UniformType::Vec4);
        directional_color_ =
            bgfx::createUniform("u_directionalColor", bgfx::UniformType::Vec4);
        texture_sampler_ = bgfx::createUniform("s_texColor", bgfx::UniformType::Sampler);
        if (!bgfx::isValid(material_color_) || !bgfx::isValid(material_params_) ||
            !bgfx::isValid(normal_matrix_) || !bgfx::isValid(ambient_light_) ||
            !bgfx::isValid(directional_light_) || !bgfx::isValid(directional_color_) ||
            !bgfx::isValid(texture_sampler_)) {
            throw EngineError("bgfx failed to create Easy3D material uniforms");
        }
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
            material.lit ? 1.0F : 0.0F, 0.0F, 0.0F, 0.0F};
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
    }

    void submit_scene() {
        if (scene_ == nullptr || !scene_->active()) {
            return;
        }
        for (const EntityHandle handle : scene_->entity_handles()) {
            if (!scene_->entity_enabled(handle) || !scene_->entity_visible(handle) ||
                !scene_->has_render_component(handle)) {
                continue;
            }
            const RenderComponent& component = scene_->render_component(handle);
            const glm::mat4 transform = model_matrix(scene_->world_transform(handle));
            if (component.mesh) {
                const auto mesh = mesh_resources_->upload_cached(*component.mesh);
                std::optional<TextureLifetimeManager::Handle> texture;
                if (component.texture) {
                    texture = texture_resources_->upload_cached(
                        *component.texture, component.sampler);
                }
                submit_draw(mesh, component.material, transform, texture);
                continue;
            }
            if (!component.model) {
                throw EngineError("render component has no mesh or model resource");
            }
            for (const ModelPart& part : component.model->parts) {
                Material material = component.material;
                const ModelMaterial& source = component.model->materials[part.material_index];
                material.color = {
                    material.color.r * source.diffuse_color.r,
                    material.color.g * source.diffuse_color.g,
                    material.color.b * source.diffuse_color.b,
                    material.color.a * source.diffuse_color.a,
                };
                std::optional<TextureLifetimeManager::Handle> texture;
                if (source.diffuse_texture.has_value()) {
                    const auto image = scene_textures_.load(*source.diffuse_texture);
                    texture = texture_resources_->upload_cached(*image);
                }
                submit_draw(mesh_resources_->upload_cached(part.mesh),
                            material,
                            transform,
                            texture);
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
        const Matrix4 view = active_camera.view_matrix();
        const Matrix4 projection = active_camera.projection_matrix(
            Camera::aspect_ratio(width_, height_), bgfx::getCaps()->homogeneousDepth);
        bgfx::setViewTransform(main_view, view.data(), projection.data());

        for (const DrawItem& item : draw_items_) {
            submit_draw(item.mesh, item.material, item.transform, item.texture);
        }
        submit_scene();
        submit_debug_lines();
    }

    bool initialized_{false};
    std::uint32_t reset_flags_{BGFX_RESET_NONE};
    std::uint32_t width_{1};
    std::uint32_t height_{1};
    bgfx::SwapChain swap_chain_{};
    bgfx::VertexLayout layout_{};
    bgfx::ProgramHandle solid_program_{BGFX_INVALID_HANDLE};
    bgfx::ProgramHandle textured_program_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle material_color_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle material_params_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle normal_matrix_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle ambient_light_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle directional_light_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle directional_color_{BGFX_INVALID_HANDLE};
    bgfx::UniformHandle texture_sampler_{BGFX_INVALID_HANDLE};
    std::unique_ptr<MeshLifetimeManager> mesh_resources_;
    std::unique_ptr<TextureLifetimeManager> texture_resources_;
    std::vector<DrawItem> draw_items_;
    Camera camera_{};
    LightingState lighting_{};
    const Scene* scene_{nullptr};
    TextureCache scene_textures_;
};

BgfxRenderer::BgfxRenderer(void* native_window,
                           const std::uint32_t width,
                           const std::uint32_t height,
                           const bool vsync,
                           const bool geometry_diagnostic,
                           const Scene* const scene)
    : impl_(std::make_unique<Impl>()) {
    impl_->initialize(native_window, width, height, vsync, geometry_diagnostic, scene);
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

} // namespace easy3d::renderer
