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
#include <utility>

namespace easy3d {
namespace {

constexpr std::size_t maximum_transport_messages_per_poll = 256;
constexpr std::size_t receive_batch_size = 16;
constexpr std::size_t maximum_transport_close_reason_size = 120;
// GNS accepts application close reasons only in its 1000+ range. Keep a
// transport-adapter sentinel distinct from Easy3D's protocol error codes and
// map it back to the public graceful code 1 on receipt.
constexpr int graceful_transport_close_reason = 1011;

NetworkClientConfig validate_client_config(NetworkClientConfig config) {
    if (!std::isfinite(config.connection_timeout_seconds) ||
        config.connection_timeout_seconds <= 0.0) {
        throw std::invalid_argument("connection timeout must be finite and positive");
    }
    if (!std::isfinite(config.peer_timeout_seconds) ||
        config.peer_timeout_seconds < 0.001 ||
        config.peer_timeout_seconds >
            static_cast<double>(std::numeric_limits<std::int32_t>::max()) / 1000.0) {
        throw std::invalid_argument(
            "peer timeout must be between 1 ms and INT32_MAX ms");
    }
    if (config.event_queue_capacity == 0) {
        throw std::invalid_argument("client event queue capacity must be positive");
    }
    if (config.maximum_message_size == 0 ||
        config.maximum_message_size > detail::hard_maximum_message_size) {
        throw std::invalid_argument("client message-size limit is invalid");
    }
    if (config.protocol_version == 0 || config.schema_version == 0) {
        throw std::invalid_argument("client protocol and schema versions must be nonzero");
    }
    return config;
}

bool valid_local_close_reason(const std::string_view reason) {
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
    if (output.empty()) {
        output = fallback;
    }
    return output;
}

int send_flags(const NetworkDelivery delivery) {
    return delivery == NetworkDelivery::Reliable ? k_nSteamNetworkingSend_Reliable
                                                  : k_nSteamNetworkingSend_Unreliable;
}

} // namespace

struct NetworkClient::Impl final {
    explicit Impl(NetworkClientConfig input)
        : config(input), runtime(), sockets(SteamNetworkingSockets()), events(
              input.event_queue_capacity) {
        if (sockets == nullptr || !runtime.ready()) {
            throw NetworkError("GameNetworkingSockets client runtime is unavailable");
        }
    }

    ~Impl() { shutdown(); }

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

    void connect(const std::string& address_text, const std::uint16_t port) {
        if (state != NetworkClientState::Disconnected ||
            handle != k_HSteamNetConnection_Invalid) {
            throw NetworkError("network client is already active");
        }
        if (events.size() != 0) {
            throw NetworkError("poll pending client events before reconnecting");
        }
        if (address_text.empty() || port == 0) {
            throw std::invalid_argument("numeric address and nonzero port are required");
        }

        SteamNetworkingIPAddr address;
        address.Clear();
        if (!address.ParseString(address_text.c_str()) || address.m_port != 0 ||
            address.IsIPv6AllZeros() ||
            (address.IsIPv4() && address.GetIPv4() == 0)) {
            throw std::invalid_argument(
                "address must be a numeric IPv4 or IPv6 host without a port");
        }
        address.m_port = port;

        char normalized[SteamNetworkingIPAddr::k_cchMaxString]{};
        address.ToString(normalized, sizeof(normalized), true);
        remote = normalized;

        if (++connection_generation == 0) {
            ++connection_generation;
        }
        connection_id = ConnectionId{connection_generation};
        statistics = {};
        overflow_pending = false;
        negotiated_maximum_message_size = 0;
        handshake = std::make_unique<detail::ProtocolHandshake>(
            detail::HandshakeConfig{detail::NetworkRole::Client,
                                    config.protocol_version,
                                    config.schema_version,
                                    static_cast<std::uint32_t>(
                                        config.maximum_message_size)});

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

        state = NetworkClientState::Connecting;
        deadline = std::chrono::steady_clock::now() +
                   std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                       std::chrono::duration<double>(
                           config.connection_timeout_seconds));
        handle = sockets->ConnectByIPAddress(
            address, static_cast<int>(options.size()), options.data());
        if (handle == k_HSteamNetConnection_Invalid) {
            state = NetworkClientState::Disconnected;
            handshake.reset();
            connection_id = {};
            remote.clear();
            throw NetworkError("GameNetworkingSockets rejected the connection request");
        }
    }

    void shutdown() noexcept {
        if (handle != k_HSteamNetConnection_Invalid && sockets != nullptr) {
            static_cast<void>(sockets->SetConnectionUserData(handle, 0));
            static_cast<void>(
                sockets->CloseConnection(handle, 0, "Easy3D client shutdown", false));
            handle = k_HSteamNetConnection_Invalid;
        }
        state = NetworkClientState::Disconnected;
        handshake.reset();
    }

    void on_status_changed(const SteamNetConnectionStatusChangedCallback_t& info) {
        if (handle == k_HSteamNetConnection_Invalid || info.m_hConn != handle) {
            return;
        }
        switch (info.m_info.m_eState) {
        case k_ESteamNetworkingConnectionState_None:
        case k_ESteamNetworkingConnectionState_Connecting:
        case k_ESteamNetworkingConnectionState_FindingRoute:
            return;
        case k_ESteamNetworkingConnectionState_Connected: {
            if (state != NetworkClientState::Connecting || handshake == nullptr) {
                return;
            }
            state = NetworkClientState::Handshaking;
            const std::vector<std::uint8_t> hello = handshake->start();
            if (!send_internal(hello)) {
                complete_disconnect(detail::DisconnectCode::TransportFailure,
                                    "failed to send the client handshake",
                                    false);
            }
            return;
        }
        case k_ESteamNetworkingConnectionState_ClosedByPeer:
        case k_ESteamNetworkingConnectionState_ProblemDetectedLocally: {
            const auto raw_reason = info.m_info.m_eEndReason;
            const detail::DisconnectCode code =
                raw_reason == graceful_transport_close_reason
                    ? detail::DisconnectCode::Normal
                    : raw_reason > 0 &&
                              raw_reason <=
                                  std::numeric_limits<std::uint16_t>::max()
                          ? static_cast<detail::DisconnectCode>(raw_reason)
                          : detail::DisconnectCode::TransportFailure;
            complete_disconnect(
                code,
                safe_transport_debug(info.m_info.m_szEndDebug,
                                     "network connection closed"),
                false);
            return;
        }
        default:
            return;
        }
    }

    bool send_internal(const std::span<const std::uint8_t> payload) {
        if (handle == k_HSteamNetConnection_Invalid) {
            return false;
        }
        return sockets->SendMessageToConnection(handle,
                                                 payload.data(),
                                                 static_cast<std::uint32_t>(payload.size()),
                                                 k_nSteamNetworkingSend_Reliable,
                                                 nullptr) == k_EResultOK;
    }

    void emit_event(TransportEvent event) {
        if (!events.try_push(std::move(event))) {
            ++statistics.event_overflows;
            overflow_pending = true;
        }
    }

    void complete_disconnect(const detail::DisconnectCode code,
                             std::string reason,
                             const bool linger) {
        const ConnectionId disconnected_connection = connection_id;
        if (handle != k_HSteamNetConnection_Invalid) {
            static_cast<void>(sockets->SetConnectionUserData(handle, 0));
            const int transport_code = code == detail::DisconnectCode::Normal
                                           ? graceful_transport_close_reason
                                           : static_cast<int>(code);
            const std::string debug_reason =
                reason.size() <= maximum_transport_close_reason_size
                    ? reason
                    : reason.substr(0, maximum_transport_close_reason_size);
            static_cast<void>(sockets->CloseConnection(
                handle, transport_code, debug_reason.c_str(), linger));
            handle = k_HSteamNetConnection_Invalid;
        }
        const bool was_active = state != NetworkClientState::Disconnected;
        state = NetworkClientState::Disconnected;
        handshake.reset();
        negotiated_maximum_message_size = 0;
        if (was_active && disconnected_connection.valid()) {
            emit_event({TransportEventType::Disconnected,
                        disconnected_connection,
                        NetworkDelivery::Reliable,
                        {},
                        std::move(reason),
                        0,
                        static_cast<std::uint16_t>(code)});
        }
        connection_id = {};
    }

    void process_handshake_message(const SteamNetworkingMessage_t& message) {
        if (handshake == nullptr || state != NetworkClientState::Handshaking) {
            complete_disconnect(detail::DisconnectCode::UnexpectedMessage,
                                "handshake message arrived in an invalid state",
                                false);
            return;
        }
        if ((message.m_nFlags & k_nSteamNetworkingSend_Reliable) == 0) {
            complete_disconnect(detail::DisconnectCode::MalformedMessage,
                                "handshake messages must use reliable delivery",
                                false);
            return;
        }
        const auto payload = std::span(
            static_cast<const std::uint8_t*>(message.m_pData),
            static_cast<std::size_t>(message.m_cbSize));
        detail::HandshakeUpdate update = handshake->receive(payload);
        if (!update.outbound.empty() && !send_internal(update.outbound)) {
            complete_disconnect(detail::DisconnectCode::TransportFailure,
                                "failed to send a handshake response",
                                false);
            return;
        }
        if (update.disconnect_code != detail::DisconnectCode::None) {
            complete_disconnect(update.disconnect_code, std::move(update.reason), true);
            return;
        }
        if (update.established) {
            negotiated_maximum_message_size =
                update.negotiated_maximum_message_size;
            state = NetworkClientState::Connected;
            emit_event({TransportEventType::Connected, connection_id});
        }
    }

    void process_application_message(const SteamNetworkingMessage_t& message) {
        if (message.m_cbSize < 0 ||
            static_cast<std::size_t>(message.m_cbSize) >
                negotiated_maximum_message_size) {
            complete_disconnect(detail::DisconnectCode::MessageTooLarge,
                                "peer application message exceeds the negotiated limit",
                                false);
            return;
        }
        TransportEvent event;
        event.type = TransportEventType::Message;
        event.connection = connection_id;
        event.delivery = (message.m_nFlags & k_nSteamNetworkingSend_Reliable) != 0
                             ? NetworkDelivery::Reliable
                             : NetworkDelivery::Unreliable;
        if (message.m_cbSize > 0) {
            if (message.m_pData == nullptr) {
                complete_disconnect(detail::DisconnectCode::MalformedMessage,
                                    "peer supplied a null message payload",
                                    false);
                return;
            }
            const auto* const begin =
                static_cast<const std::uint8_t*>(message.m_pData);
            event.payload.assign(begin, begin + message.m_cbSize);
        }
        event.sequence = message.m_nMessageNumber > 0
                             ? static_cast<std::uint64_t>(message.m_nMessageNumber)
                             : 0;
        const std::size_t bytes = event.payload.size();
        if (events.try_push(std::move(event))) {
            ++statistics.messages_received;
            statistics.bytes_received += bytes;
        } else {
            ++statistics.event_overflows;
            overflow_pending = true;
        }
    }

    void pump_messages() {
        std::size_t processed = 0;
        while (handle != k_HSteamNetConnection_Invalid &&
               processed < maximum_transport_messages_per_poll) {
            std::array<SteamNetworkingMessage_t*, receive_batch_size> messages{};
            const int count = sockets->ReceiveMessagesOnConnection(
                handle, messages.data(), static_cast<int>(messages.size()));
            if (count < 0) {
                complete_disconnect(detail::DisconnectCode::TransportFailure,
                                    "failed to receive network messages",
                                    false);
                return;
            }
            if (count == 0) {
                return;
            }
            for (int index = 0; index < count; ++index) {
                SteamNetworkingMessage_t* const message = messages[index];
                if (message == nullptr) {
                    continue;
                }
                if (handle != k_HSteamNetConnection_Invalid) {
                    if (message->m_cbSize < 0) {
                        complete_disconnect(detail::DisconnectCode::MalformedMessage,
                                            "peer supplied an invalid message size",
                                            false);
                    } else if (state == NetworkClientState::Handshaking) {
                        process_handshake_message(*message);
                    } else if (state == NetworkClientState::Connected) {
                        process_application_message(*message);
                    }
                }
                message->Release();
                ++processed;
            }
        }
    }

    std::vector<TransportEvent> poll(const std::size_t maximum_events) {
        sockets->RunCallbacks();
        if (handle != k_HSteamNetConnection_Invalid) {
            pump_messages();
        }
        if ((state == NetworkClientState::Connecting ||
             state == NetworkClientState::Handshaking) &&
            std::chrono::steady_clock::now() >= deadline) {
            complete_disconnect(detail::DisconnectCode::ConnectionTimeout,
                                "connection handshake timed out",
                                false);
        }
        if (overflow_pending) {
            overflow_pending = false;
            throw NetworkError("client event queue capacity exhausted");
        }
        return events.drain(maximum_events);
    }

    SendStatus send(const ConnectionId requested,
                    const std::span<const std::uint8_t> payload,
                    const NetworkDelivery delivery) {
        if (state != NetworkClientState::Connected || requested != connection_id ||
            handle == k_HSteamNetConnection_Invalid) {
            ++statistics.queue_rejections;
            return SendStatus::InvalidConnection;
        }
        if (payload.size() > negotiated_maximum_message_size) {
            ++statistics.queue_rejections;
            return SendStatus::MessageTooLarge;
        }
        const EResult result = sockets->SendMessageToConnection(
            handle,
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
        if (result == k_EResultLimitExceeded) {
            return SendStatus::QueueFull;
        }
        return SendStatus::InvalidConnection;
    }

    void disconnect(const ConnectionId requested, std::string reason) {
        if (state == NetworkClientState::Disconnected || requested != connection_id ||
            handle == k_HSteamNetConnection_Invalid) {
            throw NetworkError("cannot disconnect an inactive network client");
        }
        if (!valid_local_close_reason(reason)) {
            throw std::invalid_argument(
                "disconnect reason must be at most 120 bytes without controls");
        }
        if (reason.empty()) {
            reason = "client disconnected";
        }
        complete_disconnect(detail::DisconnectCode::Normal, std::move(reason), true);
    }

    NetworkConnectionMetrics metrics() const {
        NetworkConnectionMetrics result;
        result.state = state;
        result.negotiated_maximum_message_size = negotiated_maximum_message_size;
        result.transport = statistics;
        if (handle == k_HSteamNetConnection_Invalid) {
            return result;
        }
        SteamNetConnectionRealTimeStatus_t status{};
        if (sockets->GetConnectionRealTimeStatus(handle, &status, 0, nullptr) !=
            k_EResultOK) {
            return result;
        }
        result.ping_milliseconds = status.m_nPing;
        result.outgoing_bytes_per_second = status.m_flOutBytesPerSec;
        result.incoming_bytes_per_second = status.m_flInBytesPerSec;
        result.pending_reliable_bytes =
            static_cast<std::uint64_t>(std::max(0, status.m_cbPendingReliable));
        result.pending_unreliable_bytes =
            static_cast<std::uint64_t>(std::max(0, status.m_cbPendingUnreliable));
        return result;
    }

    NetworkClientConfig config;
    NetworkBackendRuntime runtime;
    ISteamNetworkingSockets* sockets{nullptr};
    TransportEventQueue events;
    HSteamNetConnection handle{k_HSteamNetConnection_Invalid};
    ConnectionId connection_id;
    std::uint64_t connection_generation{0};
    NetworkClientState state{NetworkClientState::Disconnected};
    std::string remote;
    std::unique_ptr<detail::ProtocolHandshake> handshake;
    std::chrono::steady_clock::time_point deadline{};
    std::uint32_t negotiated_maximum_message_size{0};
    TransportStats statistics;
    bool overflow_pending{false};
};

NetworkClient::NetworkClient(NetworkClientConfig config)
    : impl_(std::make_unique<Impl>(validate_client_config(config))) {}

NetworkClient::~NetworkClient() = default;

void NetworkClient::connect(std::string address, const std::uint16_t port) {
    impl_->connect(address, port);
}

ConnectionId NetworkClient::connection() const noexcept { return impl_->connection_id; }

NetworkClientState NetworkClient::state() const noexcept { return impl_->state; }

std::string NetworkClient::remote_address() const { return impl_->remote; }

NetworkConnectionMetrics NetworkClient::metrics() const { return impl_->metrics(); }

SendStatus NetworkClient::send(const ConnectionId connection,
                               const std::span<const std::uint8_t> payload,
                               const NetworkDelivery delivery) {
    return impl_->send(connection, payload, delivery);
}

void NetworkClient::disconnect(const ConnectionId connection, std::string reason) {
    impl_->disconnect(connection, std::move(reason));
}

std::vector<TransportEvent> NetworkClient::poll(const std::size_t maximum_events) {
    if (maximum_events == 0) {
        throw std::invalid_argument("maximum client events must be positive");
    }
    return impl_->poll(maximum_events);
}

TransportStats NetworkClient::stats() const { return impl_->statistics; }

} // namespace easy3d
