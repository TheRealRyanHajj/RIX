#include "easy3d/network.hpp"
#include "easy3d/network_protocol.hpp"

#include <steam/steamnetworkingsockets.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <memory>
#include <string>
#include <thread>
#include <vector>

namespace {

using namespace std::chrono_literals;

int fail(const int code, const char* const message) {
    std::cerr << message << '\n';
    return code;
}
std::vector<std::uint8_t> bytes(const std::string& value) {
    return {value.begin(), value.end()};
}
std::unique_ptr<easy3d::NetworkServer> listening_server(
    easy3d::NetworkServerConfig config) {
    for (std::uint16_t port = 32200; port < 32300; ++port) {
        config.port = port;
        auto server = std::make_unique<easy3d::NetworkServer>(config);
        try {
            server->start();
            return server;
        } catch (const easy3d::NetworkError&) {
            // A concurrently running test or local service owns this port.
        }
    }
    throw std::runtime_error("could not bind a localhost server test port");
}
std::vector<easy3d::TransportEvent> connect_clients(
    easy3d::NetworkServer& server,
    const std::vector<easy3d::NetworkClient*>& clients,
    const std::chrono::milliseconds timeout = 2000ms) {
    std::vector<easy3d::TransportEvent> server_events;
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    while (std::chrono::steady_clock::now() < deadline) {
        auto events = server.poll(32);
        server_events.insert(server_events.end(), events.begin(), events.end());
        bool ready = true;
        for (easy3d::NetworkClient* const client : clients) {
            static_cast<void>(client->poll(32));
            ready = ready &&
                    client->state() == easy3d::NetworkClientState::Connected;
        }
        if (ready && server.connections().size() == clients.size()) {
            return server_events;
        }
        std::this_thread::sleep_for(1ms);
    }
    return server_events;
}
std::vector<easy3d::TransportEvent> wait_for_server_messages(
    easy3d::NetworkServer& server,
    const std::size_t count) {
    std::vector<easy3d::TransportEvent> result;
    const auto deadline = std::chrono::steady_clock::now() + 2000ms;
    while (std::chrono::steady_clock::now() < deadline) {
        for (auto& event : server.poll(32)) {
            if (event.type == easy3d::TransportEventType::Message) {
                result.push_back(std::move(event));
            }
        }
        if (result.size() >= count) {
            return result;
        }
        std::this_thread::sleep_for(1ms);
    }
    return result;
}
std::vector<easy3d::TransportEvent> wait_for_client_events(
    easy3d::NetworkClient& client,
    const std::size_t count) {
    std::vector<easy3d::TransportEvent> result;
    const auto deadline = std::chrono::steady_clock::now() + 2000ms;
    while (std::chrono::steady_clock::now() < deadline) {
        auto events = client.poll(32);
        result.insert(result.end(), events.begin(), events.end());
        if (result.size() >= count) {
            return result;
        }
        std::this_thread::sleep_for(1ms);
    }
    return result;
}
std::atomic_bool raw_connected{false};
std::atomic_int raw_end_reason{0};

void raw_status_callback(SteamNetConnectionStatusChangedCallback_t* info) {
    if (info == nullptr) {
        return;
    }
    if (info->m_info.m_eState == k_ESteamNetworkingConnectionState_Connected) {
        raw_connected.store(true);
    } else if (info->m_info.m_eState ==
                   k_ESteamNetworkingConnectionState_ClosedByPeer ||
               info->m_info.m_eState ==
                   k_ESteamNetworkingConnectionState_ProblemDetectedLocally) {
        raw_end_reason.store(info->m_info.m_eEndReason);
    }
}
} // namespace

int main() {
    try {
        try {
            easy3d::NetworkServerConfig invalid;
            invalid.maximum_connections = 0;
            easy3d::NetworkServer server(invalid);
            return fail(1, "zero server connection limit was accepted");
        } catch (const std::invalid_argument&) {
            // Expected.
        }
        try {
            easy3d::NetworkServerConfig invalid;
            invalid.peer_timeout_seconds = 0.0;
            easy3d::NetworkServer server(invalid);
            return fail(22, "zero server peer timeout was accepted");
        } catch (const std::invalid_argument&) {
            // Expected.
        }

        easy3d::NetworkServerConfig config;
        config.bind_address = "127.0.0.1";
        config.maximum_connections = 2;
        config.handshake_timeout_seconds = 0.05;
        config.event_queue_capacity = 16;
        config.maximum_message_size = 64;
        auto server = listening_server(config);
        if (server->state() != easy3d::NetworkServerState::Listening ||
            server->port() == 0 || server->bind_address().empty()) {
            return fail(2, "server did not publish its bound listener state");
        }

        try {
            server->start();
            return fail(3, "an already-listening server started twice");
        } catch (const easy3d::NetworkError&) {
            // Expected.
        }

        easy3d::NetworkClientConfig client_config;
        client_config.connection_timeout_seconds = 1.0;
        client_config.maximum_message_size = 64;
        easy3d::NetworkClient first(client_config);
        easy3d::NetworkClient second(client_config);
        first.connect("127.0.0.1", server->port());
        second.connect("127.0.0.1", server->port());
        const auto connected = connect_clients(*server, {&first, &second});
        if (connected.size() != 2 ||
            connected[0].type != easy3d::TransportEventType::Connected ||
            connected[1].type != easy3d::TransportEventType::Connected ||
            connected[0].connection == connected[1].connection ||
            server->connections().size() != 2) {
            return fail(4, "server did not establish two distinct clients");
        }

        const std::vector<std::uint8_t> reliable = bytes("alpha");
        const std::vector<std::uint8_t> unreliable = bytes("beta");
        if (first.send(first.connection(),
                       reliable,
                       easy3d::NetworkDelivery::Reliable) !=
                easy3d::SendStatus::Queued ||
            second.send(second.connection(),
                        unreliable,
                        easy3d::NetworkDelivery::Unreliable) !=
                easy3d::SendStatus::Queued) {
            return fail(5, "clients could not queue messages for the server");
        }
        const auto messages = wait_for_server_messages(*server, 2);
        const auto reliable_event = std::find_if(
            messages.begin(), messages.end(), [&](const easy3d::TransportEvent& event) {
                return event.payload == reliable;
            });
        const auto unreliable_event = std::find_if(
            messages.begin(), messages.end(), [&](const easy3d::TransportEvent& event) {
                return event.payload == unreliable;
            });
        if (messages.size() != 2 || reliable_event == messages.end() ||
            reliable_event->delivery != easy3d::NetworkDelivery::Reliable ||
            unreliable_event == messages.end() ||
            unreliable_event->delivery != easy3d::NetworkDelivery::Unreliable) {
            return fail(6, "server did not preserve client payload delivery metadata");
        }
        for (const easy3d::TransportEvent& event : messages) {
            if (server->send(event.connection, event.payload, event.delivery) !=
                easy3d::SendStatus::Queued) {
                return fail(7, "server could not reply to an established client");
            }
        }
        const auto first_reply = wait_for_client_events(first, 1);
        const auto second_reply = wait_for_client_events(second, 1);
        if (first_reply.size() != 1 || first_reply[0].payload != reliable ||
            second_reply.size() != 1 || second_reply[0].payload != unreliable) {
            return fail(8, "clients did not receive exact server replies");
        }
        if (server->send(easy3d::ConnectionId{9999},
                         bytes("invalid"),
                         easy3d::NetworkDelivery::Reliable) !=
                easy3d::SendStatus::InvalidConnection ||
            server->send(messages[0].connection,
                         std::vector<std::uint8_t>(65, 1),
                         easy3d::NetworkDelivery::Reliable) !=
                easy3d::SendStatus::MessageTooLarge) {
            return fail(9, "server send bounds or connection validation failed");
        }

        easy3d::NetworkClient third(client_config);
        third.connect("127.0.0.1", server->port());
        const auto third_events = wait_for_client_events(third, 1);
        if (third_events.size() != 1 ||
            third_events[0].type != easy3d::TransportEventType::Disconnected ||
            third_events[0].disconnect_code != static_cast<std::uint16_t>(
                easy3d::detail::DisconnectCode::ServerFull)) {
            return fail(10, "server connection limit did not reject the third client");
        }

        const easy3d::ConnectionId first_server_id = reliable_event->connection;
        const easy3d::ConnectionId second_server_id = unreliable_event->connection;
        server->disconnect(first_server_id, "test removal");
        const auto local_disconnect = server->poll(8);
        if (local_disconnect.size() != 1 ||
            local_disconnect[0].type !=
                easy3d::TransportEventType::Disconnected ||
            local_disconnect[0].connection != first_server_id ||
            server->connections().size() != 1) {
            return fail(11, "server-side disconnect did not clean up exactly one peer");
        }
        const auto remote_clean_disconnect = wait_for_client_events(first, 1);
        if (remote_clean_disconnect.size() != 1 ||
            remote_clean_disconnect[0].type !=
                easy3d::TransportEventType::Disconnected ||
            remote_clean_disconnect[0].disconnect_code !=
                static_cast<std::uint16_t>(
                    easy3d::detail::DisconnectCode::Normal)) {
            return fail(18, "server graceful close code was not preserved remotely");
        }

        easy3d::NetworkClientConfig mismatch_config = client_config;
        mismatch_config.protocol_version = 2;
        easy3d::NetworkClient mismatch(mismatch_config);
        mismatch.connect("127.0.0.1", server->port());
        std::vector<easy3d::TransportEvent> mismatch_events;
        const auto mismatch_deadline = std::chrono::steady_clock::now() + 2000ms;
        while (std::chrono::steady_clock::now() < mismatch_deadline &&
               mismatch_events.empty()) {
            static_cast<void>(server->poll(8));
            mismatch_events = mismatch.poll(8);
            std::this_thread::sleep_for(1ms);
        }
        if (mismatch_events.size() != 1 ||
            mismatch_events[0].disconnect_code != static_cast<std::uint16_t>(
                easy3d::detail::DisconnectCode::ProtocolVersionMismatch) ||
            server->connections().size() != 1) {
            return fail(12, "server did not reject a mismatched protocol handshake");
        }

        // A raw GNS client that never sends Easy3D's hello must be removed by
        // the server-owned handshake deadline without becoming an app player.
        SteamNetworkingIPAddr raw_address;
        raw_address.SetIPv4(0x7f000001U, server->port());
        SteamNetworkingConfigValue_t raw_callback;
        raw_callback.SetPtr(k_ESteamNetworkingConfig_Callback_ConnectionStatusChanged,
                            reinterpret_cast<void*>(&raw_status_callback));
        ISteamNetworkingSockets* const sockets = SteamNetworkingSockets();
        const HSteamNetConnection raw = sockets->ConnectByIPAddress(
            raw_address, 1, &raw_callback);
        if (raw == k_HSteamNetConnection_Invalid) {
            return fail(13, "could not create the silent raw client");
        }
        const auto timeout_deadline = std::chrono::steady_clock::now() + 2000ms;
        while (std::chrono::steady_clock::now() < timeout_deadline &&
               raw_end_reason.load() == 0) {
            static_cast<void>(server->poll(8));
            sockets->RunCallbacks();
            std::this_thread::sleep_for(1ms);
        }
        static_cast<void>(sockets->SetConnectionUserData(raw, 0));
        static_cast<void>(sockets->CloseConnection(raw, 0, nullptr, false));
        if (!raw_connected.load() ||
            raw_end_reason.load() != static_cast<int>(
                easy3d::detail::DisconnectCode::ConnectionTimeout) ||
            server->connections().size() != 1) {
            return fail(14, "silent pre-handshake connection did not time out cleanly");
        }

        second.disconnect(second.connection(), "client complete");
        std::vector<easy3d::TransportEvent> client_close_events;
        const auto client_close_deadline =
            std::chrono::steady_clock::now() + 2000ms;
        while (std::chrono::steady_clock::now() < client_close_deadline &&
               client_close_events.empty()) {
            client_close_events = server->poll(8);
            std::this_thread::sleep_for(1ms);
        }
        if (client_close_events.size() != 1 ||
            client_close_events[0].connection != second_server_id ||
            client_close_events[0].disconnect_code !=
                static_cast<std::uint16_t>(
                    easy3d::detail::DisconnectCode::Normal)) {
            return fail(19, "client graceful close code was not preserved by server");
        }

        easy3d::NetworkClient final_client(client_config);
        final_client.connect("127.0.0.1", server->port());
        const auto final_connect = connect_clients(*server, {&final_client});
        if (final_connect.size() != 1 || server->connections().size() != 1) {
            return fail(20, "final shutdown-test client did not connect");
        }

        server->stop("test shutdown");
        const auto stop_events = server->poll(8);
        if (server->state() != easy3d::NetworkServerState::Stopped ||
            server->port() != 0 || server->connections().size() != 0 ||
            stop_events.size() != 1 ||
            stop_events[0].disconnect_code != static_cast<std::uint16_t>(
                easy3d::detail::DisconnectCode::ServerStopped)) {
            return fail(15, "server stop did not close and publish the final client");
        }
        server->start();
        if (server->state() != easy3d::NetworkServerState::Listening) {
            return fail(16, "server could not restart after draining stop events");
        }
        server->stop();
        static_cast<void>(server->poll(8));

        const easy3d::TransportStats stats = server->stats();
        if (stats.messages_sent != 0 || stats.messages_received != 0) {
            return fail(17, "server restart did not reset transport counters");
        }

        std::cout << "easy3d_network_server_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "easy3d_network_server_tests: FAIL: " << error.what() << '\n';
        return 99;
    }
}
