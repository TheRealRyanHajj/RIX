#include "easy3d/core.hpp"
#include "easy3d/assets.hpp"
#include "easy3d/renderer.hpp"
#include "easy3d/scene.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/operators.h>
#include <pybind11/stl.h>

#include <cstdint>
#include <memory>
#include <string>
#include <utility>

namespace py = pybind11;

PYBIND11_MODULE(_easy3d, module) {
    module.doc() = "Easy3D native engine core";

    const py::exception<easy3d::EngineError> engine_error =
        py::register_exception<easy3d::EngineError>(module, "EngineError");
    const py::exception<easy3d::AssetError> asset_error =
        py::register_exception<easy3d::AssetError>(module, "AssetError", engine_error.ptr());
    py::register_exception<easy3d::MissingAssetError>(
        module, "MissingAssetError", asset_error.ptr());
    py::register_exception<easy3d::InvalidEntityError>(
        module, "InvalidEntityError", PyExc_ReferenceError);

    module.def("engine_version", &easy3d::engine_version);
    module.def("native_add", &easy3d::native_add, py::arg("a"), py::arg("b"));
    py::enum_<easy3d::TextureColorSpace>(module, "_TextureColorSpace")
        .value("LINEAR", easy3d::TextureColorSpace::Linear)
        .value("SRGB", easy3d::TextureColorSpace::Srgb);
    const auto image_info = [](const std::shared_ptr<const easy3d::ImageData>& image) {
        return py::make_tuple(image->source_path.string(),
                              image->width,
                              image->height,
                              image->byte_size(),
                              image->color_space == easy3d::TextureColorSpace::Srgb);
    };
    module.def("_load_image_info",
               [image_info](const std::string& path,
                            const easy3d::TextureColorSpace color_space) {
                   return image_info(easy3d::load_image(path, color_space));
               },
               py::arg("path"),
               py::arg("color_space"));
    py::class_<easy3d::TextureCache>(module, "_TextureCache")
        .def(py::init<>())
        .def("load",
             [image_info](easy3d::TextureCache& cache,
                          const std::string& path,
                          const easy3d::TextureColorSpace color_space) {
                 return image_info(cache.load(path, color_space));
             },
             py::arg("path"),
             py::arg("color_space"))
        .def("clear", &easy3d::TextureCache::clear)
        .def_property_readonly("size", &easy3d::TextureCache::size);
    const auto model_info = [](const std::shared_ptr<const easy3d::ModelData>& model) {
        py::list parts;
        for (const easy3d::ModelPart& part : model->parts) {
            parts.append(py::make_tuple(part.name,
                                        part.mesh.vertices.size(),
                                        part.mesh.indices.size(),
                                        part.mesh.triangle_count(),
                                        part.material_index));
        }
        py::list materials;
        for (const easy3d::ModelMaterial& material : model->materials) {
            py::object texture = material.diffuse_texture.has_value()
                                     ? py::cast(material.diffuse_texture->string())
                                     : py::none();
            materials.append(py::make_tuple(material.name,
                                            py::make_tuple(material.diffuse_color.r,
                                                           material.diffuse_color.g,
                                                           material.diffuse_color.b,
                                                           material.diffuse_color.a),
                                            texture));
        }
        return py::make_tuple(model->source_path.string(),
                              model->triangle_count(),
                              parts,
                              materials,
                              model->warnings);
    };
    module.def("_load_obj_info",
               [model_info](const std::string& path) {
                   return model_info(easy3d::load_obj(path));
               },
               py::arg("path"));
    py::class_<easy3d::ModelCache>(module, "_ModelCache")
        .def(py::init<>())
        .def("load",
             [model_info](easy3d::ModelCache& cache, const std::string& path) {
                 return model_info(cache.load(path));
             },
             py::arg("path"))
        .def("clear", &easy3d::ModelCache::clear)
        .def_property_readonly("size", &easy3d::ModelCache::size);
    module.def("_quat_from_euler", [](const double x, const double y, const double z) {
        const easy3d::Quat value = easy3d::Quat::from_euler_degrees(
            {static_cast<float>(x), static_cast<float>(y), static_cast<float>(z)});
        return py::make_tuple(value.w, value.x, value.y, value.z);
    });
    module.def("_quat_to_euler", [](const double w,
                                      const double x,
                                      const double y,
                                      const double z) {
        const easy3d::Vec3 value = easy3d::Quat{static_cast<float>(w),
                                                static_cast<float>(x),
                                                static_cast<float>(y),
                                                static_cast<float>(z)}
                                       .to_euler_degrees();
        return py::make_tuple(value.x, value.y, value.z);
    });
    module.def("_raise_engine_error", [](const std::string& message) {
        throw easy3d::EngineError(message);
    });
    const auto matrix_tuple = [](const easy3d::Matrix4& matrix) {
        py::tuple result(matrix.values.size());
        for (std::size_t index = 0; index < matrix.values.size(); ++index) {
            result[index] = matrix.values[index];
        }
        return result;
    };
    module.def("_camera_view_matrix",
               [matrix_tuple](const double px,
                              const double py,
                              const double pz,
                              const double qw,
                              const double qx,
                              const double qy,
                              const double qz) {
                   const easy3d::Camera camera{
                       {static_cast<float>(px),
                        static_cast<float>(py),
                        static_cast<float>(pz)},
                       {static_cast<float>(qw),
                        static_cast<float>(qx),
                        static_cast<float>(qy),
                        static_cast<float>(qz)},
                   };
                   return matrix_tuple(camera.view_matrix());
               });
    module.def("_camera_projection_matrix",
               [matrix_tuple](const double vertical_fov_degrees,
                              const double near_plane,
                              const double far_plane,
                              const double aspect_ratio,
                              const bool homogeneous_depth) {
                   easy3d::Camera camera;
                   camera.vertical_fov_degrees = static_cast<float>(vertical_fov_degrees);
                   camera.near_plane = static_cast<float>(near_plane);
                   camera.far_plane = static_cast<float>(far_plane);
                   return matrix_tuple(camera.projection_matrix(
                       static_cast<float>(aspect_ratio), homogeneous_depth));
               });
    module.def("_camera_look_at",
               [](const double px,
                  const double py,
                  const double pz,
                  const double tx,
                  const double ty,
                  const double tz,
                  const double ux,
                  const double uy,
                  const double uz) {
                   const easy3d::Camera camera = easy3d::Camera::look_at(
                       {static_cast<float>(px),
                        static_cast<float>(py),
                        static_cast<float>(pz)},
                       {static_cast<float>(tx),
                        static_cast<float>(ty),
                        static_cast<float>(tz)},
                       {static_cast<float>(ux),
                        static_cast<float>(uy),
                        static_cast<float>(uz)});
                   return py::make_tuple(camera.rotation.w,
                                         camera.rotation.x,
                                         camera.rotation.y,
                                         camera.rotation.z);
               });
    module.def("_camera_aspect_ratio", &easy3d::Camera::aspect_ratio);

    const auto render_kind = [](const std::string& value) {
        if (value == "cube") {
            return easy3d::RenderKind::Cube;
        }
        if (value == "plane") {
            return easy3d::RenderKind::Plane;
        }
        if (value == "sphere") {
            return easy3d::RenderKind::Sphere;
        }
        throw std::invalid_argument("render kind must be cube, plane, or sphere");
    };
    const auto render_kind_name = [](const easy3d::RenderKind value) {
        switch (value) {
        case easy3d::RenderKind::Cube: return "cube";
        case easy3d::RenderKind::Plane: return "plane";
        case easy3d::RenderKind::Sphere: return "sphere";
        case easy3d::RenderKind::Model: return "model";
        }
        return "unknown";
    };
    const auto light_kind = [](const std::string& value) {
        if (value == "ambient") {
            return easy3d::LightKind::Ambient;
        }
        if (value == "directional") {
            return easy3d::LightKind::Directional;
        }
        throw std::invalid_argument("light kind must be ambient or directional");
    };
    const auto light_kind_name = [](const easy3d::LightKind value) {
        switch (value) {
        case easy3d::LightKind::Ambient: return "ambient";
        case easy3d::LightKind::Directional: return "directional";
        }
        return "unknown";
    };

    py::class_<easy3d::Engine>(module, "Engine")
        .def(py::init([](std::string title,
                         const std::uint32_t width,
                         const std::uint32_t height,
                         const bool vsync,
                         const double fps_limit) {
                 return std::make_unique<easy3d::Engine>(easy3d::EngineConfig{
                     std::move(title), width, height, vsync, fps_limit});
             }),
             py::arg("title") = "Easy3D",
             py::arg("width") = 1280,
             py::arg("height") = 720,
             py::arg("vsync") = true,
             py::arg("fps_limit") = 0.0)
        .def("run", &easy3d::Engine::run, py::call_guard<py::gil_scoped_release>())
        .def("stop", &easy3d::Engine::stop)
        .def("set_scene",
             [](easy3d::Engine& engine, easy3d::Scene* scene) {
                 engine.set_scene(scene);
             },
             py::arg("scene") = nullptr)
        .def_property_readonly("is_running", &easy3d::Engine::is_running)
        .def_property_readonly("frame_count", &easy3d::Engine::frame_count)
        .def_property_readonly("last_frame_seconds", &easy3d::Engine::last_frame_seconds)
        .def_property_readonly("renderer_stats", [](const easy3d::Engine& engine) {
            const easy3d::RendererStats stats = engine.renderer_stats();
            return py::make_tuple(stats.draw_calls,
                                  stats.visible_instances,
                                  stats.culled_instances,
                                  stats.instanced_draw_calls);
        });

    py::class_<easy3d::EntityHandle>(module, "EntityHandle")
        .def_property_readonly("world_id",
                               [](const easy3d::EntityHandle& handle) {
                                   return handle.world_id;
                               })
        .def_property_readonly("index",
                               [](const easy3d::EntityHandle& handle) { return handle.index; })
        .def_property_readonly("generation",
                               [](const easy3d::EntityHandle& handle) {
                                   return handle.generation;
                               })
        .def_property_readonly("id", &easy3d::EntityHandle::id)
        .def_property_readonly("valid", &easy3d::EntityHandle::valid)
        .def("__repr__", [](const easy3d::EntityHandle& handle) {
            return "EntityHandle(world_id=" + std::to_string(handle.world_id) +
                   ", index=" + std::to_string(handle.index) +
                   ", generation=" + std::to_string(handle.generation) + ")";
        })
        .def(py::self == py::self);

    py::class_<easy3d::Scene>(module, "_NativeScene")
        .def(py::init<std::string>(), py::arg("name") = "Scene")
        .def_property("name", &easy3d::Scene::name, &easy3d::Scene::set_name)
        .def_property("active", &easy3d::Scene::active, &easy3d::Scene::set_active)
        .def_property_readonly("world_id",
                               [](const easy3d::Scene& scene) { return scene.world().id(); })
        .def_property_readonly("entity_count", &easy3d::Scene::entity_count)
        .def("create_entity", &easy3d::Scene::create_entity, py::arg("name") = "Entity")
        .def("destroy_entity", &easy3d::Scene::destroy_entity, py::arg("handle"))
        .def("clear", &easy3d::Scene::clear)
        .def("is_alive", &easy3d::Scene::is_alive, py::arg("handle"))
        .def("entity_handles", &easy3d::Scene::entity_handles)
        .def("entity_name", &easy3d::Scene::entity_name, py::arg("handle"))
        .def("set_entity_name",
             &easy3d::Scene::set_entity_name,
             py::arg("handle"),
             py::arg("name"))
        .def("entity_enabled", &easy3d::Scene::entity_enabled, py::arg("handle"))
        .def("set_entity_enabled",
             &easy3d::Scene::set_entity_enabled,
             py::arg("handle"),
             py::arg("enabled"))
        .def("entity_visible", &easy3d::Scene::entity_visible, py::arg("handle"))
        .def("set_entity_visible",
             &easy3d::Scene::set_entity_visible,
             py::arg("handle"),
             py::arg("visible"))
        .def("entity_local_position", [](const easy3d::Scene& scene,
                                           const easy3d::EntityHandle handle) {
            const easy3d::Vec3 value = scene.local_transform(handle).position;
            return py::make_tuple(value.x, value.y, value.z);
        })
        .def("set_entity_local_position", [](easy3d::Scene& scene,
                                               const easy3d::EntityHandle handle,
                                               const double x,
                                               const double y,
                                               const double z) {
            easy3d::Transform transform = scene.local_transform(handle);
            transform.position = {static_cast<float>(x),
                                  static_cast<float>(y),
                                  static_cast<float>(z)};
            scene.set_local_transform(handle, transform);
        })
        .def("entity_local_rotation", [](const easy3d::Scene& scene,
                                           const easy3d::EntityHandle handle) {
            const easy3d::Quat value = scene.local_transform(handle).rotation;
            return py::make_tuple(value.w, value.x, value.y, value.z);
        })
        .def("set_entity_local_rotation", [](easy3d::Scene& scene,
                                               const easy3d::EntityHandle handle,
                                               const double w,
                                               const double x,
                                               const double y,
                                               const double z) {
            easy3d::Transform transform = scene.local_transform(handle);
            transform.rotation = {static_cast<float>(w),
                                  static_cast<float>(x),
                                  static_cast<float>(y),
                                  static_cast<float>(z)};
            scene.set_local_transform(handle, transform);
        })
        .def("entity_local_scale", [](const easy3d::Scene& scene,
                                        const easy3d::EntityHandle handle) {
            const easy3d::Vec3 value = scene.local_transform(handle).scale;
            return py::make_tuple(value.x, value.y, value.z);
        })
        .def("set_entity_local_scale", [](easy3d::Scene& scene,
                                            const easy3d::EntityHandle handle,
                                            const double x,
                                            const double y,
                                            const double z) {
            easy3d::Transform transform = scene.local_transform(handle);
            transform.scale = {static_cast<float>(x),
                               static_cast<float>(y),
                               static_cast<float>(z)};
            scene.set_local_transform(handle, transform);
        })
        .def("entity_world_transform", [](const easy3d::Scene& scene,
                                            const easy3d::EntityHandle handle) {
            const easy3d::Transform transform = scene.world_transform(handle);
            return py::make_tuple(
                py::make_tuple(transform.position.x,
                               transform.position.y,
                               transform.position.z),
                py::make_tuple(transform.rotation.w,
                               transform.rotation.x,
                               transform.rotation.y,
                               transform.rotation.z),
                py::make_tuple(transform.scale.x, transform.scale.y, transform.scale.z));
        })
        .def("entity_parent", &easy3d::Scene::entity_parent, py::arg("handle"))
        .def("entity_children", &easy3d::Scene::entity_children, py::arg("handle"))
        .def("set_entity_parent",
             &easy3d::Scene::set_entity_parent,
             py::arg("child"),
             py::arg("parent") = std::nullopt,
             py::arg("keep_world") = false)
        .def("add_primitive_renderer",
             [render_kind](easy3d::Scene& scene,
                           const easy3d::EntityHandle handle,
                           const std::string& kind,
                           const std::array<float, 4>& color,
                           const std::optional<std::string>& texture) {
                 scene.add_primitive_renderer(
                     handle,
                     render_kind(kind),
                     {color[0], color[1], color[2], color[3]},
                     texture.has_value()
                         ? std::optional<std::filesystem::path>(*texture)
                         : std::nullopt);
             },
             py::arg("handle"),
             py::arg("kind"),
             py::arg("color"),
             py::arg("texture") = std::nullopt)
        .def("add_model_renderer",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::string& path,
                const std::array<float, 4>& color) {
                 scene.add_model_renderer(
                     handle, path, {color[0], color[1], color[2], color[3]});
             },
             py::arg("handle"),
             py::arg("path"),
             py::arg("color"))
        .def("has_render_component", &easy3d::Scene::has_render_component)
        .def("render_component_info",
             [render_kind_name](const easy3d::Scene& scene,
                                const easy3d::EntityHandle handle) {
                 const easy3d::RenderComponent& component =
                     scene.render_component(handle);
                 py::object asset = py::none();
                 if (component.model) {
                     asset = py::cast(component.model->source_path.string());
                 } else if (component.texture) {
                     asset = py::cast(component.texture->source_path.string());
                 }
                 return py::make_tuple(
                     render_kind_name(component.kind),
                     py::make_tuple(component.material.color.r,
                                    component.material.color.g,
                                    component.material.color.b,
                                    component.material.color.a),
                     asset,
                     component.material.lit);
             },
             py::arg("handle"))
        .def("set_render_color",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::array<float, 4>& color) {
                 scene.set_render_color(
                     handle, {color[0], color[1], color[2], color[3]});
             },
             py::arg("handle"),
             py::arg("color"))
        .def("set_render_lit",
             &easy3d::Scene::set_render_lit,
             py::arg("handle"),
             py::arg("lit"))
        .def("remove_render_component", &easy3d::Scene::remove_render_component)
        .def("add_light_component",
             [light_kind](easy3d::Scene& scene,
                          const easy3d::EntityHandle handle,
                          const std::string& kind,
                          const std::array<float, 4>& color,
                          const float intensity) {
                 scene.add_light_component(
                     handle,
                     light_kind(kind),
                     {color[0], color[1], color[2], color[3]},
                     intensity);
             },
             py::arg("handle"),
             py::arg("kind"),
             py::arg("color"),
             py::arg("intensity"))
        .def("has_light_component", &easy3d::Scene::has_light_component)
        .def("light_component_info",
             [light_kind_name](const easy3d::Scene& scene,
                               const easy3d::EntityHandle handle) {
                 const easy3d::LightComponent& component =
                     scene.light_component(handle);
                 return py::make_tuple(
                     light_kind_name(component.kind),
                     py::make_tuple(component.color.r,
                                    component.color.g,
                                    component.color.b,
                                    component.color.a),
                     component.intensity);
             },
             py::arg("handle"))
        .def("set_light_color",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::array<float, 4>& color) {
                 scene.set_light_color(
                     handle, {color[0], color[1], color[2], color[3]});
             },
             py::arg("handle"),
             py::arg("color"))
        .def("set_light_intensity",
             &easy3d::Scene::set_light_intensity,
             py::arg("handle"),
             py::arg("intensity"))
        .def("remove_light_component", &easy3d::Scene::remove_light_component)
        .def("camera_info", [](const easy3d::Scene& scene) {
            const easy3d::Camera& camera = scene.camera();
            return py::make_tuple(
                py::make_tuple(camera.position.x,
                               camera.position.y,
                               camera.position.z),
                py::make_tuple(camera.rotation.w,
                               camera.rotation.x,
                               camera.rotation.y,
                               camera.rotation.z),
                camera.vertical_fov_degrees,
                camera.near_plane,
                camera.far_plane);
        })
        .def("set_camera",
             [](easy3d::Scene& scene,
                const std::array<float, 3>& position,
                const std::array<float, 4>& rotation,
                const float vertical_fov_degrees,
                const float near_plane,
                const float far_plane) {
                 scene.set_camera({{position[0], position[1], position[2]},
                                   {rotation[0], rotation[1], rotation[2], rotation[3]},
                                   vertical_fov_degrees,
                                   near_plane,
                                   far_plane});
             },
             py::arg("position"),
             py::arg("rotation"),
             py::arg("vertical_fov_degrees"),
             py::arg("near_plane"),
             py::arg("far_plane"))
        .def("add_debug_line",
             [](easy3d::Scene& scene,
                const std::array<float, 3>& start,
                const std::array<float, 3>& end,
                const std::array<float, 4>& color,
                const bool depth_test) {
                 scene.add_debug_line({{start[0], start[1], start[2]},
                                       {end[0], end[1], end[2]},
                                       {color[0], color[1], color[2], color[3]},
                                       depth_test});
             },
             py::arg("start"),
             py::arg("end"),
             py::arg("color"),
             py::arg("depth_test") = true)
        .def("clear_debug_lines", &easy3d::Scene::clear_debug_lines)
        .def_property_readonly("debug_line_count", [](const easy3d::Scene& scene) {
            return scene.debug_lines().size();
        });
}

