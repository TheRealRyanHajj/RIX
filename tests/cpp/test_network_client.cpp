#include "easy3d/network.hpp"
#include "easy3d/network_protocol.hpp"

#include <steam/steamnetworkingsockets.h>

#include <array>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <memory>
#include <stdexcept>
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
class LocalHandshakeServer final {
public:
    explicit LocalHandshakeServer(const bool process_messages = true,
                                  const bool ipv6 = false)
        : runtime_(),
          sockets_(SteamNetworkingSockets()),
          process_messages_(process_messages) {
        std::array<SteamNetworkingConfigValue_t, 3> options;
        options[0].SetPtr(k_ESteamNetworkingConfig_Callback_ConnectionStatusChanged,
                          reinterpret_cast<void*>(&LocalHandshakeServer::status_callback));
        options[1].SetInt64(
            k_ESteamNetworkingConfig_ConnectionUserData,
            static_cast<std::int64_t>(reinterpret_cast<std::intptr_t>(this)));
        options[2].SetInt32(k_ESteamNetworkingConfig_RecvMaxMessageSize,
                            static_cast<std::int32_t>(
                                easy3d::detail::default_maximum_message_size));
        // GNS direct-IP listeners require an explicit nonzero port. Probe a
        // small test-only range and keep every listener alive so collisions
        // are detected rather than silently shared.
        for (std::uint16_t port = 32100; port < 32200; ++port) {
            SteamNetworkingIPAddr bind_address;
            if (ipv6) {
                bind_address.SetIPv6LocalHost(port);
            } else {
                bind_address.SetIPv4(0x7f000001U, port);
            }
            listen_ = sockets_->CreateListenSocketIP(
                bind_address, static_cast<int>(options.size()), options.data());
            if (listen_ != k_HSteamListenSocket_Invalid) {
                break;
            }
        }
        if (listen_ == k_HSteamListenSocket_Invalid ||
            !sockets_->GetListenSocketAddress(listen_, &bound_address_)) {
            throw std::runtime_error("could not create the localhost test listener");
        }
    }
    ~LocalHandshakeServer() {
        if (connection_ != k_HSteamNetConnection_Invalid) {
            static_cast<void>(sockets_->SetConnectionUserData(connection_, 0));
            static_cast<void>(sockets_->CloseConnection(
                connection_, 0, "test listener shutdown", false));
        }
        if (listen_ != k_HSteamListenSocket_Invalid) {
            static_cast<void>(sockets_->CloseListenSocket(listen_));
        }
    }

    LocalHandshakeServer(const LocalHandshakeServer&) = delete;
    LocalHandshakeServer& operator=(const LocalHandshakeServer&) = delete;

    [[nodiscard]] std::uint16_t port() const noexcept {
        return bound_address_.m_port;
    }

    [[nodiscard]] bool established() const noexcept { return established_; }

    void poll() {
        sockets_->RunCallbacks();
        if (!process_messages_ || connection_ == k_HSteamNetConnection_Invalid) {
            return;
        }
        for (;;) {
            std::array<SteamNetworkingMessage_t*, 8> messages{};
            const int count = sockets_->ReceiveMessagesOnConnection(
                connection_, messages.data(), static_cast<int>(messages.size()));
            if (count <= 0) {
                return;
            }
            for (int index = 0; index < count; ++index) {
                SteamNetworkingMessage_t* const message = messages[index];
                if (message == nullptr) {
                    continue;
                }
                if (!established_) {
                    handle_handshake(*message);
                } else {
                    const int flags =
                        (message->m_nFlags & k_nSteamNetworkingSend_Reliable) != 0
                            ? k_nSteamNetworkingSend_Reliable
                            : k_nSteamNetworkingSend_Unreliable;
                    static_cast<void>(sockets_->SendMessageToConnection(
                        connection_,
                        message->m_pData,
                        static_cast<std::uint32_t>(message->m_cbSize),
                        flags,
                        nullptr));
                }
                message->Release();
            }
        }
    }

    void send_to_client(const std::vector<std::uint8_t>& payload,
                        const bool reliable = true) {
        if (!established_ || connection_ == k_HSteamNetConnection_Invalid) {
            throw std::logic_error("test server has no established client");
        }
        const EResult result = sockets_->SendMessageToConnection(
            connection_,
            payload.data(),
            static_cast<std::uint32_t>(payload.size()),
            reliable ? k_nSteamNetworkingSend_Reliable
                     : k_nSteamNetworkingSend_Unreliable,
            nullptr);
        if (result != k_EResultOK) {
            throw std::runtime_error("test server could not send a message");
        }
    }

private:
    static void status_callback(SteamNetConnectionStatusChangedCallback_t* info) {
        if (info == nullptr) {
            return;
        }
        ISteamNetworkingSockets* const sockets = SteamNetworkingSockets();
        const std::int64_t raw_owner =
            sockets == nullptr ? 0 : sockets->GetConnectionUserData(info->m_hConn);
        if (raw_owner == 0 || raw_owner == -1) {
            return;
        }
        auto* const owner = reinterpret_cast<LocalHandshakeServer*>(
            static_cast<std::intptr_t>(raw_owner));
        owner->on_status(*info);
    }

    void on_status(const SteamNetConnectionStatusChangedCallback_t& info) {
        switch (info.m_info.m_eState) {
        case k_ESteamNetworkingConnectionState_Connecting:
            if (connection_ != k_HSteamNetConnection_Invalid) {
                static_cast<void>(sockets_->CloseConnection(
                    info.m_hConn, 1000, "test listener already has a client", false));
                return;
            }
            connection_ = info.m_hConn;
            static_cast<void>(sockets_->SetConnectionUserData(
                connection_,
                static_cast<std::int64_t>(reinterpret_cast<std::intptr_t>(this))));
            handshake_ = std::make_unique<easy3d::detail::ProtocolHandshake>(
                easy3d::detail::HandshakeConfig{
                    easy3d::detail::NetworkRole::Server});
            static_cast<void>(handshake_->start());
            if (sockets_->AcceptConnection(connection_) != k_EResultOK) {
                static_cast<void>(sockets_->CloseConnection(
                    connection_, 1008, "test listener could not accept", false));
                connection_ = k_HSteamNetConnection_Invalid;
                handshake_.reset();
            }
            return;
        case k_ESteamNetworkingConnectionState_ClosedByPeer:
        case k_ESteamNetworkingConnectionState_ProblemDetectedLocally:
            static_cast<void>(sockets_->SetConnectionUserData(info.m_hConn, 0));
            static_cast<void>(sockets_->CloseConnection(
                info.m_hConn, 0, nullptr, false));
            if (connection_ == info.m_hConn) {
                connection_ = k_HSteamNetConnection_Invalid;
                handshake_.reset();
                established_ = false;
            }
            return;
        default:
            return;
        }
    }

    void handle_handshake(const SteamNetworkingMessage_t& message) {
        if (handshake_ == nullptr ||
            (message.m_nFlags & k_nSteamNetworkingSend_Reliable) == 0 ||
            message.m_cbSize < 0) {
            throw std::runtime_error("test server received an invalid handshake");
        }
        const auto payload = std::span(
            static_cast<const std::uint8_t*>(message.m_pData),
            static_cast<std::size_t>(message.m_cbSize));
        easy3d::detail::HandshakeUpdate update = handshake_->receive(payload);
        if (!update.outbound.empty()) {
            if (sockets_->SendMessageToConnection(
                    connection_,
                    update.outbound.data(),
                    static_cast<std::uint32_t>(update.outbound.size()),
                    k_nSteamNetworkingSend_Reliable,
                    nullptr) != k_EResultOK) {
                throw std::runtime_error("test server could not send handshake response");
            }
        }
        if (update.disconnect_code != easy3d::detail::DisconnectCode::None) {
            static_cast<void>(sockets_->CloseConnection(
                connection_,
                static_cast<int>(update.disconnect_code),
                update.reason.c_str(),
                true));
            return;
        }
        established_ = update.established;
    }

    easy3d::NetworkBackendRuntime runtime_;
    ISteamNetworkingSockets* sockets_{nullptr};
    HSteamListenSocket listen_{k_HSteamListenSocket_Invalid};
    HSteamNetConnection connection_{k_HSteamNetConnection_Invalid};
    SteamNetworkingIPAddr bound_address_{};
    bool process_messages_{true};
    bool established_{false};
    std::unique_ptr<easy3d::detail::ProtocolHandshake> handshake_;
};

std::vector<easy3d::TransportEvent> wait_for_connection(
    easy3d::NetworkClient& client,
    LocalHandshakeServer& server,
    const std::chrono::milliseconds limit = 2000ms) {
    std::vector<easy3d::TransportEvent> observed;
    const auto deadline = std::chrono::steady_clock::now() + limit;
    while (std::chrono::steady_clock::now() < deadline) {
        server.poll();
        auto events = client.poll(16);
        observed.insert(observed.end(), events.begin(), events.end());
        server.poll();
        if (client.state() == easy3d::NetworkClientState::Connected &&
            server.established()) {
            return observed;
        }
        std::this_thread::sleep_for(1ms);
    }
    return observed;
}
std::vector<easy3d::TransportEvent> wait_for_messages(
    easy3d::NetworkClient& client,
    LocalHandshakeServer& server,
    const std::size_t count) {
    std::vector<easy3d::TransportEvent> observed;
    const auto deadline = std::chrono::steady_clock::now() + 2000ms;
    while (std::chrono::steady_clock::now() < deadline) {
        server.poll();
        auto events = client.poll(16);
        for (auto& event : events) {
            if (event.type == easy3d::TransportEventType::Message) {
                observed.push_back(std::move(event));
            }
        }
        if (observed.size() >= count) {
            return observed;
        }
        std::this_thread::sleep_for(1ms);
    }
    return observed;
}
} // namespace

int main() {
    try {
        try {
            easy3d::NetworkClientConfig invalid;
            invalid.connection_timeout_seconds = 0.0;
            easy3d::NetworkClient client(invalid);
            return fail(1, "zero client timeout was accepted");
        } catch (const std::invalid_argument&) {
            // Expected.
        }
        try {
            easy3d::NetworkClientConfig invalid;
            invalid.peer_timeout_seconds = 0.0;
            easy3d::NetworkClient client(invalid);
            return fail(22, "zero client peer timeout was accepted");
        } catch (const std::invalid_argument&) {
            // Expected.
        }

        LocalHandshakeServer server;
        easy3d::NetworkClientConfig config;
        config.connection_timeout_seconds = 2.0;
        config.event_queue_capacity = 8;
        config.maximum_message_size = 64;
        easy3d::NetworkClient client(config);

        try {
            client.connect("not-an-ip", server.port());
            return fail(2, "non-numeric address was accepted");
        } catch (const std::invalid_argument&) {
            // Expected.
        }
        try {
            client.connect("127.0.0.1:32100", server.port());
            return fail(17, "address text containing a second port was accepted");
        } catch (const std::invalid_argument&) {
            // Expected.
        }
        try {
            client.connect("127.0.0.1", 0);
            return fail(3, "zero remote port was accepted");
        } catch (const std::invalid_argument&) {
            // Expected.
        }

        client.connect("127.0.0.1", server.port());
        if (client.state() != easy3d::NetworkClientState::Connecting ||
            !client.connection().valid() || client.remote_address().empty()) {
            return fail(4, "client did not enter connecting state with diagnostics");
        }
        const auto connect_events = wait_for_connection(client, server);
        if (connect_events.size() != 1 ||
            connect_events[0].type != easy3d::TransportEventType::Connected ||
            connect_events[0].connection != client.connection()) {
            return fail(5, "client did not publish exactly one connected event");
        }

        const easy3d::NetworkConnectionMetrics connected_metrics = client.metrics();
        if (connected_metrics.state != easy3d::NetworkClientState::Connected ||
            connected_metrics.negotiated_maximum_message_size != 64 ||
            connected_metrics.transport != client.stats()) {
            return fail(6, "connected client metrics are inconsistent");
        }

        if (client.send(client.connection(),
                        std::vector<std::uint8_t>(65, 1),
                        easy3d::NetworkDelivery::Reliable) !=
                easy3d::SendStatus::MessageTooLarge ||
            client.send(easy3d::ConnectionId{999},
                        bytes("wrong"),
                        easy3d::NetworkDelivery::Reliable) !=
                easy3d::SendStatus::InvalidConnection) {
            return fail(7, "client send bounds or connection validation failed");
        }

        const std::vector<std::uint8_t> reliable = bytes("reliable");
        const std::vector<std::uint8_t> unreliable = bytes("unreliable");
        if (client.send(client.connection(),
                        reliable,
                        easy3d::NetworkDelivery::Reliable) !=
                easy3d::SendStatus::Queued ||
            client.send(client.connection(),
                        unreliable,
                        easy3d::NetworkDelivery::Unreliable) !=
                easy3d::SendStatus::Queued) {
            return fail(8, "client could not queue application messages");
        }
        const auto echoed = wait_for_messages(client, server, 2);
        if (echoed.size() != 2 || echoed[0].payload != reliable ||
            echoed[0].delivery != easy3d::NetworkDelivery::Reliable ||
            echoed[1].payload != unreliable ||
            echoed[1].delivery != easy3d::NetworkDelivery::Unreliable) {
            return fail(9, "localhost echo delivery or metadata is incorrect");
        }
        const easy3d::TransportStats stats = client.stats();
        if (stats.messages_sent != 2 || stats.messages_received != 2 ||
            stats.bytes_sent != reliable.size() + unreliable.size() ||
            stats.bytes_received != reliable.size() + unreliable.size() ||
            stats.queue_rejections != 2) {
            return fail(10, "client transport counters are incorrect");
        }

        try {
            client.disconnect(client.connection(), "bad\nreason");
            return fail(11, "control characters were accepted in disconnect reason");
        } catch (const std::invalid_argument&) {
            // Expected.
        }
        const easy3d::ConnectionId disconnected_id = client.connection();
        client.disconnect(disconnected_id, "test complete");
        const auto disconnect_events = client.poll(4);
        if (disconnect_events.size() != 1 ||
            disconnect_events[0].type != easy3d::TransportEventType::Disconnected ||
            disconnect_events[0].connection != disconnected_id ||
            disconnect_events[0].reason != "test complete" ||
            disconnect_events[0].disconnect_code !=
                static_cast<std::uint16_t>(easy3d::detail::DisconnectCode::Normal) ||
            client.state() != easy3d::NetworkClientState::Disconnected ||
            client.connection().valid()) {
            return fail(12, "clean client disconnect event is incorrect");
        }

        LocalHandshakeServer ipv6_server(true, true);
        easy3d::NetworkClient ipv6_client(config);
        ipv6_client.connect("::1", ipv6_server.port());
        const auto ipv6_events = wait_for_connection(ipv6_client, ipv6_server);
        if (ipv6_events.size() != 1 ||
            ipv6_client.state() != easy3d::NetworkClientState::Connected ||
            ipv6_client.remote_address().find("[::1]:") != 0) {
            return fail(16, "numeric IPv6 localhost connection failed");
        }
        ipv6_client.disconnect(ipv6_client.connection(), "IPv6 complete");
        static_cast<void>(ipv6_client.poll(1));

        LocalHandshakeServer silent_server(false);
        easy3d::NetworkClientConfig timeout_config;
        timeout_config.connection_timeout_seconds = 0.05;
        easy3d::NetworkClient timeout_client(timeout_config);
        timeout_client.connect("127.0.0.1", silent_server.port());
        std::vector<easy3d::TransportEvent> timeout_events;
        const auto timeout_deadline = std::chrono::steady_clock::now() + 2000ms;
        while (std::chrono::steady_clock::now() < timeout_deadline &&
               timeout_events.empty()) {
            silent_server.poll();
            timeout_events = timeout_client.poll(4);
            std::this_thread::sleep_for(1ms);
        }
        if (timeout_events.size() != 1 ||
            timeout_events[0].type != easy3d::TransportEventType::Disconnected ||
            timeout_events[0].disconnect_code != static_cast<std::uint16_t>(
                easy3d::detail::DisconnectCode::ConnectionTimeout) ||
            timeout_client.state() != easy3d::NetworkClientState::Disconnected ||
            timeout_client.connection().valid()) {
            return fail(13, "silent peer did not trigger the bounded handshake timeout");
        }

        LocalHandshakeServer overflow_server;
        easy3d::NetworkClientConfig overflow_config;
        overflow_config.event_queue_capacity = 1;
        easy3d::NetworkClient overflow_client(overflow_config);
        overflow_client.connect("127.0.0.1", overflow_server.port());
        if (wait_for_connection(overflow_client, overflow_server).size() != 1) {
            return fail(14, "overflow-test client could not connect");
        }
        overflow_server.send_to_client(bytes("one"));
        overflow_server.send_to_client(bytes("two"));
        bool overflow_reported = false;
        const auto overflow_deadline = std::chrono::steady_clock::now() + 2000ms;
        while (std::chrono::steady_clock::now() < overflow_deadline &&
               !overflow_reported) {
            overflow_server.poll();
            try {
                static_cast<void>(overflow_client.poll(1));
            } catch (const easy3d::NetworkError&) {
                overflow_reported = true;
            }
            std::this_thread::sleep_for(1ms);
        }
        if (!overflow_reported || overflow_client.stats().event_overflows != 1 ||
            overflow_client.poll(1).size() != 1) {
            return fail(15, "client event overflow was not bounded and recoverable");
        }

        std::cout << "easy3d_network_client_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "easy3d_network_client_tests: FAIL: " << error.what() << '\n';
        return 99;
    }
}
