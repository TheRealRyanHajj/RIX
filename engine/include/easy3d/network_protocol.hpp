#pragma once

#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <vector>

namespace easy3d::detail {

// Internal transport-independent wire contract. Python gameplay and the future
// public Client/Server API do not construct these frames directly.

inline constexpr std::uint16_t current_protocol_version = 1;
inline constexpr std::uint32_t current_schema_version = 1;
inline constexpr std::uint32_t default_maximum_message_size = 64 * 1024;
inline constexpr std::uint32_t hard_maximum_message_size = 1024 * 1024;
inline constexpr std::size_t maximum_handshake_frame_size = 512;
inline constexpr std::size_t maximum_disconnect_reason_size = 256;

enum class NetworkRole : std::uint8_t {
    Client = 1,
    Server = 2,
};

enum class HandshakeState : std::uint8_t {
    Ready,
    WaitingForClientHello,
    WaitingForServerAccept,
    WaitingForClientConfirm,
    Established,
    Rejected,
};

// Values are stable wire disconnect codes. Keep protocol failures at or above
// 1000 so later application-defined graceful reasons have a separate range.
enum class DisconnectCode : std::uint16_t {
    None = 0,
    Normal = 1,
    MalformedMessage = 1000,
    ProtocolVersionMismatch = 1001,
    SchemaVersionMismatch = 1002,
    RoleMismatch = 1003,
    LimitViolation = 1004,
    UnexpectedMessage = 1005,
    MessageTooLarge = 1006,
    ConnectionTimeout = 1007,
    TransportFailure = 1008,
    ServerStopped = 1009,
    ServerFull = 1010,
};

struct HandshakeConfig final {
    NetworkRole role{NetworkRole::Client};
    std::uint16_t protocol_version{current_protocol_version};
    std::uint32_t schema_version{current_schema_version};
    std::uint32_t maximum_message_size{default_maximum_message_size};
};

struct HandshakeUpdate final {
    std::vector<std::uint8_t> outbound;
    bool established{false};
    DisconnectCode disconnect_code{DisconnectCode::None};
    std::string reason;
    std::uint32_t negotiated_maximum_message_size{0};
};

class ProtocolHandshake final {
public:
    explicit ProtocolHandshake(HandshakeConfig config);

    ProtocolHandshake(const ProtocolHandshake&) = delete;
    ProtocolHandshake& operator=(const ProtocolHandshake&) = delete;
    ProtocolHandshake(ProtocolHandshake&&) = delete;
    ProtocolHandshake& operator=(ProtocolHandshake&&) = delete;

    // Starts exactly once. A client returns its hello; a server returns an
    // empty vector and begins waiting for that hello.
    [[nodiscard]] std::vector<std::uint8_t> start();
    [[nodiscard]] HandshakeUpdate receive(std::span<const std::uint8_t> frame);

    [[nodiscard]] HandshakeState state() const noexcept;
    [[nodiscard]] std::uint32_t negotiated_maximum_message_size() const noexcept;
    [[nodiscard]] const HandshakeConfig& config() const noexcept;

private:
    HandshakeConfig config_;
    HandshakeState state_{HandshakeState::Ready};
    std::uint32_t negotiated_maximum_message_size_{0};
};

[[nodiscard]] const char* disconnect_code_name(DisconnectCode code) noexcept;

} // namespace easy3d::detail
