#include "easy3d/core.hpp"
#include "easy3d/assets.hpp"
#include "easy3d/network.hpp"
#include "easy3d/physics.hpp"
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
    py::register_exception<easy3d::PhysicsError>(module, "PhysicsError", engine_error.ptr());
    py::register_exception<easy3d::NetworkError>(module, "NetworkError", engine_error.ptr());

    module.def("engine_version", &easy3d::engine_version);
    module.def("native_add", &easy3d::native_add, py::arg("a"), py::arg("b"));
    const auto network_delivery = [](const std::string& value) {
        if (value == "reliable") {
            return easy3d::NetworkDelivery::Reliable;
        }
        if (value == "unreliable") {
            return easy3d::NetworkDelivery::Unreliable;
        }
        throw std::invalid_argument("network delivery must be 'reliable' or 'unreliable'");
    };
    const auto network_delivery_name = [](const easy3d::NetworkDelivery value) {
        return value == easy3d::NetworkDelivery::Reliable ? "reliable" : "unreliable";
    };
    const auto send_status_name = [](const easy3d::SendStatus value) {
        switch (value) {
        case easy3d::SendStatus::Queued:
            return "queued";
        case easy3d::SendStatus::InvalidConnection:
            return "invalid_connection";
        case easy3d::SendStatus::MessageTooLarge:
            return "message_too_large";
        case easy3d::SendStatus::QueueFull:
            return "queue_full";
        }
        return "invalid_connection";
    };
    const auto event_type_name = [](const easy3d::TransportEventType value) {
        switch (value) {
        case easy3d::TransportEventType::Connected:
            return "connected";
        case easy3d::TransportEventType::Disconnected:
            return "disconnected";
        case easy3d::TransportEventType::Message:
            return "message";
        }
        return "message";
    };
    const auto client_state_name = [](const easy3d::NetworkClientState value) {
        switch (value) {
        case easy3d::NetworkClientState::Disconnected:
            return "disconnected";
        case easy3d::NetworkClientState::Connecting:
            return "connecting";
        case easy3d::NetworkClientState::Handshaking:
            return "handshaking";
        case easy3d::NetworkClientState::Connected:
            return "connected";
        }
        return "disconnected";
    };
    const auto server_state_name = [](const easy3d::NetworkServerState value) {
        switch (value) {
        case easy3d::NetworkServerState::Stopped:
            return "stopped";
        case easy3d::NetworkServerState::Listening:
            return "listening";
        }
        return "stopped";
    };
    const auto transport_event_tuple =
        [network_delivery_name, event_type_name](const easy3d::TransportEvent& event) {
            return py::make_tuple(
                event_type_name(event.type),
                event.connection.value,
                network_delivery_name(event.delivery),
                py::bytes(reinterpret_cast<const char*>(event.payload.data()),
                          event.payload.size()),
                event.reason,
                event.sequence,
                event.disconnect_code);
        };
    const auto transport_stats_tuple = [](const easy3d::TransportStats& value) {
        return py::make_tuple(value.messages_sent,
                              value.messages_received,
                              value.messages_lost,
                              value.bytes_sent,
                              value.bytes_received,
                              value.queue_rejections,
                              value.event_overflows);
    };
    module.def("_network_backend_info", []() {
        const easy3d::NetworkBackendInfo info = easy3d::network_backend_info();
        return py::make_tuple(
            info.available, info.name, info.version, info.crypto_provider);
    });
    module.def("_network_backend_smoke_test", []() {
        easy3d::NetworkBackendRuntime runtime;
        return runtime.ready() && runtime.loopback_smoke_test();
    });
    py::class_<easy3d::SimulatedNetwork>(module, "_NetworkSimulator")
        .def(py::init([](const double latency_seconds,
                         const double jitter_seconds,
                         const double loss_probability,
                         const std::uint64_t random_seed,
                         const std::size_t in_flight_capacity,
                         const std::size_t event_queue_capacity,
                         const std::size_t maximum_message_size) {
                 return std::make_unique<easy3d::SimulatedNetwork>(
                     easy3d::SimulatedNetworkConfig{latency_seconds,
                                                    jitter_seconds,
                                                    loss_probability,
                                                    random_seed,
                                                    in_flight_capacity,
                                                    event_queue_capacity,
                                                    maximum_message_size});
             }),
             py::arg("latency_seconds") = 0.0,
             py::arg("jitter_seconds") = 0.0,
             py::arg("loss_probability") = 0.0,
             py::arg("random_seed") = 1,
             py::arg("in_flight_capacity") = 1024,
             py::arg("event_queue_capacity") = 1024,
             py::arg("maximum_message_size") = 64 * 1024)
        .def_property_readonly("first_connection", [](easy3d::SimulatedNetwork& network) {
            return network.first().connection().value;
        })
        .def_property_readonly("second_connection", [](easy3d::SimulatedNetwork& network) {
            return network.second().connection().value;
        })
        .def("send",
             [network_delivery, send_status_name](easy3d::SimulatedNetwork& network,
                                                  const bool first,
                                                  const std::uint64_t connection,
                                                  const py::bytes& data,
                                                  const std::string& delivery) {
                 char* value = nullptr;
                 py::ssize_t size = 0;
                 if (PyBytes_AsStringAndSize(data.ptr(), &value, &size) != 0) {
                     throw py::error_already_set();
                 }
                 easy3d::SimulatedNetwork::Endpoint& endpoint =
                     first ? network.first() : network.second();
                 const auto payload = std::span{
                     reinterpret_cast<const std::uint8_t*>(value),
                     static_cast<std::size_t>(size)};
                 return send_status_name(endpoint.send(easy3d::ConnectionId{connection},
                                                       payload,
                                                       network_delivery(delivery)));
             },
             py::arg("first"),
             py::arg("connection"),
             py::arg("data"),
             py::arg("delivery"))
        .def("disconnect",
             [](easy3d::SimulatedNetwork& network,
                const bool first,
                const std::uint64_t connection,
                const std::string& reason) {
                 easy3d::SimulatedNetwork::Endpoint& endpoint =
                     first ? network.first() : network.second();
                 endpoint.disconnect(easy3d::ConnectionId{connection}, reason);
             },
             py::arg("first"),
             py::arg("connection"),
             py::arg("reason") = "")
        .def("poll",
             [transport_event_tuple](easy3d::SimulatedNetwork& network,
                                     const bool first,
                                     const std::size_t maximum_events) {
                 easy3d::SimulatedNetwork::Endpoint& endpoint =
                     first ? network.first() : network.second();
                 py::list result;
                 for (easy3d::TransportEvent& event : endpoint.poll(maximum_events)) {
                     result.append(transport_event_tuple(event));
                 }
                 return result;
             },
             py::arg("first"),
             py::arg("maximum_events") = 256)
        .def("stats", [transport_stats_tuple](easy3d::SimulatedNetwork& network,
                                               const bool first) {
            const easy3d::TransportStats value =
                (first ? network.first() : network.second()).stats();
            return transport_stats_tuple(value);
        })
        .def("advance", &easy3d::SimulatedNetwork::advance, py::arg("elapsed_seconds"))
        .def_property_readonly("time_seconds", &easy3d::SimulatedNetwork::time_seconds)
        .def_property_readonly("in_flight_count",
                               &easy3d::SimulatedNetwork::in_flight_count);
    py::class_<easy3d::NetworkClient>(module, "_NetworkClient")
        .def(py::init([](const double connection_timeout_seconds,
                         const double peer_timeout_seconds,
                         const std::size_t event_queue_capacity,
                         const std::size_t maximum_message_size,
                         const std::uint16_t protocol_version,
                         const std::uint32_t schema_version) {
                 return std::make_unique<easy3d::NetworkClient>(
                     easy3d::NetworkClientConfig{connection_timeout_seconds,
                                                 peer_timeout_seconds,
                                                 event_queue_capacity,
                                                 maximum_message_size,
                                                 protocol_version,
                                                 schema_version});
             }),
             py::arg("connection_timeout_seconds") = 5.0,
             py::arg("peer_timeout_seconds") = 10.0,
             py::arg("event_queue_capacity") = 1024,
             py::arg("maximum_message_size") = 64 * 1024,
             py::arg("protocol_version") = 1,
             py::arg("schema_version") = 1)
        .def("connect", &easy3d::NetworkClient::connect, py::arg("address"), py::arg("port"))
        .def("send",
             [network_delivery, send_status_name](easy3d::NetworkClient& client,
                                                  const std::uint64_t connection,
                                                  const py::bytes& data,
                                                  const std::string& delivery) {
                 char* value = nullptr;
                 py::ssize_t size = 0;
                 if (PyBytes_AsStringAndSize(data.ptr(), &value, &size) != 0) {
                     throw py::error_already_set();
                 }
                 return send_status_name(client.send(
                     easy3d::ConnectionId{connection},
                     std::span{reinterpret_cast<const std::uint8_t*>(value),
                               static_cast<std::size_t>(size)},
                     network_delivery(delivery)));
             },
             py::arg("connection"),
             py::arg("data"),
             py::arg("delivery"))
        .def("disconnect",
             [](easy3d::NetworkClient& client,
                const std::uint64_t connection,
                const std::string& reason) {
                 client.disconnect(easy3d::ConnectionId{connection}, reason);
             },
             py::arg("connection"),
             py::arg("reason") = "")
        .def("poll",
             [transport_event_tuple](easy3d::NetworkClient& client,
                                     const std::size_t maximum_events) {
                 const std::vector<easy3d::TransportEvent> events =
                     client.poll(maximum_events);
                 py::list result;
                 for (const easy3d::TransportEvent& event : events) {
                     result.append(transport_event_tuple(event));
                 }
                 return result;
             },
             py::arg("maximum_events") = 256)
        .def_property_readonly("connection", [](const easy3d::NetworkClient& client) {
            return client.connection().value;
        })
        .def_property_readonly("state", [client_state_name](const easy3d::NetworkClient& client) {
            return client_state_name(client.state());
        })
        .def_property_readonly("remote_address", &easy3d::NetworkClient::remote_address)
        .def_property_readonly("stats", [transport_stats_tuple](const easy3d::NetworkClient& client) {
            return transport_stats_tuple(client.stats());
        })
        .def_property_readonly(
            "metrics",
            [client_state_name, transport_stats_tuple](const easy3d::NetworkClient& client) {
                const easy3d::NetworkConnectionMetrics value = client.metrics();
                return py::make_tuple(client_state_name(value.state),
                                      value.ping_milliseconds,
                                      value.outgoing_bytes_per_second,
                                      value.incoming_bytes_per_second,
                                      value.pending_reliable_bytes,
                                      value.pending_unreliable_bytes,
                                      value.negotiated_maximum_message_size,
                                      transport_stats_tuple(value.transport));
            });
    py::class_<easy3d::NetworkServer>(module, "_NetworkServer")
        .def(py::init([](std::string bind_address,
                         const std::uint16_t port,
                         const std::size_t maximum_connections,
                         const double handshake_timeout_seconds,
                         const double peer_timeout_seconds,
                         const std::size_t event_queue_capacity,
                         const std::size_t maximum_message_size,
                         const std::uint16_t protocol_version,
                         const std::uint32_t schema_version) {
                 return std::make_unique<easy3d::NetworkServer>(
                     easy3d::NetworkServerConfig{std::move(bind_address),
                                                 port,
                                                 maximum_connections,
                                                 handshake_timeout_seconds,
                                                 peer_timeout_seconds,
                                                 event_queue_capacity,
                                                 maximum_message_size,
                                                 protocol_version,
                                                 schema_version});
             }),
             py::arg("bind_address") = "0.0.0.0",
             py::arg("port") = 7777,
             py::arg("maximum_connections") = 32,
             py::arg("handshake_timeout_seconds") = 5.0,
             py::arg("peer_timeout_seconds") = 10.0,
             py::arg("event_queue_capacity") = 4096,
             py::arg("maximum_message_size") = 64 * 1024,
             py::arg("protocol_version") = 1,
             py::arg("schema_version") = 1)
        .def("start", &easy3d::NetworkServer::start)
        .def("stop", &easy3d::NetworkServer::stop, py::arg("reason") = "server stopped")
        .def("send",
             [network_delivery, send_status_name](easy3d::NetworkServer& server,
                                                  const std::uint64_t connection,
                                                  const py::bytes& data,
                                                  const std::string& delivery) {
                 char* value = nullptr;
                 py::ssize_t size = 0;
                 if (PyBytes_AsStringAndSize(data.ptr(), &value, &size) != 0) {
                     throw py::error_already_set();
                 }
                 return send_status_name(server.send(
                     easy3d::ConnectionId{connection},
                     std::span{reinterpret_cast<const std::uint8_t*>(value),
                               static_cast<std::size_t>(size)},
                     network_delivery(delivery)));
             },
             py::arg("connection"),
             py::arg("data"),
             py::arg("delivery"))
        .def("disconnect",
             [](easy3d::NetworkServer& server,
                const std::uint64_t connection,
                const std::string& reason) {
                 server.disconnect(easy3d::ConnectionId{connection}, reason);
             },
             py::arg("connection"),
             py::arg("reason") = "")
        .def("poll",
             [transport_event_tuple](easy3d::NetworkServer& server,
                                     const std::size_t maximum_events) {
                 py::list result;
                 for (const easy3d::TransportEvent& event :
                      server.poll(maximum_events)) {
                     result.append(transport_event_tuple(event));
                 }
                 return result;
             },
             py::arg("maximum_events") = 256)
        .def_property_readonly("state", [server_state_name](
                                             const easy3d::NetworkServer& server) {
            return server_state_name(server.state());
        })
        .def_property_readonly("port", &easy3d::NetworkServer::port)
        .def_property_readonly("bind_address", &easy3d::NetworkServer::bind_address)
        .def_property_readonly("connections", [](const easy3d::NetworkServer& server) {
            const std::vector<easy3d::ConnectionId> connections =
                server.connections();
            py::tuple result(connections.size());
            std::size_t index = 0;
            for (const easy3d::ConnectionId connection : connections) {
                result[index++] = connection.value;
            }
            return result;
        })
        .def_property_readonly("stats", [transport_stats_tuple](
                                             const easy3d::NetworkServer& server) {
            return transport_stats_tuple(server.stats());
        });
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
                              const bool orthographic,
                              const double orthographic_height,
                              const double aspect_ratio,
                              const bool homogeneous_depth) {
                   easy3d::Camera camera;
                   camera.vertical_fov_degrees = static_cast<float>(vertical_fov_degrees);
                   camera.near_plane = static_cast<float>(near_plane);
                   camera.far_plane = static_cast<float>(far_plane);
                   camera.projection = orthographic
                                           ? easy3d::CameraProjection::Orthographic
                                           : easy3d::CameraProjection::Perspective;
                   camera.orthographic_height = static_cast<float>(orthographic_height);
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
    const auto physics_shape = [](const std::string& value) {
        if (value == "box") return easy3d::PhysicsShape::Box;
        if (value == "sphere") return easy3d::PhysicsShape::Sphere;
        if (value == "capsule") return easy3d::PhysicsShape::Capsule;
        if (value == "convex") return easy3d::PhysicsShape::ConvexHull;
        if (value == "mesh") return easy3d::PhysicsShape::TriangleMesh;
        throw std::invalid_argument(
            "collider shape must be box, sphere, capsule, convex, or mesh");
    };
    const auto physics_shape_name = [](const easy3d::PhysicsShape value) {
        switch (value) {
        case easy3d::PhysicsShape::Box: return "box";
        case easy3d::PhysicsShape::Sphere: return "sphere";
        case easy3d::PhysicsShape::Capsule: return "capsule";
        case easy3d::PhysicsShape::ConvexHull: return "convex";
        case easy3d::PhysicsShape::TriangleMesh: return "mesh";
        }
        return "unknown";
    };
    const auto collision_layer = [](const std::string& value) {
        if (value == "static") return easy3d::CollisionLayer::Static;
        if (value == "dynamic") return easy3d::CollisionLayer::Dynamic;
        if (value == "sensor") return easy3d::CollisionLayer::Sensor;
        if (value == "character") return easy3d::CollisionLayer::Character;
        throw std::invalid_argument(
            "collision layer must be static, dynamic, sensor, or character");
    };
    const auto collision_layer_name = [](const easy3d::CollisionLayer value) {
        switch (value) {
        case easy3d::CollisionLayer::Static: return "static";
        case easy3d::CollisionLayer::Dynamic: return "dynamic";
        case easy3d::CollisionLayer::Sensor: return "sensor";
        case easy3d::CollisionLayer::Character: return "character";
        }
        return "unknown";
    };
    const auto motion_type = [](const std::string& value) {
        if (value == "kinematic") return easy3d::PhysicsMotionType::Kinematic;
        if (value == "dynamic") return easy3d::PhysicsMotionType::Dynamic;
        throw std::invalid_argument("rigid body type must be dynamic or kinematic");
    };
    const auto motion_type_name = [](const easy3d::PhysicsMotionType value) {
        switch (value) {
        case easy3d::PhysicsMotionType::Static: return "static";
        case easy3d::PhysicsMotionType::Kinematic: return "kinematic";
        case easy3d::PhysicsMotionType::Dynamic: return "dynamic";
        }
        return "unknown";
    };
    const auto contact_phase_name = [](const easy3d::PhysicsContactPhase value) {
        switch (value) {
        case easy3d::PhysicsContactPhase::Enter: return "enter";
        case easy3d::PhysicsContactPhase::Stay: return "stay";
        case easy3d::PhysicsContactPhase::Exit: return "exit";
        }
        return "unknown";
    };

    py::class_<easy3d::InputSystem>(module, "_NativeInput")
        .def("bind_action",
             [](easy3d::InputSystem& input,
                std::string action,
                const std::vector<std::tuple<std::string, float, float>>& values,
                const bool replace) {
                 std::vector<easy3d::InputBinding> bindings;
                 bindings.reserve(values.size());
                 for (const auto& [control, scale, deadzone] : values) {
                     bindings.push_back({control, scale, deadzone});
                 }
                 input.bind_action(std::move(action), std::move(bindings), replace);
             },
             py::arg("action"),
             py::arg("bindings"),
             py::arg("replace") = true)
        .def("unbind_action", &easy3d::InputSystem::unbind_action)
        .def("clear_actions", &easy3d::InputSystem::clear_actions)
        .def("action_state", [](const easy3d::InputSystem& input,
                                const std::string& action) {
            const easy3d::InputActionState state = input.action_state(action);
            return py::make_tuple(
                state.value, state.down, state.pressed, state.released);
        })
        .def("action_bindings", [](const easy3d::InputSystem& input,
                                   const std::string& action) {
            py::list result;
            for (const easy3d::InputBinding& binding : input.action_bindings(action)) {
                result.append(py::make_tuple(
                    binding.control, binding.scale, binding.deadzone));
            }
            return result;
        })
        .def("control_value", &easy3d::InputSystem::control_value)
        .def_property_readonly("pointer_state", [](const easy3d::InputSystem& input) {
            const easy3d::PointerState state = input.pointer_state();
            return py::make_tuple(state.x,
                                  state.y,
                                  state.delta_x,
                                  state.delta_y,
                                  state.wheel_x,
                                  state.wheel_y);
        })
        .def_property_readonly("focused", &easy3d::InputSystem::focused)
        .def_property("pointer_lock_requested",
                      &easy3d::InputSystem::pointer_lock_requested,
                      &easy3d::InputSystem::request_pointer_lock)
        .def_property_readonly("pointer_lock_active",
                               &easy3d::InputSystem::pointer_lock_active)
        .def_property_readonly("gamepad_connected",
                               &easy3d::InputSystem::gamepad_connected)
        .def_property_readonly("gamepad_name", &easy3d::InputSystem::gamepad_name)
        .def_property_readonly("action_count", &easy3d::InputSystem::action_count);

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
        .def("run",
             [](easy3d::Engine& engine, const py::object& callback) {
                 easy3d::Engine::FrameCallback frame_callback;
                 if (!callback.is_none()) {
                     if (PyCallable_Check(callback.ptr()) == 0) {
                         throw py::type_error("frame_callback must be callable or None");
                     }
                     // The binding argument owns this object until engine.run returns. Capturing
                     // only its borrowed pointer prevents a Python refcount decrement when the
                     // native std::function is destroyed while the GIL is released.
                     PyObject* const callback_ptr = callback.ptr();
                     frame_callback = [callback_ptr](const double delta_seconds) {
                         py::gil_scoped_acquire acquire;
                         py::reinterpret_borrow<py::function>(callback_ptr)(delta_seconds);
                     };
                 }
                 py::gil_scoped_release release;
                 engine.run(std::move(frame_callback));
             },
             py::arg("frame_callback") = py::none())
        .def("stop", &easy3d::Engine::stop)
        .def("set_scene",
             [](easy3d::Engine& engine, easy3d::Scene* scene) {
                 engine.set_scene(scene);
             },
             py::arg("scene") = nullptr)
        .def_property_readonly("is_running", &easy3d::Engine::is_running)
        .def_property_readonly("frame_count", &easy3d::Engine::frame_count)
        .def_property_readonly("last_frame_seconds", &easy3d::Engine::last_frame_seconds)
        .def_property_readonly(
            "input",
            static_cast<easy3d::InputSystem& (easy3d::Engine::*)() noexcept>(
                &easy3d::Engine::input),
            py::return_value_policy::reference_internal)
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

    py::class_<easy3d::PhysicsConstraintHandle>(module, "_PhysicsConstraintHandle")
        .def_property_readonly("id", &easy3d::PhysicsConstraintHandle::id)
        .def_property_readonly("valid", &easy3d::PhysicsConstraintHandle::valid)
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
        .def("add_collider_component",
             [physics_shape, collision_layer](
                 easy3d::Scene& scene,
                 const easy3d::EntityHandle handle,
                 const std::string& shape,
                 const std::array<float, 3>& half_extents,
                 const float radius,
                 const float height,
                 const std::vector<std::array<float, 3>>& points,
                 const std::optional<std::string>& mesh_path,
                 const bool trigger,
                 const std::string& layer,
                 const float friction,
                 const float restitution) {
                 easy3d::ColliderComponent component;
                 component.shape = physics_shape(shape);
                 component.half_extents =
                     {half_extents[0], half_extents[1], half_extents[2]};
                 component.radius = radius;
                 component.height = height;
                 component.trigger = trigger;
                 component.layer = collision_layer(layer);
                 component.material = {friction, restitution};
                 component.vertices.reserve(points.size());
                 for (const auto& point : points) {
                     component.vertices.push_back({point[0], point[1], point[2]});
                 }
                 if (mesh_path.has_value()) {
                     const std::shared_ptr<const easy3d::ModelData> model =
                         easy3d::load_obj(*mesh_path);
                     component.vertices.clear();
                     component.indices.clear();
                     for (const easy3d::ModelPart& part : model->parts) {
                         const std::uint32_t offset =
                             static_cast<std::uint32_t>(component.vertices.size());
                         for (const easy3d::Vertex& vertex : part.mesh.vertices) {
                             component.vertices.push_back(vertex.position);
                         }
                         for (const std::uint32_t index : part.mesh.indices) {
                             component.indices.push_back(offset + index);
                         }
                     }
                 }
                 scene.add_collider_component(handle, std::move(component));
             },
             py::arg("handle"),
             py::arg("shape"),
             py::arg("half_extents"),
             py::arg("radius"),
             py::arg("height"),
             py::arg("points"),
             py::arg("mesh_path"),
             py::arg("trigger"),
             py::arg("layer"),
             py::arg("friction"),
             py::arg("restitution"))
        .def("has_collider_component", &easy3d::Scene::has_collider_component)
        .def("collider_component_info",
             [physics_shape_name, collision_layer_name](
                 const easy3d::Scene& scene, const easy3d::EntityHandle handle) {
                 const easy3d::ColliderComponent& component =
                     scene.collider_component(handle);
                 return py::make_tuple(
                     physics_shape_name(component.shape),
                     py::make_tuple(component.half_extents.x,
                                    component.half_extents.y,
                                    component.half_extents.z),
                     component.radius,
                     component.height,
                     component.trigger,
                     collision_layer_name(component.layer),
                     component.material.friction,
                     component.material.restitution);
             },
             py::arg("handle"))
        .def("remove_collider_component", &easy3d::Scene::remove_collider_component)
        .def("add_rigid_body_component",
             [motion_type](easy3d::Scene& scene,
                           const easy3d::EntityHandle handle,
                           const std::string& type,
                           const float mass,
                           const bool use_gravity,
                           const bool continuous) {
                 scene.add_rigid_body_component(handle,
                                                {motion_type(type),
                                                 mass,
                                                 use_gravity,
                                                 continuous});
             },
             py::arg("handle"),
             py::arg("type"),
             py::arg("mass"),
             py::arg("use_gravity"),
             py::arg("continuous"))
        .def("has_rigid_body_component", &easy3d::Scene::has_rigid_body_component)
        .def("rigid_body_component_info",
             [motion_type_name](const easy3d::Scene& scene,
                                const easy3d::EntityHandle handle) {
                 const easy3d::RigidBodyComponent& component =
                     scene.rigid_body_component(handle);
                 return py::make_tuple(motion_type_name(component.motion_type),
                                       component.mass,
                                       component.use_gravity,
                                       component.continuous);
             },
             py::arg("handle"))
        .def("remove_rigid_body_component", &easy3d::Scene::remove_rigid_body_component)
        .def("rigid_body_linear_velocity",
             [](const easy3d::Scene& scene, const easy3d::EntityHandle handle) {
                 const easy3d::Vec3 value = scene.rigid_body_linear_velocity(handle);
                 return py::make_tuple(value.x, value.y, value.z);
             },
             py::arg("handle"))
        .def("set_rigid_body_linear_velocity",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::array<float, 3>& velocity) {
                 scene.set_rigid_body_linear_velocity(
                     handle, {velocity[0], velocity[1], velocity[2]});
             },
             py::arg("handle"),
             py::arg("velocity"))
        .def("add_rigid_body_force",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::array<float, 3>& force) {
                 scene.add_rigid_body_force(handle, {force[0], force[1], force[2]});
             },
             py::arg("handle"),
             py::arg("force"))
        .def("add_rigid_body_impulse",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::array<float, 3>& impulse) {
                 scene.add_rigid_body_impulse(
                     handle, {impulse[0], impulse[1], impulse[2]});
             },
             py::arg("handle"),
             py::arg("impulse"))
        .def("teleport_rigid_body",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::array<float, 3>& position,
                const std::array<float, 4>& rotation) {
                 scene.teleport_rigid_body(
                     handle,
                     {position[0], position[1], position[2]},
                     {rotation[0], rotation[1], rotation[2], rotation[3]});
             },
             py::arg("handle"),
             py::arg("position"),
             py::arg("rotation"))
        .def("add_character_controller_component",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::string& mode,
                const float radius,
                const float height,
                const float speed,
                const float acceleration,
                const float air_control,
                const float jump_speed,
                const float max_slope_degrees,
                const float step_height) {
                 easy3d::CharacterMotorMode native_mode;
                 if (mode == "first_person") {
                     native_mode = easy3d::CharacterMotorMode::FirstPerson;
                 } else if (mode == "third_person") {
                     native_mode = easy3d::CharacterMotorMode::ThirdPerson;
                 } else {
                     throw std::invalid_argument(
                         "character mode must be 'first_person' or 'third_person'");
                 }
                 scene.add_character_controller_component(
                     handle,
                     {native_mode,
                      radius,
                      height,
                      speed,
                      acceleration,
                      air_control,
                      jump_speed,
                      max_slope_degrees,
                      step_height});
             },
             py::arg("handle"),
             py::arg("mode"),
             py::arg("radius"),
             py::arg("height"),
             py::arg("speed"),
             py::arg("acceleration"),
             py::arg("air_control"),
             py::arg("jump_speed"),
             py::arg("max_slope_degrees"),
             py::arg("step_height"))
        .def("has_character_controller_component",
             &easy3d::Scene::has_character_controller_component)
        .def("character_controller_component_info",
             [](const easy3d::Scene& scene, const easy3d::EntityHandle handle) {
                 const easy3d::CharacterControllerComponent& component =
                     scene.character_controller_component(handle);
                 return py::make_tuple(
                     component.mode == easy3d::CharacterMotorMode::FirstPerson
                         ? "first_person"
                         : "third_person",
                     component.radius,
                     component.height,
                     component.speed,
                     component.acceleration,
                     component.air_control,
                     component.jump_speed,
                     component.max_slope_degrees,
                     component.step_height);
             },
             py::arg("handle"))
        .def("remove_character_controller_component",
             &easy3d::Scene::remove_character_controller_component)
        .def("set_character_input",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::array<float, 3>& movement,
                const float heading_degrees,
                const bool jump) {
                 scene.set_character_input(
                     handle,
                     {movement[0], movement[1], movement[2]},
                     heading_degrees,
                     jump);
             },
             py::arg("handle"),
             py::arg("movement"),
             py::arg("heading_degrees"),
             py::arg("jump") = false)
        .def("set_character_sequenced_input",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::uint64_t sequence,
                const std::array<float, 3>& movement,
                const float heading_degrees,
                const bool jump) {
                 scene.set_character_sequenced_input(
                     handle,
                     sequence,
                     {movement[0], movement[1], movement[2]},
                     heading_degrees,
                     jump);
             },
             py::arg("handle"),
             py::arg("sequence"),
             py::arg("movement"),
             py::arg("heading_degrees"),
             py::arg("jump") = false)
        .def("character_input_sequence",
             &easy3d::Scene::character_input_sequence,
             py::arg("handle"))
        .def("character_state",
             [](const easy3d::Scene& scene, const easy3d::EntityHandle handle) {
                 const easy3d::CharacterMotorState state = scene.character_state(handle);
                 return py::make_tuple(
                     py::make_tuple(state.position.x, state.position.y, state.position.z),
                     py::make_tuple(state.rotation.w,
                                    state.rotation.x,
                                    state.rotation.y,
                                    state.rotation.z),
                     py::make_tuple(state.linear_velocity.x,
                                    state.linear_velocity.y,
                                    state.linear_velocity.z),
                     py::make_tuple(state.ground_normal.x,
                                    state.ground_normal.y,
                                    state.ground_normal.z),
                     state.grounded);
             },
             py::arg("handle"))
        .def("teleport_character",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::array<float, 3>& position,
                const float heading_degrees) {
                 scene.teleport_character(
                     handle,
                     {position[0], position[1], position[2]},
                     heading_degrees);
             },
             py::arg("handle"),
             py::arg("position"),
             py::arg("heading_degrees") = 0.0F)
        .def("add_fixed_constraint",
             &easy3d::Scene::add_fixed_constraint,
             py::arg("first"),
             py::arg("second"))
        .def("add_distance_constraint",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle first,
                const easy3d::EntityHandle second,
                const std::array<float, 3>& first_anchor,
                const std::array<float, 3>& second_anchor,
                const float minimum_distance,
                const float maximum_distance) {
                 return scene.add_distance_constraint(
                     first,
                     second,
                     {first_anchor[0], first_anchor[1], first_anchor[2]},
                     {second_anchor[0], second_anchor[1], second_anchor[2]},
                     minimum_distance,
                     maximum_distance);
             },
             py::arg("first"),
             py::arg("second"),
             py::arg("first_anchor"),
             py::arg("second_anchor"),
             py::arg("minimum_distance") = -1.0F,
             py::arg("maximum_distance") = -1.0F)
        .def("remove_constraint", &easy3d::Scene::remove_constraint)
        .def("has_constraint", &easy3d::Scene::has_constraint)
        .def("physics_raycast_all",
             [](const easy3d::Scene& scene,
                const std::array<float, 3>& origin,
                const std::array<float, 3>& direction,
                const float max_distance,
                const std::uint8_t layer_mask,
                const bool include_triggers,
                const std::optional<easy3d::EntityHandle> excluded) {
                 py::list result;
                 for (const easy3d::ScenePhysicsQueryHit& hit : scene.raycast_all(
                          {origin[0], origin[1], origin[2]},
                          {direction[0], direction[1], direction[2]},
                          max_distance,
                          layer_mask,
                          include_triggers,
                          excluded)) {
                     result.append(py::make_tuple(
                         hit.entity,
                         py::make_tuple(hit.point.x, hit.point.y, hit.point.z),
                         py::make_tuple(hit.normal.x, hit.normal.y, hit.normal.z),
                         hit.distance,
                         hit.fraction));
                 }
                 return result;
             },
             py::arg("origin"),
             py::arg("direction"),
             py::arg("max_distance"),
             py::arg("layer_mask") = 0x0fU,
             py::arg("include_triggers") = true,
             py::arg("excluded") = std::nullopt)
        .def("physics_overlap_sphere",
             [](const easy3d::Scene& scene,
                const std::array<float, 3>& center,
                const float radius,
                const std::uint8_t layer_mask,
                const bool include_triggers,
                const std::optional<easy3d::EntityHandle> excluded) {
                 py::list result;
                 for (const easy3d::ScenePhysicsQueryHit& hit : scene.overlap_sphere(
                          {center[0], center[1], center[2]},
                          radius,
                          layer_mask,
                          include_triggers,
                          excluded)) {
                     result.append(py::make_tuple(
                         hit.entity,
                         py::make_tuple(hit.point.x, hit.point.y, hit.point.z),
                         py::make_tuple(hit.normal.x, hit.normal.y, hit.normal.z),
                         hit.distance,
                         hit.fraction));
                 }
                 return result;
             },
             py::arg("center"),
             py::arg("radius"),
             py::arg("layer_mask") = 0x0fU,
             py::arg("include_triggers") = true,
             py::arg("excluded") = std::nullopt)
        .def("physics_overlap_box",
             [](const easy3d::Scene& scene,
                const std::array<float, 3>& center,
                const std::array<float, 3>& half_extents,
                const std::array<float, 4>& rotation,
                const std::uint8_t layer_mask,
                const bool include_triggers,
                const std::optional<easy3d::EntityHandle> excluded) {
                 py::list result;
                 for (const easy3d::ScenePhysicsQueryHit& hit : scene.overlap_box(
                          {center[0], center[1], center[2]},
                          {half_extents[0], half_extents[1], half_extents[2]},
                          {rotation[0], rotation[1], rotation[2], rotation[3]},
                          layer_mask,
                          include_triggers,
                          excluded)) {
                     result.append(py::make_tuple(
                         hit.entity,
                         py::make_tuple(hit.point.x, hit.point.y, hit.point.z),
                         py::make_tuple(hit.normal.x, hit.normal.y, hit.normal.z),
                         hit.distance,
                         hit.fraction));
                 }
                 return result;
             },
             py::arg("center"),
             py::arg("half_extents"),
             py::arg("rotation"),
             py::arg("layer_mask") = 0x0fU,
             py::arg("include_triggers") = true,
             py::arg("excluded") = std::nullopt)
        .def("physics_sphere_cast_all",
             [](const easy3d::Scene& scene,
                const std::array<float, 3>& origin,
                const float radius,
                const std::array<float, 3>& direction,
                const float max_distance,
                const std::uint8_t layer_mask,
                const bool include_triggers,
                const std::optional<easy3d::EntityHandle> excluded) {
                 py::list result;
                 for (const easy3d::ScenePhysicsQueryHit& hit : scene.sphere_cast_all(
                          {origin[0], origin[1], origin[2]},
                          radius,
                          {direction[0], direction[1], direction[2]},
                          max_distance,
                          layer_mask,
                          include_triggers,
                          excluded)) {
                     result.append(py::make_tuple(
                         hit.entity,
                         py::make_tuple(hit.point.x, hit.point.y, hit.point.z),
                         py::make_tuple(hit.normal.x, hit.normal.y, hit.normal.z),
                         hit.distance,
                         hit.fraction));
                 }
                 return result;
             },
             py::arg("origin"),
             py::arg("radius"),
             py::arg("direction"),
             py::arg("max_distance"),
             py::arg("layer_mask") = 0x0fU,
             py::arg("include_triggers") = true,
             py::arg("excluded") = std::nullopt)
        .def("physics_capsule_cast_all",
             [](const easy3d::Scene& scene,
                const std::array<float, 3>& origin,
                const float radius,
                const float height,
                const std::array<float, 4>& rotation,
                const std::array<float, 3>& direction,
                const float max_distance,
                const std::uint8_t layer_mask,
                const bool include_triggers,
                const std::optional<easy3d::EntityHandle> excluded) {
                 py::list result;
                 for (const easy3d::ScenePhysicsQueryHit& hit : scene.capsule_cast_all(
                          {origin[0], origin[1], origin[2]},
                          radius,
                          height,
                          {rotation[0], rotation[1], rotation[2], rotation[3]},
                          {direction[0], direction[1], direction[2]},
                          max_distance,
                          layer_mask,
                          include_triggers,
                          excluded)) {
                     result.append(py::make_tuple(
                         hit.entity,
                         py::make_tuple(hit.point.x, hit.point.y, hit.point.z),
                         py::make_tuple(hit.normal.x, hit.normal.y, hit.normal.z),
                         hit.distance,
                         hit.fraction));
                 }
                 return result;
             },
             py::arg("origin"),
             py::arg("radius"),
             py::arg("height"),
             py::arg("rotation"),
             py::arg("direction"),
             py::arg("max_distance"),
             py::arg("layer_mask") = 0x0fU,
             py::arg("include_triggers") = true,
             py::arg("excluded") = std::nullopt)
        .def("drain_physics_events",
             [contact_phase_name](easy3d::Scene& scene) {
                 py::list result;
                 for (const easy3d::ScenePhysicsContactEvent& event :
                      scene.drain_physics_events()) {
                     result.append(py::make_tuple(
                         contact_phase_name(event.phase),
                         event.trigger,
                         event.first,
                         event.second,
                         py::make_tuple(event.point.x, event.point.y, event.point.z),
                         py::make_tuple(event.normal.x,
                                        event.normal.y,
                                        event.normal.z)));
                 }
                 return result;
             })
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
                camera.far_plane,
                camera.projection == easy3d::CameraProjection::Orthographic
                    ? "orthographic"
                    : "perspective",
                camera.orthographic_height);
        })
        .def("set_camera",
             [](easy3d::Scene& scene,
                const std::array<float, 3>& position,
                const std::array<float, 4>& rotation,
                const float vertical_fov_degrees,
                const float near_plane,
                const float far_plane,
                const std::string& projection,
                const float orthographic_height) {
                 easy3d::CameraProjection projection_mode;
                 if (projection == "orthographic") {
                     projection_mode = easy3d::CameraProjection::Orthographic;
                 } else if (projection == "perspective") {
                     projection_mode = easy3d::CameraProjection::Perspective;
                 } else {
                     throw std::invalid_argument(
                         "camera projection must be 'perspective' or 'orthographic'");
                 }
                 scene.set_camera({{position[0], position[1], position[2]},
                                   {rotation[0], rotation[1], rotation[2], rotation[3]},
                                   vertical_fov_degrees,
                                   near_plane,
                                   far_plane,
                                   projection_mode,
                                   orthographic_height});
             },
             py::arg("position"),
             py::arg("rotation"),
             py::arg("vertical_fov_degrees"),
             py::arg("near_plane"),
             py::arg("far_plane"),
             py::arg("projection"),
             py::arg("orthographic_height"))
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
        .def("physics_gravity", [](const easy3d::Scene& scene) {
            const easy3d::Vec3 gravity = scene.physics_gravity();
            return py::make_tuple(gravity.x, gravity.y, gravity.z);
        })
        .def("set_physics_gravity",
             [](easy3d::Scene& scene, const std::array<float, 3>& gravity) {
                 scene.set_physics_gravity({gravity[0], gravity[1], gravity[2]});
             },
             py::arg("gravity"))
        .def("step_physics", &easy3d::Scene::step_physics, py::arg("delta_seconds"))
        .def_property_readonly("physics_step_count", &easy3d::Scene::physics_step_count)
        .def_property_readonly("debug_line_count", [](const easy3d::Scene& scene) {
            return scene.debug_lines().size();
        });
}

