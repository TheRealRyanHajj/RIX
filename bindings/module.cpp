#include "easy3d/core.hpp"
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

    py::register_exception<easy3d::EngineError>(module, "EngineError");
    py::register_exception<easy3d::InvalidEntityError>(
        module, "InvalidEntityError", PyExc_ReferenceError);

    module.def("engine_version", &easy3d::engine_version);
    module.def("native_add", &easy3d::native_add, py::arg("a"), py::arg("b"));
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
        .def_property_readonly("is_running", &easy3d::Engine::is_running)
        .def_property_readonly("frame_count", &easy3d::Engine::frame_count)
        .def_property_readonly("last_frame_seconds", &easy3d::Engine::last_frame_seconds);

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
             py::arg("keep_world") = false);
}

