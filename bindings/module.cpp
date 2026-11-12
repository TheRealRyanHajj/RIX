#include "easy3d/core.hpp"
#include "easy3d/assets.hpp"
#include "easy3d/network.hpp"
#include "easy3d/physics.hpp"
#include "easy3d/renderer.hpp"
#include "easy3d/scene.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/operators.h>
#include <pybind11/stl.h>

#include <array>
#include <chrono>
#include <cstdint>
#include <limits>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace py = pybind11;

PYBIND11_MODULE(_rix, module) {
    module.doc() = "RIX native engine core";

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
    module.def("_network_set_backend_impairment",
               &easy3d::set_network_backend_impairment,
               py::arg("lag_milliseconds"),
               py::arg("jitter_average_milliseconds"),
               py::arg("jitter_maximum_milliseconds"),
               py::arg("loss_percent"));
    module.def("_network_clear_backend_impairment",
               &easy3d::clear_network_backend_impairment);
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
    const auto assign_rgba8 = [](easy3d::ImageData& image,
                                 const py::bytes& pixels,
                                 const std::uint32_t width,
                                 const std::uint32_t height) {
        if (width == 0 || height == 0) {
            throw py::value_error("texture width and height must be positive");
        }
        const std::uint64_t expected =
            static_cast<std::uint64_t>(width) * height * 4U;
        const std::string bytes = pixels;
        if (expected > std::numeric_limits<std::size_t>::max() ||
            bytes.size() != static_cast<std::size_t>(expected)) {
            throw py::value_error(
                "RGBA8 data length must equal width * height * 4 bytes");
        }
        image.width = width;
        image.height = height;
        image.rgba8.assign(bytes.begin(), bytes.end());
        image.validate();
    };
    py::class_<easy3d::ImageData, std::shared_ptr<easy3d::ImageData>>(
        module, "_DynamicImage")
        .def(py::init([assign_rgba8](const std::uint32_t width,
                                    const std::uint32_t height,
                                    const py::bytes& pixels,
                                    const bool srgb) {
                 auto image = std::make_shared<easy3d::ImageData>();
                 image->source_path = "<RIX Pygame Surface>";
                 image->color_space = srgb ? easy3d::TextureColorSpace::Srgb
                                            : easy3d::TextureColorSpace::Linear;
                 assign_rgba8(*image, pixels, width, height);
                 return image;
             }),
             py::arg("width"),
             py::arg("height"),
             py::arg("rgba8"),
             py::arg("srgb") = true)
        .def("update",
             [assign_rgba8](easy3d::ImageData& image,
                            const std::uint32_t width,
                            const std::uint32_t height,
                            const py::bytes& pixels) {
                 assign_rgba8(image, pixels, width, height);
                 ++image.revision;
                 if (image.revision == 0) image.revision = 1;
             },
             py::arg("width"),
             py::arg("height"),
             py::arg("rgba8"))
        .def_property_readonly("width", [](const easy3d::ImageData& image) {
            return image.width;
        })
        .def_property_readonly("height", [](const easy3d::ImageData& image) {
            return image.height;
        })
        .def_property_readonly("revision", [](const easy3d::ImageData& image) {
            return image.revision;
        })
        .def("_rgba8", [](const easy3d::ImageData& image) {
            return py::bytes(reinterpret_cast<const char*>(image.rgba8.data()),
                             image.rgba8.size());
        });
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
                          const easy3d::TextureColorSpace color_space,
                          const bool hot_reload) {
                 return image_info(cache.load(path, color_space, hot_reload));
             },
             py::arg("path"),
             py::arg("color_space"),
             py::arg("hot_reload") = true)
        .def("poll_changes",
             [](const easy3d::TextureCache& cache, const std::uint64_t interval_ms) {
                 return cache.poll_changes(std::chrono::milliseconds(interval_ms));
             },
             py::arg("interval_ms") = 0)
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
            const auto path_or_none = [](const auto& path) -> py::object {
                return path.has_value() ? py::cast(path->string()) : py::none();
            };
            materials.append(py::make_tuple(material.name,
                                            py::make_tuple(material.diffuse_color.r,
                                                           material.diffuse_color.g,
                                                           material.diffuse_color.b,
                                                           material.diffuse_color.a),
                                            path_or_none(material.diffuse_texture),
                                            material.metallic,
                                            material.roughness,
                                            material.emission,
                                            path_or_none(material.normal_texture),
                                            path_or_none(material.roughness_texture),
                                            path_or_none(material.metallic_texture),
                                            path_or_none(material.emissive_texture),
                                            path_or_none(material.ambient_occlusion_texture),
                                            material.normal_strength,
                                             material.packed_metallic_roughness,
                                             material.double_sided));
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
    module.def("_load_gltf_info",
               [model_info](const std::string& path) {
                   const auto model = easy3d::load_gltf(path);
                   py::object skeleton = py::none();
                   if (model->skeleton.has_value()) {
                       py::list joints;
                       for (const easy3d::SkeletonJoint& joint :
                            model->skeleton->joints) {
                           py::tuple inverse_bind(16);
                           for (std::size_t index = 0;
                                index < joint.inverse_bind.values.size();
                                ++index) {
                               inverse_bind[index] = joint.inverse_bind.values[index];
                           }
                           joints.append(py::make_tuple(
                               joint.name,
                               joint.parent,
                               py::make_tuple(joint.local_bind.position.x,
                                              joint.local_bind.position.y,
                                              joint.local_bind.position.z),
                               py::make_tuple(joint.local_bind.rotation.w,
                                              joint.local_bind.rotation.x,
                                              joint.local_bind.rotation.y,
                                              joint.local_bind.rotation.z),
                               py::make_tuple(joint.local_bind.scale.x,
                                              joint.local_bind.scale.y,
                                              joint.local_bind.scale.z),
                               inverse_bind));
                       }
                       skeleton = py::make_tuple(model->skeleton->name, joints);
                   }
                   py::list animations;
                   for (const easy3d::AnimationClip& clip : model->animations) {
                       py::list channels;
                       for (const easy3d::AnimationChannel& channel : clip.channels) {
                           const char* target = "translation";
                           if (channel.target == easy3d::AnimationTarget::Rotation) {
                               target = "rotation";
                           } else if (channel.target ==
                                      easy3d::AnimationTarget::Scale) {
                               target = "scale";
                           }
                           channels.append(py::make_tuple(
                               channel.joint_index,
                               target,
                               channel.interpolation ==
                                       easy3d::AnimationInterpolation::Linear
                                   ? "linear"
                                   : "step",
                               channel.times,
                               channel.values));
                       }
                       animations.append(
                           py::make_tuple(clip.name, clip.duration, channels));
                   }
                   return py::make_tuple(model_info(model), skeleton, animations);
               },
               py::arg("path"));
    module.def("_load_fbx_info",
               [model_info](const std::string& path) {
                   const auto model = easy3d::load_fbx(path);
                   py::object skeleton = py::none();
                   if (model->skeleton.has_value()) {
                       py::list joints;
                       for (const easy3d::SkeletonJoint& joint : model->skeleton->joints) {
                           py::tuple inverse_bind(16);
                           for (std::size_t index = 0;
                                index < joint.inverse_bind.values.size(); ++index) {
                               inverse_bind[index] = joint.inverse_bind.values[index];
                           }
                           joints.append(py::make_tuple(
                               joint.name,
                               joint.parent,
                               py::make_tuple(joint.local_bind.position.x,
                                              joint.local_bind.position.y,
                                              joint.local_bind.position.z),
                               py::make_tuple(joint.local_bind.rotation.w,
                                              joint.local_bind.rotation.x,
                                              joint.local_bind.rotation.y,
                                              joint.local_bind.rotation.z),
                               py::make_tuple(joint.local_bind.scale.x,
                                              joint.local_bind.scale.y,
                                              joint.local_bind.scale.z),
                               inverse_bind));
                       }
                       skeleton = py::make_tuple(model->skeleton->name, joints);
                   }
                   py::list animations;
                   for (const easy3d::AnimationClip& clip : model->animations) {
                       py::list channels;
                       for (const easy3d::AnimationChannel& channel : clip.channels) {
                           const char* target = "translation";
                           if (channel.target == easy3d::AnimationTarget::Rotation) {
                               target = "rotation";
                           } else if (channel.target == easy3d::AnimationTarget::Scale) {
                               target = "scale";
                           }
                           channels.append(py::make_tuple(
                               channel.joint_index,
                               target,
                               channel.interpolation == easy3d::AnimationInterpolation::Linear
                                   ? "linear" : "step",
                               channel.times,
                               channel.values));
                       }
                       animations.append(py::make_tuple(clip.name, clip.duration, channels));
                   }
                   return py::make_tuple(model_info(model), skeleton, animations);
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
    const auto texture_mode = [](const std::string& value) {
        if (value == "auto") return easy3d::TextureMode::Auto;
        if (value == "tile") return easy3d::TextureMode::Tile;
        if (value == "atlas") return easy3d::TextureMode::Atlas;
        if (value == "sphere") return easy3d::TextureMode::Sphere;
        if (value == "preserve") return easy3d::TextureMode::Preserve;
        throw std::invalid_argument(
            "texture mode must be auto, tile, atlas, sphere, or preserve");
    };
    const auto texture_mode_name = [](const easy3d::TextureMode value) {
        switch (value) {
        case easy3d::TextureMode::Auto: return "auto";
        case easy3d::TextureMode::Tile: return "tile";
        case easy3d::TextureMode::Atlas: return "atlas";
        case easy3d::TextureMode::Sphere: return "sphere";
        case easy3d::TextureMode::Preserve: return "preserve";
        }
        return "auto";
    };
    const auto texture_filter = [](const std::string& value) {
        if (value == "nearest") return easy3d::TextureFilter::Nearest;
        if (value == "linear") return easy3d::TextureFilter::Linear;
        throw std::invalid_argument("texture filter must be nearest or linear");
    };
    const auto texture_filter_name = [](const easy3d::TextureFilter value) {
        return value == easy3d::TextureFilter::Nearest ? "nearest" : "linear";
    };
    const auto cull_mode = [](const std::string& value) {
        if (value == "back") return easy3d::CullMode::Back;
        if (value == "front") return easy3d::CullMode::Front;
        if (value == "none") return easy3d::CullMode::None;
        throw std::invalid_argument("cull mode must be back, front, or none");
    };
    const auto cull_mode_name = [](const easy3d::CullMode value) {
        switch (value) {
        case easy3d::CullMode::Back: return "back";
        case easy3d::CullMode::Front: return "front";
        case easy3d::CullMode::None: return "none";
        }
        return "back";
    };
    const auto optional_path = [](const std::optional<std::string>& value) {
        return value.has_value()
                   ? std::optional<std::filesystem::path>(*value)
                   : std::nullopt;
    };
    const auto light_kind = [](const std::string& value) {
        if (value == "ambient") {
            return easy3d::LightKind::Ambient;
        }
        if (value == "directional") {
            return easy3d::LightKind::Directional;
        }
        if (value == "point") {
            return easy3d::LightKind::Point;
        }
        if (value == "spot") {
            return easy3d::LightKind::Spot;
        }
        throw std::invalid_argument(
            "light kind must be ambient, directional, point, or spot");
    };
    const auto light_kind_name = [](const easy3d::LightKind value) {
        switch (value) {
        case easy3d::LightKind::Ambient: return "ambient";
        case easy3d::LightKind::Directional: return "directional";
        case easy3d::LightKind::Point: return "point";
        case easy3d::LightKind::Spot: return "spot";
        }
        return "unknown";
    };
    const auto ui_kind = [](const std::string& value) {
        if (value == "panel") return easy3d::UiElementKind::Panel;
        if (value == "sprite") return easy3d::UiElementKind::Sprite;
        if (value == "text") return easy3d::UiElementKind::Text;
        if (value == "button") return easy3d::UiElementKind::Button;
        throw std::invalid_argument("UI kind must be panel, sprite, text, or button");
    };
    const auto ui_kind_name = [](const easy3d::UiElementKind value) {
        switch (value) {
        case easy3d::UiElementKind::Panel: return "panel";
        case easy3d::UiElementKind::Sprite: return "sprite";
        case easy3d::UiElementKind::Text: return "text";
        case easy3d::UiElementKind::Button: return "button";
        }
        return "panel";
    };
    const auto ui_anchor = [](const std::string& value) {
        if (value == "top_left") return easy3d::UiAnchor::TopLeft;
        if (value == "top") return easy3d::UiAnchor::Top;
        if (value == "top_right") return easy3d::UiAnchor::TopRight;
        if (value == "left") return easy3d::UiAnchor::Left;
        if (value == "center") return easy3d::UiAnchor::Center;
        if (value == "right") return easy3d::UiAnchor::Right;
        if (value == "bottom_left") return easy3d::UiAnchor::BottomLeft;
        if (value == "bottom") return easy3d::UiAnchor::Bottom;
        if (value == "bottom_right") return easy3d::UiAnchor::BottomRight;
        throw std::invalid_argument("invalid UI anchor");
    };
    const auto ui_anchor_name = [](const easy3d::UiAnchor value) {
        switch (value) {
        case easy3d::UiAnchor::TopLeft: return "top_left";
        case easy3d::UiAnchor::Top: return "top";
        case easy3d::UiAnchor::TopRight: return "top_right";
        case easy3d::UiAnchor::Left: return "left";
        case easy3d::UiAnchor::Center: return "center";
        case easy3d::UiAnchor::Right: return "right";
        case easy3d::UiAnchor::BottomLeft: return "bottom_left";
        case easy3d::UiAnchor::Bottom: return "bottom";
        case easy3d::UiAnchor::BottomRight: return "bottom_right";
        }
        return "top_left";
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
        .def("_begin_frame", &easy3d::InputSystem::begin_frame)
        .def("_end_frame", &easy3d::InputSystem::end_frame)
        .def("_set_control",
             &easy3d::InputSystem::set_control,
             py::arg("control"),
             py::arg("value"))
        .def("_add_pointer_motion",
             &easy3d::InputSystem::add_pointer_motion,
             py::arg("x"),
             py::arg("y"),
             py::arg("delta_x"),
             py::arg("delta_y"))
        .def("_add_wheel",
             &easy3d::InputSystem::add_wheel,
             py::arg("x"),
             py::arg("y"))
        .def("_set_focused", &easy3d::InputSystem::set_focused)
        .def("_set_pointer_lock_active",
             &easy3d::InputSystem::set_pointer_lock_active)
        .def("_set_gamepad_connected",
             &easy3d::InputSystem::set_gamepad_connected,
             py::arg("connected"),
             py::arg("name") = "")
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
        .def("control_state", [](const easy3d::InputSystem& input,
                                 const std::string& control) {
            const easy3d::InputActionState state = input.control_state(control);
            return py::make_tuple(
                state.value, state.down, state.pressed, state.released);
        })
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

    const auto external_viewport_camera = [](const double px,
                                              const double py,
                                              const double pz,
                                              const double qw,
                                              const double qx,
                                              const double qy,
                                              const double qz,
                                              const double vertical_fov_degrees,
                                              const double near_plane,
                                              const double far_plane,
                                              const bool orthographic,
                                              const double orthographic_height) {
        easy3d::Camera camera;
        camera.position = {static_cast<float>(px),
                           static_cast<float>(py),
                           static_cast<float>(pz)};
        camera.rotation = {static_cast<float>(qw),
                           static_cast<float>(qx),
                           static_cast<float>(qy),
                           static_cast<float>(qz)};
        camera.vertical_fov_degrees = static_cast<float>(vertical_fov_degrees);
        camera.near_plane = static_cast<float>(near_plane);
        camera.far_plane = static_cast<float>(far_plane);
        camera.projection = orthographic
            ? easy3d::CameraProjection::Orthographic
            : easy3d::CameraProjection::Perspective;
        camera.orthographic_height = static_cast<float>(orthographic_height);
        camera.validate();
        return camera;
    };

    py::class_<easy3d::Engine>(module, "Engine")
        .def(py::init([](std::string title,
                         const std::uint32_t width,
                         const std::uint32_t height,
                         const bool vsync,
                         const double fps_limit,
                         const std::string& graphics_preset) {
                 easy3d::GraphicsPreset preset;
                 if (graphics_preset == "low") {
                     preset = easy3d::GraphicsPreset::Low;
                 } else if (graphics_preset == "medium") {
                     preset = easy3d::GraphicsPreset::Medium;
                 } else if (graphics_preset == "high") {
                     preset = easy3d::GraphicsPreset::High;
                 } else if (graphics_preset == "ultra") {
                     preset = easy3d::GraphicsPreset::Ultra;
                 } else {
                     throw py::value_error(
                         "graphics_preset must be 'low', 'medium', 'high', or 'ultra'");
                 }
                 return std::make_unique<easy3d::Engine>(easy3d::EngineConfig{
                     std::move(title), width, height, vsync, fps_limit, preset});
             }),
             py::arg("title") = "RIX",
             py::arg("width") = 1280,
             py::arg("height") = 720,
             py::arg("vsync") = true,
             py::arg("fps_limit") = 0.0,
             py::arg("graphics_preset") = "medium")
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
        .def("tick",
             [](easy3d::Engine& engine,
                const py::object& callback,
                const double fps_limit) {
                 easy3d::Engine::FrameCallback frame_callback;
                 if (!callback.is_none()) {
                     if (PyCallable_Check(callback.ptr()) == 0) {
                         throw py::type_error("frame_callback must be callable or None");
                     }
                     PyObject* const callback_ptr = callback.ptr();
                     frame_callback = [callback_ptr](const double delta_seconds) {
                         py::gil_scoped_acquire acquire;
                         py::reinterpret_borrow<py::function>(callback_ptr)(delta_seconds);
                     };
                 }
                 py::gil_scoped_release release;
                 return engine.tick(std::move(frame_callback), fps_limit);
             },
             py::arg("frame_callback") = py::none(),
             py::arg("fps_limit") = -1.0)
        .def("stop", &easy3d::Engine::stop)
        .def("close", &easy3d::Engine::close)
        .def("begin_external_window",
             &easy3d::Engine::begin_external_window,
             py::arg("native_window"),
             py::arg("width"),
             py::arg("height"))
        .def("resize_external_window",
             &easy3d::Engine::resize_external_window,
             py::arg("width"),
             py::arg("height"))
        .def("render_external_window", &easy3d::Engine::render_external_window)
        .def("render_external_offscreen", &easy3d::Engine::render_external_offscreen)
        .def("readback_external_window_rgba8", [](easy3d::Engine& engine) {
            const std::vector<std::uint8_t> pixels =
                engine.readback_external_window_rgba8();
            return py::bytes(reinterpret_cast<const char*>(pixels.data()), pixels.size());
        })
        .def("render_external_viewport_rgba8",
             [external_viewport_camera](easy3d::Engine& engine,
                                        const double px,
                                        const double py,
                                        const double pz,
                                        const double qw,
                                        const double qx,
                                        const double qy,
                                        const double qz,
                                        const double vertical_fov_degrees,
                                        const double near_plane,
                                        const double far_plane,
                                        const bool orthographic,
                                        const double orthographic_height,
                                        const std::uint32_t width,
                                        const std::uint32_t height) {
                 const std::vector<std::uint8_t> pixels =
                     engine.render_external_viewport_rgba8(
                         external_viewport_camera(
                             px, py, pz, qw, qx, qy, qz,
                             vertical_fov_degrees, near_plane, far_plane,
                             orthographic, orthographic_height),
                         width,
                         height);
                 return py::bytes(
                     reinterpret_cast<const char*>(pixels.data()), pixels.size());
             })
        .def("request_external_viewport_rgba8",
             [external_viewport_camera](easy3d::Engine& engine,
                                        const double px,
                                        const double py,
                                        const double pz,
                                        const double qw,
                                        const double qx,
                                        const double qy,
                                        const double qz,
                                        const double vertical_fov_degrees,
                                        const double near_plane,
                                        const double far_plane,
                                        const bool orthographic,
                                        const double orthographic_height,
                                        const std::uint32_t width,
                                        const std::uint32_t height) {
                 return engine.request_external_viewport_rgba8(
                     external_viewport_camera(
                         px, py, pz, qw, qx, qy, qz,
                         vertical_fov_degrees, near_plane, far_plane,
                         orthographic, orthographic_height),
                     width,
                     height);
             })
        .def("poll_external_viewport_rgba8",
             [](easy3d::Engine& engine,
                const std::uint64_t request_id) -> py::object {
                 auto pixels = engine.poll_external_viewport_rgba8(request_id);
                 if (!pixels.has_value()) return py::none();
                 return py::bytes(
                     reinterpret_cast<const char*>(pixels->data()), pixels->size());
             })
        .def("wait_external_viewport_rgba8",
             [](easy3d::Engine& engine, const std::uint64_t request_id) {
                 const std::vector<std::uint8_t> pixels =
                     engine.wait_external_viewport_rgba8(request_id);
                 return py::bytes(
                     reinterpret_cast<const char*>(pixels.data()), pixels.size());
             })
        .def("cancel_external_viewport_rgba8",
             &easy3d::Engine::cancel_external_viewport_rgba8)
        .def("end_external_window", &easy3d::Engine::end_external_window)
        .def("set_scene",
             [](easy3d::Engine& engine, easy3d::Scene* scene) {
                 engine.set_scene(scene);
             },
             py::arg("scene") = nullptr)
        .def_property_readonly("is_running", &easy3d::Engine::is_running)
        .def_property_readonly("frame_count", &easy3d::Engine::frame_count)
        .def_property_readonly("last_frame_seconds", &easy3d::Engine::last_frame_seconds)
        .def_property_readonly("viewport_size", &easy3d::Engine::viewport_size)
        .def_property_readonly("graphics_preset", [](const easy3d::Engine& engine) {
            return easy3d::graphics_preset_name(engine.config().graphics_preset);
        })
        .def_property_readonly(
            "input",
            static_cast<easy3d::InputSystem& (easy3d::Engine::*)() noexcept>(
                &easy3d::Engine::input),
            py::return_value_policy::reference_internal)
        .def("audio_create_pcm16_sound",
             [](easy3d::Engine& engine,
                const py::bytes& data,
                const std::uint8_t channels,
                const std::uint32_t sample_rate) {
                 const std::string bytes = data;
                 if (bytes.empty() || bytes.size() % 2 != 0) {
                     throw py::value_error(
                         "PCM16 data must contain a non-empty even number of bytes");
                 }
                 std::vector<std::int16_t> samples(bytes.size() / 2);
                 for (std::size_t index = 0; index < samples.size(); ++index) {
                     const auto low = static_cast<std::uint8_t>(bytes[index * 2]);
                     const auto high = static_cast<std::uint8_t>(bytes[index * 2 + 1]);
                     const std::uint16_t value = static_cast<std::uint16_t>(low) |
                                                 (static_cast<std::uint16_t>(high) << 8U);
                     samples[index] = static_cast<std::int16_t>(value);
                 }
                 return engine.audio().create_pcm16_sound(
                     std::move(samples), channels, sample_rate);
             },
             py::arg("data"),
             py::arg("channels"),
             py::arg("sample_rate"))
        .def("audio_play",
             [](easy3d::Engine& engine,
                const std::uint64_t sound,
                const float volume,
                const bool loop,
                const bool spatial,
                const std::array<float, 3>& position,
                const float minimum_distance,
                const float maximum_distance) {
                 easy3d::AudioPlayConfig config;
                 config.volume = volume;
                 config.loop = loop;
                 config.spatial = spatial;
                 config.position = {position[0], position[1], position[2]};
                 config.minimum_distance = minimum_distance;
                 config.maximum_distance = maximum_distance;
                 return engine.audio().play(sound, config);
             },
             py::arg("sound"),
             py::arg("volume") = 1.0F,
             py::arg("loop") = false,
             py::arg("spatial") = false,
             py::arg("position") = std::array<float, 3>{0.0F, 0.0F, 0.0F},
             py::arg("minimum_distance") = 1.0F,
             py::arg("maximum_distance") = 50.0F)
        .def("audio_stop", [](easy3d::Engine& engine, const std::uint64_t voice) {
            engine.audio().stop(voice);
        })
        .def("audio_set_volume",
             [](easy3d::Engine& engine,
                const std::uint64_t voice,
                const float volume) {
                 engine.audio().set_voice_volume(voice, volume);
             })
        .def("audio_set_position",
             [](easy3d::Engine& engine,
                const std::uint64_t voice,
                const std::array<float, 3>& position) {
                 engine.audio().set_voice_position(
                     voice, {position[0], position[1], position[2]});
             })
        .def("audio_voice_playing",
             [](const easy3d::Engine& engine, const std::uint64_t voice) {
                 return engine.audio().voice_playing(voice);
             })
        .def_property_readonly("audio_backend_active", [](const easy3d::Engine& engine) {
            return engine.audio().backend_active();
        })
        .def_property_readonly("audio_sound_count", [](const easy3d::Engine& engine) {
            return engine.audio().sound_count();
        })
        .def_property_readonly("audio_active_voice_count",
                               [](const easy3d::Engine& engine) {
                                   return engine.audio().active_voice_count();
                               })
        .def_property_readonly("renderer_stats", [](const easy3d::Engine& engine) {
            const easy3d::RendererStats stats = engine.renderer_stats();
            return py::make_tuple(stats.draw_calls,
                                  stats.visible_instances,
                                  stats.culled_instances,
                                  stats.instanced_draw_calls,
                                  stats.ui_draw_calls,
                                  stats.ui_elements,
                                  stats.enhanced_lighting,
                                  stats.shadows,
                                  stats.postprocessing,
                                  stats.fxaa,
                                  stats.shadow_resolution,
                                  stats.cpu_frame_ms,
                                  stats.gpu_frame_ms,
                                  stats.texture_count,
                                  stats.texture_memory_bytes,
                                  stats.active_directional_lights,
                                  stats.active_point_lights,
                                  stats.active_spot_lights,
                                  stats.culled_lights,
                                  stats.shadow_passes,
                                  stats.active_shadow_casters,
                                  stats.dropped_shadow_casters,
                                  stats.shadow_memory_bytes);
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
        .def("entity_velocity", [](const easy3d::Scene& scene,
                                     const easy3d::EntityHandle handle) {
            const easy3d::Vec3 value = scene.entity_velocity(handle);
            return py::make_tuple(value.x, value.y, value.z);
        })
        .def("set_entity_velocity", [](easy3d::Scene& scene,
                                         const easy3d::EntityHandle handle,
                                         const std::array<float, 3>& value) {
            scene.set_entity_velocity(handle, {value[0], value[1], value[2]});
        })
        .def("entity_acceleration", [](const easy3d::Scene& scene,
                                         const easy3d::EntityHandle handle) {
            const easy3d::Vec3 value = scene.entity_acceleration(handle);
            return py::make_tuple(value.x, value.y, value.z);
        })
        .def("set_entity_acceleration", [](easy3d::Scene& scene,
                                             const easy3d::EntityHandle handle,
                                             const std::array<float, 3>& value) {
            scene.set_entity_acceleration(handle, {value[0], value[1], value[2]});
        })
        .def("entity_angular_velocity", [](const easy3d::Scene& scene,
                                             const easy3d::EntityHandle handle) {
            const easy3d::Vec3 value = scene.entity_angular_velocity(handle);
            return py::make_tuple(value.x, value.y, value.z);
        })
        .def("set_entity_angular_velocity", [](easy3d::Scene& scene,
                                                 const easy3d::EntityHandle handle,
                                                 const std::array<float, 3>& value) {
            scene.set_entity_angular_velocity(handle, {value[0], value[1], value[2]});
        })
        .def("entity_angular_acceleration", [](const easy3d::Scene& scene,
                                                 const easy3d::EntityHandle handle) {
            const easy3d::Vec3 value = scene.entity_angular_acceleration(handle);
            return py::make_tuple(value.x, value.y, value.z);
        })
        .def("set_entity_angular_acceleration", [](easy3d::Scene& scene,
                                                     const easy3d::EntityHandle handle,
                                                     const std::array<float, 3>& value) {
            scene.set_entity_angular_acceleration(
                handle, {value[0], value[1], value[2]});
        })
        .def("entity_character_yaw_offset",
             &easy3d::Scene::entity_character_yaw_offset,
             py::arg("handle"))
        .def("reset_entity_motion",
             &easy3d::Scene::reset_entity_motion,
             py::arg("handle"))
        .def("add_primitive_renderer",
             [render_kind, texture_mode, texture_filter, cull_mode, optional_path](easy3d::Scene& scene,
                           const easy3d::EntityHandle handle,
                           const std::string& kind,
                           const std::array<float, 4>& color,
                           const std::optional<std::string>& texture,
                           const double pixels_per_unit,
                           const std::string& filter,
                           const std::string& mode,
                           const std::optional<std::string>& normal_map,
                           const std::optional<std::string>& roughness_map,
                           const std::optional<std::string>& metallic_map,
                           const std::optional<std::string>& emissive_map,
                           const std::optional<std::string>& ambient_occlusion_map,
                           const double normal_strength,
                           const bool hot_reload,
                            const std::array<float, 3>& atlas_dimensions,
                            const std::string& culling) {
                 easy3d::TextureMaterialSettings settings;
                 settings.pixels_per_unit = static_cast<float>(pixels_per_unit);
                 settings.filter = texture_filter(filter);
                 settings.mode = texture_mode(mode);
                 settings.atlas_dimensions = {atlas_dimensions[0],
                                              atlas_dimensions[1],
                                              atlas_dimensions[2]};
                 settings.normal_strength = static_cast<float>(normal_strength);
                 settings.hot_reload = hot_reload;
                 scene.add_primitive_renderer(
                     handle,
                     render_kind(kind),
                     {color[0], color[1], color[2], color[3]},
                     optional_path(texture),
                     settings,
                     optional_path(normal_map),
                     optional_path(roughness_map),
                     optional_path(metallic_map),
                     optional_path(emissive_map),
                      optional_path(ambient_occlusion_map),
                      cull_mode(culling));
             },
             py::arg("handle"),
             py::arg("kind"),
             py::arg("color"),
             py::arg("texture") = std::nullopt,
             py::arg("pixels_per_unit") = 16.0,
             py::arg("texture_filter") = "nearest",
             py::arg("texture_mode") = "auto",
             py::arg("normal_map") = std::nullopt,
             py::arg("roughness_map") = std::nullopt,
             py::arg("metallic_map") = std::nullopt,
             py::arg("emissive_map") = std::nullopt,
             py::arg("ambient_occlusion_map") = std::nullopt,
             py::arg("normal_strength") = 1.0,
             py::arg("hot_reload") = true,
              py::arg("atlas_dimensions") = std::array<float, 3>{1.0F, 1.0F, 1.0F},
              py::arg("cull_mode") = "back")
        .def("add_model_renderer",
             [cull_mode](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::string& path,
                 const std::array<float, 4>& color,
                 const std::optional<std::string>& culling) {
                 scene.add_model_renderer(
                      handle,
                      path,
                      {color[0], color[1], color[2], color[3]},
                      culling.has_value()
                          ? std::optional<easy3d::CullMode>(cull_mode(*culling))
                          : std::nullopt);
             },
             py::arg("handle"),
             py::arg("path"),
              py::arg("color"),
              py::arg("cull_mode") = std::nullopt)
        .def("add_model_animation",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                std::string name,
                const std::string& path) {
                 scene.add_model_animation(handle, std::move(name), path);
             },
             py::arg("handle"), py::arg("name"), py::arg("path"))
        .def("play_model_animation", &easy3d::Scene::play_model_animation,
             py::arg("handle"), py::arg("name"), py::arg("loop") = true,
             py::arg("speed") = 1.0F, py::arg("blend") = 0.0F,
             py::arg("root_motion") = false)
        .def("pause_model_animation", &easy3d::Scene::pause_model_animation,
             py::arg("handle"))
        .def("resume_model_animation", &easy3d::Scene::resume_model_animation,
             py::arg("handle"))
        .def("stop_model_animation", &easy3d::Scene::stop_model_animation,
             py::arg("handle"))
        .def("model_animation_info",
             [](const easy3d::Scene& scene, const easy3d::EntityHandle handle) {
                 const easy3d::RenderComponent& component =
                     scene.render_component(handle);
                 if (!component.animation) {
                     throw easy3d::AssetError("model has no animation-capable skeleton");
                 }
                 const easy3d::ModelAnimationState& state = *component.animation;
                 py::list clips;
                 for (const auto& [name, clip] : state.clips) {
                     clips.append(py::make_tuple(name, clip.duration));
                 }
                 float duration = 0.0F;
                 const auto current = state.clips.find(state.current_clip);
                 if (current != state.clips.end()) duration = current->second.duration;
                 const char* skinning =
                     component.model && component.model->skeleton &&
                             component.model->skeleton->joints.size() <= 64U
                         ? "gpu"
                         : "cpu";
                 return py::make_tuple(clips, state.current_clip, state.time_seconds,
                                       duration, state.speed, state.loop, state.playing,
                                       state.paused, state.root_motion,
                                       skinning,
                                       state.completion_count);
             },
             py::arg("handle"))
        .def("has_render_component", &easy3d::Scene::has_render_component)
        .def("render_component_info",
             [render_kind_name, texture_mode_name, texture_filter_name, cull_mode_name](const easy3d::Scene& scene,
                                const easy3d::EntityHandle handle) {
                 const easy3d::RenderComponent& component =
                     scene.render_component(handle);
                 py::object asset = py::none();
                 if (component.model) {
                     asset = py::cast(component.model->source_path.string());
                 } else if (component.texture) {
                     asset = py::cast(component.texture->source_path.string());
                 }
                 const auto path_or_none = [](const auto& image) -> py::object {
                     return image ? py::cast(image->source_path.string()) : py::none();
                 };
                 return py::make_tuple(
                     render_kind_name(component.kind),
                     py::make_tuple(component.material.color.r,
                                    component.material.color.g,
                                    component.material.color.b,
                                    component.material.color.a),
                     asset,
                     component.material.lit,
                     component.material.metallic,
                     component.material.roughness,
                     component.material.emission,
                     component.material.casts_shadows,
                     component.material.receives_shadows,
                     component.texture_settings.pixels_per_unit,
                     texture_filter_name(component.texture_settings.filter),
                     texture_mode_name(component.texture_settings.mode),
                     component.material.normal_strength,
                     component.texture_settings.hot_reload,
                     path_or_none(component.normal_map),
                     path_or_none(component.roughness_map),
                     path_or_none(component.metallic_map),
                     path_or_none(component.emissive_map),
                     path_or_none(component.ambient_occlusion_map),
                     py::make_tuple(component.texture_settings.atlas_dimensions.x,
                                    component.texture_settings.atlas_dimensions.y,
                                     component.texture_settings.atlas_dimensions.z),
                      cull_mode_name(component.material.cull_mode));
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
        .def("set_render_cull_mode",
             [cull_mode](easy3d::Scene& scene,
                         const easy3d::EntityHandle handle,
                         const std::string& value) {
                 scene.set_render_cull_mode(handle, cull_mode(value));
             },
             py::arg("handle"),
             py::arg("cull_mode"))
        .def("set_render_surface",
             &easy3d::Scene::set_render_surface,
             py::arg("handle"),
             py::arg("metallic"),
             py::arg("roughness"),
             py::arg("emission"),
             py::arg("casts_shadows"),
             py::arg("receives_shadows"))
        .def("set_render_texture",
             [texture_mode, texture_filter, optional_path](
                 easy3d::Scene& scene,
                 const easy3d::EntityHandle handle,
                 const std::optional<std::string>& texture,
                 const double pixels_per_unit,
                 const std::string& filter,
                 const std::string& mode,
                 const std::optional<std::string>& normal_map,
                 const std::optional<std::string>& roughness_map,
                 const std::optional<std::string>& metallic_map,
                 const std::optional<std::string>& emissive_map,
                 const std::optional<std::string>& ambient_occlusion_map,
                 const double normal_strength,
                 const bool hot_reload,
                 const std::array<float, 3>& atlas_dimensions) {
                 easy3d::TextureMaterialSettings settings;
                 settings.pixels_per_unit = static_cast<float>(pixels_per_unit);
                 settings.filter = texture_filter(filter);
                 settings.mode = texture_mode(mode);
                 settings.atlas_dimensions = {atlas_dimensions[0],
                                              atlas_dimensions[1],
                                              atlas_dimensions[2]};
                 settings.normal_strength = static_cast<float>(normal_strength);
                 settings.hot_reload = hot_reload;
                 scene.set_render_texture(handle,
                                          optional_path(texture),
                                          settings,
                                          optional_path(normal_map),
                                          optional_path(roughness_map),
                                          optional_path(metallic_map),
                                          optional_path(emissive_map),
                                          optional_path(ambient_occlusion_map));
             },
             py::arg("handle"),
             py::arg("texture"),
             py::arg("pixels_per_unit"),
             py::arg("texture_filter"),
             py::arg("texture_mode"),
             py::arg("normal_map") = std::nullopt,
             py::arg("roughness_map") = std::nullopt,
             py::arg("metallic_map") = std::nullopt,
             py::arg("emissive_map") = std::nullopt,
             py::arg("ambient_occlusion_map") = std::nullopt,
             py::arg("normal_strength") = 1.0,
             py::arg("hot_reload") = true,
             py::arg("atlas_dimensions") = std::array<float, 3>{1.0F, 1.0F, 1.0F})
        .def("set_render_image",
             [texture_mode, texture_filter](
                 easy3d::Scene& scene,
                 const easy3d::EntityHandle handle,
                 const std::shared_ptr<easy3d::ImageData>& texture,
                 const double pixels_per_unit,
                 const std::string& filter,
                 const std::string& mode,
                 const std::array<float, 3>& atlas_dimensions) {
                 easy3d::TextureMaterialSettings settings;
                 settings.pixels_per_unit = static_cast<float>(pixels_per_unit);
                 settings.filter = texture_filter(filter);
                 settings.mode = texture_mode(mode);
                 settings.atlas_dimensions = {atlas_dimensions[0],
                                              atlas_dimensions[1],
                                              atlas_dimensions[2]};
                 settings.hot_reload = false;
                 scene.set_render_image(handle, texture, settings);
             },
             py::arg("handle"),
             py::arg("texture"),
             py::arg("pixels_per_unit"),
             py::arg("texture_filter"),
             py::arg("texture_mode"),
             py::arg("atlas_dimensions") = std::array<float, 3>{1.0F, 1.0F, 1.0F})
        .def("remove_render_component", &easy3d::Scene::remove_render_component)
        .def("add_light_component",
             [light_kind](easy3d::Scene& scene,
                          const easy3d::EntityHandle handle,
                          const std::string& kind,
                          const std::array<float, 4>& color,
                          const float intensity,
                          const float range,
                          const float inner_angle,
                          const float outer_angle,
                          const bool casts_shadows,
                          const std::uint16_t shadow_resolution,
                          const float shadow_bias) {
                 scene.add_light_component(
                     handle,
                     light_kind(kind),
                     {color[0], color[1], color[2], color[3]},
                     intensity,
                     range,
                     inner_angle,
                     outer_angle,
                     casts_shadows,
                     shadow_resolution,
                     shadow_bias);
             },
             py::arg("handle"),
             py::arg("kind"),
             py::arg("color"),
             py::arg("intensity"),
             py::arg("range") = 10.0,
             py::arg("inner_angle") = 30.0,
             py::arg("outer_angle") = 45.0,
             py::arg("casts_shadows") = false,
             py::arg("shadow_resolution") = 0,
             py::arg("shadow_bias") = 0.002)
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
                     component.intensity,
                     component.range,
                     component.inner_angle_degrees,
                     component.outer_angle_degrees,
                     component.casts_shadows,
                     component.shadow_resolution,
                     component.shadow_bias);
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
        .def("set_light_properties",
             &easy3d::Scene::set_light_properties,
             py::arg("handle"),
             py::arg("range"),
             py::arg("inner_angle"),
             py::arg("outer_angle"),
             py::arg("casts_shadows"),
             py::arg("shadow_resolution"),
             py::arg("shadow_bias"))
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
                     easy3d::ModelCache model_cache;
                     const std::shared_ptr<const easy3d::ModelData> model =
                         model_cache.load(*mesh_path);
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
        .def("rigid_body_angular_velocity",
             [](const easy3d::Scene& scene,
                const easy3d::EntityHandle handle) {
                 const easy3d::Vec3 value =
                     scene.rigid_body_angular_velocity(handle);
                 return py::make_tuple(value.x, value.y, value.z);
             },
             py::arg("handle"))
        .def("set_rigid_body_angular_velocity",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::array<float, 3>& velocity) {
                 scene.set_rigid_body_angular_velocity(
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
                const float air_acceleration,
                const float ground_friction,
                const float stop_speed,
                const float air_speed_cap,
                const float horizontal_speed_limit,
                const float jump_speed,
                const float max_slope_degrees,
                const float step_height,
                const float sprint_multiplier,
                const float crouch_height,
                const float crouch_speed_multiplier) {
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
                      air_acceleration,
                      ground_friction,
                      stop_speed,
                      air_speed_cap,
                      horizontal_speed_limit,
                      jump_speed,
                      max_slope_degrees,
                      step_height,
                      sprint_multiplier,
                      crouch_height,
                      crouch_speed_multiplier});
             },
             py::arg("handle"),
             py::arg("mode"),
             py::arg("radius"),
             py::arg("height"),
             py::arg("speed"),
             py::arg("acceleration"),
             py::arg("air_acceleration"),
             py::arg("ground_friction"),
             py::arg("stop_speed"),
             py::arg("air_speed_cap"),
             py::arg("horizontal_speed_limit"),
             py::arg("jump_speed"),
             py::arg("max_slope_degrees"),
             py::arg("step_height"),
             py::arg("sprint_multiplier"),
             py::arg("crouch_height"),
             py::arg("crouch_speed_multiplier"))
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
                     component.air_acceleration,
                     component.ground_friction,
                     component.stop_speed,
                     component.air_speed_cap,
                     component.horizontal_speed_limit,
                     component.jump_speed,
                     component.max_slope_degrees,
                     component.step_height,
                     component.sprint_multiplier,
                     component.crouch_height,
                     component.crouch_speed_multiplier);
             },
             py::arg("handle"))
        .def("remove_character_controller_component",
             &easy3d::Scene::remove_character_controller_component)
        .def("set_character_input",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::array<float, 3>& movement,
                const float heading_degrees,
                const bool jump,
                const bool sprint,
                const bool crouch) {
                 scene.set_character_input(
                     handle,
                     {movement[0], movement[1], movement[2]},
                     heading_degrees,
                     jump,
                     sprint,
                     crouch);
             },
             py::arg("handle"),
             py::arg("movement"),
             py::arg("heading_degrees"),
             py::arg("jump") = false,
             py::arg("sprint") = false,
             py::arg("crouch") = false)
        .def("set_character_sequenced_input",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::uint64_t sequence,
                const std::array<float, 3>& movement,
                const float heading_degrees,
                const bool jump,
                const bool sprint,
                const bool crouch) {
                 scene.set_character_sequenced_input(
                     handle,
                     sequence,
                     {movement[0], movement[1], movement[2]},
                     heading_degrees,
                     jump,
                     sprint,
                     crouch);
             },
             py::arg("handle"),
             py::arg("sequence"),
             py::arg("movement"),
             py::arg("heading_degrees"),
             py::arg("jump") = false,
             py::arg("sprint") = false,
             py::arg("crouch") = false)
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
                     state.grounded,
                     state.crouched,
                     state.sprinting);
             },
             py::arg("handle"))
        .def("set_character_linear_velocity",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::array<float, 3>& velocity) {
                 scene.set_character_linear_velocity(
                     handle, {velocity[0], velocity[1], velocity[2]});
             },
             py::arg("handle"),
             py::arg("velocity"))
        .def("correct_character",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::array<float, 3>& position,
                const std::array<float, 4>& rotation,
                const std::array<float, 3>& linear_velocity) {
                 scene.correct_character(
                     handle,
                     {position[0], position[1], position[2]},
                     {rotation[0], rotation[1], rotation[2], rotation[3]},
                     {linear_velocity[0], linear_velocity[1], linear_velocity[2]});
             },
             py::arg("handle"),
             py::arg("position"),
             py::arg("rotation"),
             py::arg("linear_velocity"))
        .def("replay_character_input",
             [](easy3d::Scene& scene,
                const easy3d::EntityHandle handle,
                const std::array<float, 3>& movement,
                const float heading_degrees,
                const bool jump,
                const bool sprint,
                const bool crouch,
                const float delta_seconds) {
                 scene.replay_character_input(
                     handle,
                     {movement[0], movement[1], movement[2]},
                     heading_degrees,
                     jump,
                     sprint,
                     crouch,
                     delta_seconds);
             },
             py::arg("handle"),
             py::arg("movement"),
             py::arg("heading_degrees"),
             py::arg("jump"),
             py::arg("sprint"),
             py::arg("crouch"),
             py::arg("delta_seconds"))
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
        .def("skybox_info", [](const easy3d::Scene& scene) -> py::object {
            if (!scene.skybox().has_value()) return py::none();
            const easy3d::SkyboxConfig& sky = *scene.skybox();
            py::object source = py::none();
            const char* kind = "procedural";
            if (sky.kind == easy3d::SkyboxKind::Panorama) {
                kind = "panorama";
                source = py::cast(sky.panorama->source_path.string());
            } else if (sky.kind == easy3d::SkyboxKind::Cubemap) {
                kind = "cubemap";
                py::list paths;
                for (const auto& face : sky.cubemap) {
                    paths.append(face->source_path.string());
                }
                source = std::move(paths);
            }
            return py::make_tuple(
                kind,
                py::make_tuple(sky.top.r, sky.top.g, sky.top.b, sky.top.a),
                py::make_tuple(sky.horizon.r, sky.horizon.g,
                               sky.horizon.b, sky.horizon.a),
                py::make_tuple(sky.bottom.r, sky.bottom.g,
                               sky.bottom.b, sky.bottom.a),
                sky.brightness, sky.rotation_degrees, source);
        })
        .def("set_procedural_skybox",
             [](easy3d::Scene& scene,
                const std::array<float, 4>& top,
                const std::array<float, 4>& horizon,
                const std::array<float, 4>& bottom,
                const float brightness,
                const float rotation) {
                 scene.set_procedural_skybox(
                     {top[0], top[1], top[2], top[3]},
                     {horizon[0], horizon[1], horizon[2], horizon[3]},
                     {bottom[0], bottom[1], bottom[2], bottom[3]},
                     brightness, rotation);
             })
        .def("set_panorama_skybox",
             [](easy3d::Scene& scene,
                const std::string& path,
                const float brightness,
                const float rotation) {
                 scene.set_panorama_skybox(path, brightness, rotation);
             },
             py::arg("path"), py::arg("brightness") = 1.0,
             py::arg("rotation") = 0.0)
        .def("set_cubemap_skybox",
             [](easy3d::Scene& scene,
                const std::array<std::string, 6>& paths,
                const float brightness,
                const float rotation) {
                 std::array<std::filesystem::path, 6> native_paths;
                 std::copy(paths.begin(), paths.end(), native_paths.begin());
                 scene.set_cubemap_skybox(native_paths, brightness, rotation);
             },
             py::arg("paths"), py::arg("brightness") = 1.0,
             py::arg("rotation") = 0.0)
        .def("clear_skybox", &easy3d::Scene::clear_skybox)
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
        .def("add_ui_element",
             [ui_kind, ui_anchor](easy3d::Scene& scene,
                                  const std::string& kind,
                                  const std::string& anchor,
                                  const std::array<float, 2>& position,
                                  const std::array<float, 2>& size,
                                  const std::array<float, 4>& color,
                                  const std::string& text,
                                  const std::array<float, 4>& text_color,
                                  const float font_size,
                                  const std::int32_t z_index,
                                  const bool visible,
                                  const bool enabled,
                                  const std::optional<std::string>& texture) {
                 easy3d::UiElement element;
                 element.kind = ui_kind(kind);
                 element.anchor = ui_anchor(anchor);
                 element.x = position[0];
                 element.y = position[1];
                 element.width = size[0];
                 element.height = size[1];
                 element.color = {color[0], color[1], color[2], color[3]};
                 element.text = text;
                 element.text_color = {
                     text_color[0], text_color[1], text_color[2], text_color[3]};
                 element.font_size = font_size;
                 element.z_index = z_index;
                 element.visible = visible;
                 element.enabled = enabled;
                 return scene.add_ui_element(
                     std::move(element),
                     texture.has_value()
                         ? std::optional<std::filesystem::path>(*texture)
                         : std::nullopt);
             },
             py::arg("kind"),
             py::arg("anchor"),
             py::arg("position"),
             py::arg("size"),
             py::arg("color"),
             py::arg("text") = "",
             py::arg("text_color") = std::array<float, 4>{1, 1, 1, 1},
             py::arg("font_size") = 24.0F,
             py::arg("z_index") = 0,
             py::arg("visible") = true,
             py::arg("enabled") = true,
             py::arg("texture") = std::nullopt)
        .def("ui_element_info",
             [ui_kind_name, ui_anchor_name](const easy3d::Scene& scene,
                                             const std::uint64_t id) {
                 const easy3d::UiElement& element = scene.ui_element(id);
                 py::object texture = py::none();
                 if (element.texture) {
                     texture = py::cast(element.texture->source_path.string());
                 }
                 return py::make_tuple(
                     ui_kind_name(element.kind),
                     ui_anchor_name(element.anchor),
                     py::make_tuple(element.x, element.y),
                     py::make_tuple(element.width, element.height),
                     py::make_tuple(element.color.r,
                                    element.color.g,
                                    element.color.b,
                                    element.color.a),
                     element.text,
                     py::make_tuple(element.text_color.r,
                                    element.text_color.g,
                                    element.text_color.b,
                                    element.text_color.a),
                     element.font_size,
                     element.z_index,
                     element.visible,
                     element.enabled,
                     texture);
             },
             py::arg("id"))
        .def("update_ui_element",
             [ui_anchor](easy3d::Scene& scene,
                         const std::uint64_t id,
                         const std::string& anchor,
                         const std::array<float, 2>& position,
                         const std::array<float, 2>& size,
                         const std::array<float, 4>& color,
                         const std::string& text,
                         const std::array<float, 4>& text_color,
                         const float font_size,
                         const std::int32_t z_index,
                         const bool visible,
                         const bool enabled) {
                 easy3d::UiElement element;
                 element.anchor = ui_anchor(anchor);
                 element.x = position[0];
                 element.y = position[1];
                 element.width = size[0];
                 element.height = size[1];
                 element.color = {color[0], color[1], color[2], color[3]};
                 element.text = text;
                 element.text_color = {
                     text_color[0], text_color[1], text_color[2], text_color[3]};
                 element.font_size = font_size;
                 element.z_index = z_index;
                 element.visible = visible;
                 element.enabled = enabled;
                 scene.update_ui_element(id, std::move(element));
             },
             py::arg("id"),
             py::arg("anchor"),
             py::arg("position"),
             py::arg("size"),
             py::arg("color"),
             py::arg("text"),
             py::arg("text_color"),
             py::arg("font_size"),
             py::arg("z_index"),
             py::arg("visible"),
             py::arg("enabled"))
        .def("set_ui_image",
             &easy3d::Scene::set_ui_image,
             py::arg("id"),
             py::arg("texture"))
        .def("remove_ui_element", &easy3d::Scene::remove_ui_element, py::arg("id"))
        .def("clear_ui", &easy3d::Scene::clear_ui)
        .def_property_readonly("ui_element_count", [](const easy3d::Scene& scene) {
            return scene.ui_elements().size();
        })
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

