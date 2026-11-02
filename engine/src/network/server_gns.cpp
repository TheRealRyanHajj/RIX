#include "easy3d/network.hpp"

#include "easy3d/network_protocol.hpp"

#include <steam/steamnetworkingsockets.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string_view>
#include <unordered_map>
#include <utility>

namespace easy3d {
namespace {

constexpr std::size_t maximum_transport_messages_per_poll = 256;
constexpr std::size_t receive_batch_size = 32;
constexpr std::size_t maximum_transport_close_reason_size = 120;
constexpr std::size_t hard_maximum_server_connections = 1024;
constexpr int graceful_transport_close_reason = 1011;

NetworkServerConfig validate_server_config(NetworkServerConfig config) {
    if (config.bind_address.empty() || config.port == 0) {
        throw std::invalid_argument("server bind address and port are required");
    }
    if (config.maximum_connections == 0 ||
        config.maximum_connections > hard_maximum_server_connections) {
        throw std::invalid_argument("server connection limit must be between 1 and 1024");
    }
    if (!std::isfinite(config.handshake_timeout_seconds) ||
        config.handshake_timeout_seconds <= 0.0) {
        throw std::invalid_argument("server handshake timeout must be finite and positive");
    }
    if (!std::isfinite(config.peer_timeout_seconds) ||
        config.peer_timeout_seconds < 0.001 ||
        config.peer_timeout_seconds >
            static_cast<double>(std::numeric_limits<std::int32_t>::max()) / 1000.0) {
        throw std::invalid_argument(
            "server peer timeout must be between 1 ms and INT32_MAX ms");
    }
    if (config.event_queue_capacity == 0) {
        throw std::invalid_argument("server event queue capacity must be positive");
    }
    if (config.maximum_message_size == 0 ||
        config.maximum_message_size > detail::hard_maximum_message_size) {
        throw std::invalid_argument("server message-size limit is invalid");
    }
    if (config.protocol_version == 0 || config.schema_version == 0) {
        throw std::invalid_argument("server protocol and schema versions must be nonzero");
    }
    return config;
}

bool valid_close_reason(const std::string_view reason) {
    if (reason.size() > maximum_transport_close_reason_size) {
        return false;
    }
    for (const unsigned char byte : reason) {
        if (byte == 0 || byte < 0x20U || byte == 0x7fU) {
            return false;
        }
    }
    return true;
}

std::string safe_transport_debug(const char* const text,
                                 const std::string_view fallback) {
    std::string output = text == nullptr ? std::string{} : std::string{text};
    if (output.size() > detail::maximum_disconnect_reason_size) {
        output.resize(detail::maximum_disconnect_reason_size);
    }
    for (char& value : output) {
        const unsigned char byte = static_cast<unsigned char>(value);
        if (byte < 0x20U || byte == 0x7fU) {
            value = '?';
        }
    }
    return output.empty() ? std::string{fallback} : output;
}

int send_flags(const NetworkDelivery delivery) {
    return delivery == NetworkDelivery::Reliable ? k_nSteamNetworkingSend_Reliable
                                                  : k_nSteamNetworkingSend_Unreliable;
}

} // namespace

struct NetworkServer::Impl final {
    struct Peer final {
        HSteamNetConnection handle{k_HSteamNetConnection_Invalid};
        ConnectionId connection;
        std::string remote_address;
        std::unique_ptr<detail::ProtocolHandshake> handshake;
        std::chrono::steady_clock::time_point deadline{};
        std::uint32_t negotiated_maximum_message_size{0};
        bool established{false};
    };

    explicit Impl(NetworkServerConfig input)
        : config(std::move(input)),
          runtime(),
          sockets(SteamNetworkingSockets()),
          events(config.event_queue_capacity) {
        if (sockets == nullptr || !runtime.ready()) {
            throw NetworkError("GameNetworkingSockets server runtime is unavailable");
        }
    }

    ~Impl() {
        try {
            shutdown(false, "server destroyed");
        } catch (...) {
            // Destruction must not throw. User data is cleared by close_peer
            // before any native handle is released.
        }
    }

    static void status_callback(SteamNetConnectionStatusChangedCallback_t* info) {
        if (info == nullptr) {
            return;
        }
        ISteamNetworkingSockets* const interface_pointer = SteamNetworkingSockets();
        if (interface_pointer == nullptr) {
            return;
        }
        const std::int64_t raw_owner =
            interface_pointer->GetConnectionUserData(info->m_hConn);
        if (raw_owner == 0 || raw_owner == -1) {
            return;
        }
        auto* const owner = reinterpret_cast<Impl*>(
            static_cast<std::intptr_t>(raw_owner));
        owner->on_status_changed(*info);
    }

    void start() {
        if (state != NetworkServerState::Stopped ||
            listen_socket != k_HSteamListenSocket_Invalid) {
            throw NetworkError("network server is already listening");
        }
        if (!peers.empty()) {
            throw NetworkError("network server still owns peer connections");
        }
        if (events.size() != 0) {
            throw NetworkError("poll pending server events before restarting");
        }

        SteamNetworkingIPAddr address;
        address.Clear();
        if (!address.ParseString(config.bind_address.c_str()) || address.m_port != 0) {
            throw std::invalid_argument(
                "server bind address must be a numeric IPv4 or IPv6 host without a port");
        }
        address.m_port = config.port;

        poll_group = sockets->CreatePollGroup();
        if (poll_group == k_HSteamNetPollGroup_Invalid) {
            throw NetworkError("could not create the server network poll group");
        }

        std::array<SteamNetworkingConfigValue_t, 4> options;
        options[0].SetPtr(k_ESteamNetworkingConfig_Callback_ConnectionStatusChanged,
                          reinterpret_cast<void*>(&Impl::status_callback));
        options[1].SetInt64(
            k_ESteamNetworkingConfig_ConnectionUserData,
            static_cast<std::int64_t>(reinterpret_cast<std::intptr_t>(this)));
        options[2].SetInt32(
            k_ESteamNetworkingConfig_RecvMaxMessageSize,
            static_cast<std::int32_t>(std::max<std::size_t>(
                config.maximum_message_size, detail::maximum_handshake_frame_size)));
        options[3].SetInt32(
            k_ESteamNetworkingConfig_TimeoutConnected,
            static_cast<std::int32_t>(config.peer_timeout_seconds * 1000.0));

        listen_socket = sockets->CreateListenSocketIP(
            address, static_cast<int>(options.size()), options.data());
        if (listen_socket == k_HSteamListenSocket_Invalid) {
            static_cast<void>(sockets->DestroyPollGroup(poll_group));
            poll_group = k_HSteamNetPollGroup_Invalid;
            throw NetworkError("could not bind the server listen socket");
        }

        SteamNetworkingIPAddr bound;
        if (!sockets->GetListenSocketAddress(listen_socket, &bound)) {
            static_cast<void>(sockets->CloseListenSocket(listen_socket));
            listen_socket = k_HSteamListenSocket_Invalid;
            static_cast<void>(sockets->DestroyPollGroup(poll_group));
            poll_group = k_HSteamNetPollGroup_Invalid;
            throw NetworkError("could not query the server listen address");
        }
        char normalized[SteamNetworkingIPAddr::k_cchMaxString]{};
        bound.ToString(normalized, sizeof(normalized), true);
        bound_address = normalized;
        bound_port = bound.m_port;
        state = NetworkServerState::Listening;
        statistics = {};
        overflow_pending = false;
    }

    void reject_raw_connection(const HSteamNetConnection connection,
                               const detail::DisconnectCode code,
                               const char* const reason) {
        static_cast<void>(sockets->SetConnectionUserData(connection, 0));
        static_cast<void>(sockets->CloseConnection(
            connection, static_cast<int>(code), reason, false));
    }

    void accept_connection(const SteamNetConnectionStatusChangedCallback_t& info) {
        if (state != NetworkServerState::Listening ||
            peers.size() >= config.maximum_connections) {
            reject_raw_connection(info.m_hConn,
                                  detail::DisconnectCode::ServerFull,
                                  "server connection limit reached");
            return;
        }

        if (++connection_generation == 0) {
            ++connection_generation;
        }
        Peer peer;
        peer.handle = info.m_hConn;
        peer.connection = ConnectionId{connection_generation};
        char remote_text[SteamNetworkingIPAddr::k_cchMaxString]{};
        info.m_info.m_addrRemote.ToString(remote_text, sizeof(remote_text), true);
        peer.remote_address = remote_text;
        peer.handshake = std::make_unique<detail::ProtocolHandshake>(
            detail::HandshakeConfig{detail::NetworkRole::Server,
                                    config.protocol_version,
                                    config.schema_version,
                                    static_cast<std::uint32_t>(
                                        config.maximum_message_size)});
        static_cast<void>(peer.handshake->start());
        peer.deadline = std::chrono::steady_clock::now() +
                        std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                            std::chrono::duration<double>(
                                config.handshake_timeout_seconds));
        peers.emplace(info.m_hConn, std::move(peer));
        static_cast<void>(sockets->SetConnectionUserData(
            info.m_hConn,
            static_cast<std::int64_t>(reinterpret_cast<std::intptr_t>(this))));

        if (sockets->AcceptConnection(info.m_hConn) != k_EResultOK ||
            !sockets->SetConnectionPollGroup(info.m_hConn, poll_group)) {
            close_peer(info.m_hConn,
                       detail::DisconnectCode::TransportFailure,
                       "server could not accept the connection",
                       false,
                       false);
        }
    }

    void on_status_changed(const SteamNetConnectionStatusChangedCallback_t& info) {
        switch (info.m_info.m_eState) {
        case k_ESteamNetworkingConnectionState_Connecting:
            if (!peers.contains(info.m_hConn)) {
                accept_connection(info);
            }
            return;
        case k_ESteamNetworkingConnectionState_None:
        case k_ESteamNetworkingConnectionState_FindingRoute:
        case k_ESteamNetworkingConnectionState_Connected:
            return;
        case k_ESteamNetworkingConnectionState_ClosedByPeer:
        case k_ESteamNetworkingConnectionState_ProblemDetectedLocally: {
            const int raw_reason = info.m_info.m_eEndReason;
            const auto code = raw_reason == graceful_transport_close_reason
                                  ? detail::DisconnectCode::Normal
                                  : raw_reason > 0 &&
                                      raw_reason <=
                                          std::numeric_limits<std::uint16_t>::max()
                                  ? static_cast<detail::DisconnectCode>(raw_reason)
                                  : detail::DisconnectCode::TransportFailure;
            close_peer(info.m_hConn,
                       code,
                       safe_transport_debug(info.m_info.m_szEndDebug,
                                            "network connection closed"),
                       false,
                       true);
            return;
        }
        default:
            return;
        }
    }

    bool emit_event(TransportEvent event) {
        if (events.try_push(std::move(event))) {
            return true;
        }
        ++statistics.event_overflows;
        overflow_pending = true;
        return false;
    }

    void close_peer(const HSteamNetConnection handle,
                    const detail::DisconnectCode code,
                    std::string reason,
                    const bool linger,
                    const bool publish_event) {
        const auto iterator = peers.find(handle);
        if (iterator == peers.end()) {
            return;
        }
        const ConnectionId connection = iterator->second.connection;
        const bool established = iterator->second.established;
        static_cast<void>(sockets->SetConnectionUserData(handle, 0));
        const std::string transport_reason =
            reason.size() <= maximum_transport_close_reason_size
                ? reason
                : reason.substr(0, maximum_transport_close_reason_size);
        const int transport_code = code == detail::DisconnectCode::Normal
                                       ? graceful_transport_close_reason
                                       : static_cast<int>(code);
        static_cast<void>(sockets->CloseConnection(
            handle, transport_code, transport_reason.c_str(), linger));
        peers.erase(iterator);
        if (publish_event && established) {
            emit_event({TransportEventType::Disconnected,
                        connection,
                        NetworkDelivery::Reliable,
                        {},
                        std::move(reason),
                        0,
                        static_cast<std::uint16_t>(code)});
        }
    }

    bool send_internal(Peer& peer, const std::span<const std::uint8_t> payload) {
        return sockets->SendMessageToConnection(
                   peer.handle,
                   payload.data(),
                   static_cast<std::uint32_t>(payload.size()),
                   k_nSteamNetworkingSend_Reliable,
                   nullptr) == k_EResultOK;
    }

    void process_handshake(Peer& peer, const SteamNetworkingMessage_t& message) {
        if (peer.handshake == nullptr || peer.established) {
            close_peer(peer.handle,
                       detail::DisconnectCode::UnexpectedMessage,
                       "handshake message arrived in an invalid state",
                       false,
                       false);
            return;
        }
        if ((message.m_nFlags & k_nSteamNetworkingSend_Reliable) == 0) {
            close_peer(peer.handle,
                       detail::DisconnectCode::MalformedMessage,
                       "handshake messages must use reliable delivery",
                       false,
                       false);
            return;
        }
        if (message.m_cbSize < 0 ||
            (message.m_cbSize > 0 && message.m_pData == nullptr)) {
            close_peer(peer.handle,
                       detail::DisconnectCode::MalformedMessage,
                       "peer supplied an invalid handshake payload",
                       false,
                       false);
            return;
        }
        const auto payload = std::span(
            static_cast<const std::uint8_t*>(message.m_pData),
            static_cast<std::size_t>(message.m_cbSize));
        detail::HandshakeUpdate update = peer.handshake->receive(payload);
        if (!update.outbound.empty() && !send_internal(peer, update.outbound)) {
            close_peer(peer.handle,
                       detail::DisconnectCode::TransportFailure,
                       "server failed to send a handshake response",
                       false,
                       false);
            return;
        }
        if (update.disconnect_code != detail::DisconnectCode::None) {
            close_peer(peer.handle,
                       update.disconnect_code,
                       std::move(update.reason),
                       true,
                       false);
            return;
        }
        if (update.established) {
            peer.negotiated_maximum_message_size =
                update.negotiated_maximum_message_size;
            peer.established = true;
            peer.handshake.reset();
            const HSteamNetConnection handle = peer.handle;
            if (!emit_event({TransportEventType::Connected, peer.connection})) {
                close_peer(handle,
                           detail::DisconnectCode::LimitViolation,
                           "server event queue capacity exhausted",
                           false,
                           false);
            }
        }
    }

    void process_application_message(Peer& peer,
                                     const SteamNetworkingMessage_t& message) {
        if (message.m_cbSize < 0 ||
            static_cast<std::size_t>(message.m_cbSize) >
                peer.negotiated_maximum_message_size ||
            (message.m_cbSize > 0 && message.m_pData == nullptr)) {
            close_peer(peer.handle,
                       message.m_cbSize < 0 || message.m_pData == nullptr
                           ? detail::DisconnectCode::MalformedMessage
                           : detail::DisconnectCode::MessageTooLarge,
                       "peer application message violates the negotiated limit",
                       false,
                       true);
            return;
        }
        TransportEvent event;
        event.type = TransportEventType::Message;
        event.connection = peer.connection;
        event.delivery = (message.m_nFlags & k_nSteamNetworkingSend_Reliable) != 0
                             ? NetworkDelivery::Reliable
                             : NetworkDelivery::Unreliable;
        if (message.m_cbSize > 0) {
            const auto* const begin =
                static_cast<const std::uint8_t*>(message.m_pData);
            event.payload.assign(begin, begin + message.m_cbSize);
        }
        event.sequence = message.m_nMessageNumber > 0
                             ? static_cast<std::uint64_t>(message.m_nMessageNumber)
                             : 0;
        const std::size_t bytes = event.payload.size();
        if (emit_event(std::move(event))) {
            ++statistics.messages_received;
            statistics.bytes_received += bytes;
        }
    }

    void pump_messages() {
        std::size_t processed = 0;
        while (poll_group != k_HSteamNetPollGroup_Invalid &&
               processed < maximum_transport_messages_per_poll) {
            std::array<SteamNetworkingMessage_t*, receive_batch_size> messages{};
            const int count = sockets->ReceiveMessagesOnPollGroup(
                poll_group, messages.data(), static_cast<int>(messages.size()));
            if (count < 0) {
                throw NetworkError("failed to receive server network messages");
            }
            if (count == 0) {
                return;
            }
            for (int index = 0; index < count; ++index) {
                SteamNetworkingMessage_t* const message = messages[index];
                if (message == nullptr) {
                    continue;
                }
                const auto iterator = peers.find(message->m_conn);
                if (iterator != peers.end()) {
                    if (iterator->second.established) {
                        process_application_message(iterator->second, *message);
                    } else {
                        process_handshake(iterator->second, *message);
                    }
                }
                message->Release();
                ++processed;
            }
        }
    }

    std::vector<TransportEvent> poll(const std::size_t maximum_events) {
        sockets->RunCallbacks();
        if (state == NetworkServerState::Listening) {
            pump_messages();
            const auto now = std::chrono::steady_clock::now();
            std::vector<HSteamNetConnection> timed_out;
            for (const auto& [handle, peer] : peers) {
                if (!peer.established && now >= peer.deadline) {
                    timed_out.push_back(handle);
                }
            }
            for (const HSteamNetConnection handle : timed_out) {
                close_peer(handle,
                           detail::DisconnectCode::ConnectionTimeout,
                           "server handshake timed out",
                           false,
                           false);
            }
        }
        if (overflow_pending) {
            overflow_pending = false;
            throw NetworkError("server event queue capacity exhausted");
        }
        return events.drain(maximum_events);
    }

    Peer* find_peer(const ConnectionId connection) {
        for (auto& [handle, peer] : peers) {
            static_cast<void>(handle);
            if (peer.connection == connection) {
                return &peer;
            }
        }
        return nullptr;
    }

    SendStatus send(const ConnectionId connection,
                    const std::span<const std::uint8_t> payload,
                    const NetworkDelivery delivery) {
        Peer* const peer = find_peer(connection);
        if (peer == nullptr || !peer->established) {
            ++statistics.queue_rejections;
            return SendStatus::InvalidConnection;
        }
        if (payload.size() > peer->negotiated_maximum_message_size) {
            ++statistics.queue_rejections;
            return SendStatus::MessageTooLarge;
        }
        const EResult result = sockets->SendMessageToConnection(
            peer->handle,
            payload.data(),
            static_cast<std::uint32_t>(payload.size()),
            send_flags(delivery),
            nullptr);
        if (result == k_EResultOK) {
            ++statistics.messages_sent;
            statistics.bytes_sent += payload.size();
            return SendStatus::Queued;
        }
        ++statistics.queue_rejections;
        return result == k_EResultLimitExceeded ? SendStatus::QueueFull
                                                : SendStatus::InvalidConnection;
    }

    void disconnect(const ConnectionId connection, std::string reason) {
        Peer* const peer = find_peer(connection);
        if (peer == nullptr || !peer->established) {
            throw NetworkError("cannot disconnect an inactive server connection");
        }
        if (!valid_close_reason(reason)) {
            throw std::invalid_argument(
                "disconnect reason must be at most 120 bytes without controls");
        }
        if (reason.empty()) {
            reason = "server disconnected the client";
        }
        close_peer(peer->handle,
                   detail::DisconnectCode::Normal,
                   std::move(reason),
                   true,
                   true);
    }

    void shutdown(const bool publish_events, std::string reason) {
        if (sockets != nullptr) {
            while (!peers.empty()) {
                const HSteamNetConnection handle = peers.begin()->first;
                close_peer(handle,
                           detail::DisconnectCode::ServerStopped,
                           publish_events ? reason : std::string{},
                           false,
                           publish_events);
            }
            // Close accepted peers before the listen socket. GNS documents
            // CloseListenSocket as an ungraceful close of every connection
            // still accepted on it, which would discard our stable reason.
            if (listen_socket != k_HSteamListenSocket_Invalid) {
                static_cast<void>(sockets->CloseListenSocket(listen_socket));
                listen_socket = k_HSteamListenSocket_Invalid;
            }
            if (poll_group != k_HSteamNetPollGroup_Invalid) {
                static_cast<void>(sockets->DestroyPollGroup(poll_group));
                poll_group = k_HSteamNetPollGroup_Invalid;
            }
        }
        state = NetworkServerState::Stopped;
        bound_address.clear();
        bound_port = 0;
    }

    std::vector<ConnectionId> established_connections() const {
        std::vector<ConnectionId> result;
        result.reserve(peers.size());
        for (const auto& [handle, peer] : peers) {
            static_cast<void>(handle);
            if (peer.established) {
                result.push_back(peer.connection);
            }
        }
        std::sort(result.begin(), result.end());
        return result;
    }

    NetworkServerConfig config;
    NetworkBackendRuntime runtime;
    ISteamNetworkingSockets* sockets{nullptr};
    TransportEventQueue events;
    HSteamListenSocket listen_socket{k_HSteamListenSocket_Invalid};
    HSteamNetPollGroup poll_group{k_HSteamNetPollGroup_Invalid};
    std::unordered_map<HSteamNetConnection, Peer> peers;
    std::uint64_t connection_generation{0};
    NetworkServerState state{NetworkServerState::Stopped};
    std::string bound_address;
    std::uint16_t bound_port{0};
    TransportStats statistics;
    bool overflow_pending{false};
};

NetworkServer::NetworkServer(NetworkServerConfig config)
    : impl_(std::make_unique<Impl>(validate_server_config(std::move(config)))) {}

NetworkServer::~NetworkServer() = default;

void NetworkServer::start() { impl_->start(); }

void NetworkServer::stop(std::string reason) {
    if (impl_->state == NetworkServerState::Stopped) {
        return;
    }
    if (!valid_close_reason(reason)) {
        throw std::invalid_argument(
            "server stop reason must be at most 120 bytes without controls");
    }
    if (reason.empty()) {
        reason = "server stopped";
    }
    impl_->shutdown(true, std::move(reason));
}

NetworkServerState NetworkServer::state() const noexcept { return impl_->state; }

std::uint16_t NetworkServer::port() const noexcept { return impl_->bound_port; }

std::string NetworkServer::bind_address() const { return impl_->bound_address; }

std::vector<ConnectionId> NetworkServer::connections() const {
    return impl_->established_connections();
}

SendStatus NetworkServer::send(const ConnectionId connection,
                               const std::span<const std::uint8_t> payload,
                               const NetworkDelivery delivery) {
    return impl_->send(connection, payload, delivery);
}

void NetworkServer::disconnect(const ConnectionId connection, std::string reason) {
    impl_->disconnect(connection, std::move(reason));
}

std::vector<TransportEvent> NetworkServer::poll(const std::size_t maximum_events) {
    if (maximum_events == 0) {
        throw std::invalid_argument("maximum server events must be positive");
    }
    return impl_->poll(maximum_events);
}

TransportStats NetworkServer::stats() const { return impl_->statistics; }

} // namespace easy3d
