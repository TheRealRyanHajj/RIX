#include "easy3d/core.hpp"
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
    module.def("_raise_engine_error", [](const std::string& message) {
        throw easy3d::EngineError(message);
    });

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
             py::arg("visible"));
}

