#include "easy3d/network_protocol.hpp"

#include <algorithm>
#include <array>
#include <limits>
#include <stdexcept>
#include <string_view>

namespace easy3d::detail {
namespace {

constexpr std::array<std::uint8_t, 4> wire_magic{'E', '3', 'D', 'N'};
constexpr std::uint16_t wire_format_version = 1;
constexpr std::size_t frame_header_size = 12;
constexpr std::size_t peer_declaration_size = 12;

enum class HandshakeMessageType : std::uint8_t {
    ClientHello = 1,
    ServerAccept = 2,
    ClientConfirm = 3,
    Reject = 4,
};

struct DecodedFrame final {
    HandshakeMessageType type;
    std::span<const std::uint8_t> payload;
};

struct DecodeResult final {
    DecodedFrame frame{HandshakeMessageType::Reject, {}};
    DisconnectCode error{DisconnectCode::None};
    std::string_view reason;
};

struct PeerDeclaration final {
    std::uint16_t protocol_version{0};
    std::uint32_t schema_version{0};
    NetworkRole role{NetworkRole::Client};
    std::uint32_t maximum_message_size{0};
};

void append_u16(std::vector<std::uint8_t>& output, const std::uint16_t value) {
    output.push_back(static_cast<std::uint8_t>(value & 0xffU));
    output.push_back(static_cast<std::uint8_t>((value >> 8U) & 0xffU));
}

void append_u32(std::vector<std::uint8_t>& output, const std::uint32_t value) {
    for (unsigned int shift = 0; shift < 32; shift += 8) {
        output.push_back(static_cast<std::uint8_t>((value >> shift) & 0xffU));
    }
}

bool read_u16(const std::span<const std::uint8_t> input,
              const std::size_t offset,
              std::uint16_t& value) {
    if (offset > input.size() || input.size() - offset < 2) {
        return false;
    }
    value = static_cast<std::uint16_t>(input[offset]) |
            static_cast<std::uint16_t>(input[offset + 1]) << 8U;
    return true;
}

bool read_u32(const std::span<const std::uint8_t> input,
              const std::size_t offset,
              std::uint32_t& value) {
    if (offset > input.size() || input.size() - offset < 4) {
        return false;
    }
    value = static_cast<std::uint32_t>(input[offset]) |
            static_cast<std::uint32_t>(input[offset + 1]) << 8U |
            static_cast<std::uint32_t>(input[offset + 2]) << 16U |
            static_cast<std::uint32_t>(input[offset + 3]) << 24U;
    return true;
}

std::vector<std::uint8_t> encode_frame(
    const HandshakeMessageType type,
    const std::span<const std::uint8_t> payload) {
    if (payload.size() > maximum_handshake_frame_size - frame_header_size) {
        throw std::logic_error("internal handshake payload exceeds its wire limit");
    }
    std::vector<std::uint8_t> output;
    output.reserve(frame_header_size + payload.size());
    output.insert(output.end(), wire_magic.begin(), wire_magic.end());
    append_u16(output, wire_format_version);
    output.push_back(static_cast<std::uint8_t>(type));
    output.push_back(0); // Reserved flags must remain zero for this format.
    append_u32(output, static_cast<std::uint32_t>(payload.size()));
    output.insert(output.end(), payload.begin(), payload.end());
    return output;
}

std::vector<std::uint8_t> encode_peer_declaration(
    const HandshakeMessageType type,
    const HandshakeConfig& config,
    const std::uint32_t maximum_message_size) {
    std::vector<std::uint8_t> payload;
    payload.reserve(peer_declaration_size);
    append_u16(payload, config.protocol_version);
    append_u32(payload, config.schema_version);
    payload.push_back(static_cast<std::uint8_t>(config.role));
    payload.push_back(0); // Reserved.
    append_u32(payload, maximum_message_size);
    return encode_frame(type, payload);
}

bool valid_reason_text(const std::span<const std::uint8_t> text) {
    std::size_t index = 0;
    while (index < text.size()) {
        const std::uint8_t first = text[index];
        std::uint32_t code_point = 0;
        std::size_t length = 0;
        if (first <= 0x7fU) {
            code_point = first;
            length = 1;
        } else if (first >= 0xc2U && first <= 0xdfU) {
            code_point = first & 0x1fU;
            length = 2;
        } else if (first >= 0xe0U && first <= 0xefU) {
            code_point = first & 0x0fU;
            length = 3;
        } else if (first >= 0xf0U && first <= 0xf4U) {
            code_point = first & 0x07U;
            length = 4;
        } else {
            return false;
        }
        if (text.size() - index < length) {
            return false;
        }
        for (std::size_t continuation = 1; continuation < length; ++continuation) {
            const std::uint8_t byte = text[index + continuation];
            if ((byte & 0xc0U) != 0x80U) {
                return false;
            }
            code_point = (code_point << 6U) | (byte & 0x3fU);
        }
        if ((length == 2 && code_point < 0x80U) ||
            (length == 3 && code_point < 0x800U) ||
            (length == 4 && code_point < 0x10000U) || code_point > 0x10ffffU ||
            (code_point >= 0xd800U && code_point <= 0xdfffU) ||
            code_point < 0x20U || (code_point >= 0x7fU && code_point <= 0x9fU)) {
            return false;
        }
        index += length;
    }
    return true;
}

bool known_disconnect_code(const DisconnectCode code) {
    switch (code) {
    case DisconnectCode::Normal:
    case DisconnectCode::MalformedMessage:
    case DisconnectCode::ProtocolVersionMismatch:
    case DisconnectCode::SchemaVersionMismatch:
    case DisconnectCode::RoleMismatch:
    case DisconnectCode::LimitViolation:
    case DisconnectCode::UnexpectedMessage:
    case DisconnectCode::MessageTooLarge:
        return true;
    case DisconnectCode::None:
        return false;
    }
    return false;
}

std::vector<std::uint8_t> encode_reject(const DisconnectCode code,
                                        const std::string_view reason) {
    if (!known_disconnect_code(code) || reason.empty() ||
        reason.size() > maximum_disconnect_reason_size) {
        throw std::logic_error("invalid internal handshake rejection");
    }
    const auto bytes = std::span(
        reinterpret_cast<const std::uint8_t*>(reason.data()), reason.size());
    if (!valid_reason_text(bytes)) {
        throw std::logic_error("internal handshake rejection is not safe UTF-8 text");
    }
    std::vector<std::uint8_t> payload;
    payload.reserve(4 + reason.size());
    append_u16(payload, static_cast<std::uint16_t>(code));
    append_u16(payload, static_cast<std::uint16_t>(reason.size()));
    payload.insert(payload.end(), bytes.begin(), bytes.end());
    return encode_frame(HandshakeMessageType::Reject, payload);
}

DecodeResult decode_frame(const std::span<const std::uint8_t> input) {
    if (input.size() > maximum_handshake_frame_size) {
        return {{}, DisconnectCode::MessageTooLarge,
                "handshake frame exceeds 512 bytes"};
    }
    if (input.size() < frame_header_size) {
        return {{}, DisconnectCode::MalformedMessage,
                "handshake frame is truncated"};
    }
    if (!std::equal(wire_magic.begin(), wire_magic.end(), input.begin())) {
        return {{}, DisconnectCode::MalformedMessage,
                "handshake magic is invalid"};
    }
    std::uint16_t format_version = 0;
    static_cast<void>(read_u16(input, 4, format_version));
    if (format_version != wire_format_version) {
        return {{}, DisconnectCode::ProtocolVersionMismatch,
                "wire format version is incompatible"};
    }
    if (input[7] != 0) {
        return {{}, DisconnectCode::MalformedMessage,
                "handshake reserved flags are nonzero"};
    }
    const auto raw_type = static_cast<HandshakeMessageType>(input[6]);
    if (raw_type < HandshakeMessageType::ClientHello ||
        raw_type > HandshakeMessageType::Reject) {
        return {{}, DisconnectCode::UnexpectedMessage,
                "handshake message type is unknown"};
    }
    std::uint32_t payload_size = 0;
    static_cast<void>(read_u32(input, 8, payload_size));
    if (payload_size > maximum_handshake_frame_size - frame_header_size) {
        return {{}, DisconnectCode::MessageTooLarge,
                "declared handshake payload exceeds its limit"};
    }
    if (payload_size != input.size() - frame_header_size) {
        return {{}, DisconnectCode::MalformedMessage,
                "handshake payload length does not match the frame"};
    }
    return {{raw_type, input.subspan(frame_header_size)}, DisconnectCode::None, {}};
}

bool decode_peer_declaration(const std::span<const std::uint8_t> payload,
                             PeerDeclaration& peer,
                             DisconnectCode& error,
                             std::string_view& reason) {
    if (payload.size() != peer_declaration_size) {
        error = DisconnectCode::MalformedMessage;
        reason = "peer declaration has the wrong size";
        return false;
    }
    static_cast<void>(read_u16(payload, 0, peer.protocol_version));
    static_cast<void>(read_u32(payload, 2, peer.schema_version));
    if (payload[7] != 0) {
        error = DisconnectCode::MalformedMessage;
        reason = "peer declaration reserved byte is nonzero";
        return false;
    }
    if (payload[6] != static_cast<std::uint8_t>(NetworkRole::Client) &&
        payload[6] != static_cast<std::uint8_t>(NetworkRole::Server)) {
        error = DisconnectCode::RoleMismatch;
        reason = "peer role is invalid";
        return false;
    }
    peer.role = static_cast<NetworkRole>(payload[6]);
    static_cast<void>(read_u32(payload, 8, peer.maximum_message_size));
    if (peer.maximum_message_size == 0 ||
        peer.maximum_message_size > hard_maximum_message_size) {
        error = DisconnectCode::LimitViolation;
        reason = "peer message-size limit is invalid";
        return false;
    }
    return true;
}

bool validate_peer_compatibility(const PeerDeclaration& peer,
                                 const HandshakeConfig& local,
                                 const NetworkRole expected_role,
                                 DisconnectCode& error,
                                 std::string_view& reason) {
    if (peer.protocol_version != local.protocol_version) {
        error = DisconnectCode::ProtocolVersionMismatch;
        reason = "application protocol version is incompatible";
        return false;
    }
    if (peer.schema_version != local.schema_version) {
        error = DisconnectCode::SchemaVersionMismatch;
        reason = "application schema version is incompatible";
        return false;
    }
    if (peer.role != expected_role) {
        error = DisconnectCode::RoleMismatch;
        reason = "peer declared the wrong network role";
        return false;
    }
    return true;
}

bool decode_reject(const std::span<const std::uint8_t> payload,
                   DisconnectCode& code,
                   std::string& reason) {
    std::uint16_t raw_code = 0;
    std::uint16_t reason_size = 0;
    if (!read_u16(payload, 0, raw_code) || !read_u16(payload, 2, reason_size) ||
        reason_size == 0 || reason_size > maximum_disconnect_reason_size ||
        payload.size() != 4 + reason_size) {
        return false;
    }
    code = static_cast<DisconnectCode>(raw_code);
    const auto reason_bytes = payload.subspan(4);
    if (!known_disconnect_code(code) || !valid_reason_text(reason_bytes)) {
        return false;
    }
    reason.assign(reinterpret_cast<const char*>(reason_bytes.data()), reason_bytes.size());
    return true;
}

HandshakeUpdate rejected_update(HandshakeState& state,
                                const DisconnectCode code,
                                const std::string_view reason,
                                const bool send_notice) {
    state = HandshakeState::Rejected;
    HandshakeUpdate update;
    update.disconnect_code = code;
    update.reason = reason;
    if (send_notice) {
        update.outbound = encode_reject(code, reason);
    }
    return update;
}

} // namespace

ProtocolHandshake::ProtocolHandshake(HandshakeConfig config) : config_(config) {
    if (config.role != NetworkRole::Client && config.role != NetworkRole::Server) {
        throw std::invalid_argument("handshake role must be client or server");
    }
    if (config.protocol_version == 0 || config.schema_version == 0) {
        throw std::invalid_argument("handshake protocol and schema versions must be nonzero");
    }
    if (config.maximum_message_size == 0 ||
        config.maximum_message_size > hard_maximum_message_size) {
        throw std::invalid_argument("handshake message-size limit is invalid");
    }
}

std::vector<std::uint8_t> ProtocolHandshake::start() {
    if (state_ != HandshakeState::Ready) {
        throw std::logic_error("protocol handshake has already started");
    }
    if (config_.role == NetworkRole::Client) {
        state_ = HandshakeState::WaitingForServerAccept;
        return encode_peer_declaration(
            HandshakeMessageType::ClientHello, config_, config_.maximum_message_size);
    }
    state_ = HandshakeState::WaitingForClientHello;
    return {};
}

HandshakeUpdate ProtocolHandshake::receive(
    const std::span<const std::uint8_t> input) {
    if (state_ == HandshakeState::Ready) {
        throw std::logic_error("protocol handshake must be started before receiving");
    }
    if (state_ == HandshakeState::Rejected) {
        return {{}, false, DisconnectCode::UnexpectedMessage,
                "handshake is already rejected", 0};
    }
    if (state_ == HandshakeState::Established) {
        return rejected_update(state_,
                               DisconnectCode::UnexpectedMessage,
                               "handshake message arrived after establishment",
                               true);
    }

    const DecodeResult decoded = decode_frame(input);
    if (decoded.error != DisconnectCode::None) {
        return rejected_update(state_, decoded.error, decoded.reason, true);
    }
    if (decoded.frame.type == HandshakeMessageType::Reject) {
        DisconnectCode code = DisconnectCode::None;
        std::string reason;
        if (!decode_reject(decoded.frame.payload, code, reason)) {
            return rejected_update(state_,
                                   DisconnectCode::MalformedMessage,
                                   "peer rejection frame is malformed",
                                   true);
        }
        state_ = HandshakeState::Rejected;
        return {{}, false, code, std::move(reason), 0};
    }

    PeerDeclaration peer;
    DisconnectCode error = DisconnectCode::None;
    std::string_view reason;
    if (!decode_peer_declaration(decoded.frame.payload, peer, error, reason)) {
        return rejected_update(state_, error, reason, true);
    }

    if (state_ == HandshakeState::WaitingForClientHello) {
        if (decoded.frame.type != HandshakeMessageType::ClientHello) {
            return rejected_update(state_,
                                   DisconnectCode::UnexpectedMessage,
                                   "server expected a client hello",
                                   true);
        }
        if (!validate_peer_compatibility(
                peer, config_, NetworkRole::Client, error, reason)) {
            return rejected_update(state_, error, reason, true);
        }
        negotiated_maximum_message_size_ =
            std::min(config_.maximum_message_size, peer.maximum_message_size);
        state_ = HandshakeState::WaitingForClientConfirm;
        HandshakeConfig declaration = config_;
        declaration.role = NetworkRole::Server;
        return {encode_peer_declaration(HandshakeMessageType::ServerAccept,
                                        declaration,
                                        negotiated_maximum_message_size_),
                false,
                DisconnectCode::None,
                {},
                negotiated_maximum_message_size_};
    }

    if (state_ == HandshakeState::WaitingForServerAccept) {
        if (decoded.frame.type != HandshakeMessageType::ServerAccept) {
            return rejected_update(state_,
                                   DisconnectCode::UnexpectedMessage,
                                   "client expected a server acceptance",
                                   true);
        }
        if (!validate_peer_compatibility(
                peer, config_, NetworkRole::Server, error, reason)) {
            return rejected_update(state_, error, reason, true);
        }
        if (peer.maximum_message_size > config_.maximum_message_size) {
            return rejected_update(state_,
                                   DisconnectCode::LimitViolation,
                                   "server negotiated a message limit above the client limit",
                                   true);
        }
        negotiated_maximum_message_size_ = peer.maximum_message_size;
        state_ = HandshakeState::Established;
        HandshakeConfig declaration = config_;
        declaration.role = NetworkRole::Client;
        return {encode_peer_declaration(HandshakeMessageType::ClientConfirm,
                                        declaration,
                                        negotiated_maximum_message_size_),
                true,
                DisconnectCode::None,
                {},
                negotiated_maximum_message_size_};
    }

    if (state_ == HandshakeState::WaitingForClientConfirm) {
        if (decoded.frame.type != HandshakeMessageType::ClientConfirm) {
            return rejected_update(state_,
                                   DisconnectCode::UnexpectedMessage,
                                   "server expected a client confirmation",
                                   true);
        }
        if (!validate_peer_compatibility(
                peer, config_, NetworkRole::Client, error, reason)) {
            return rejected_update(state_, error, reason, true);
        }
        if (peer.maximum_message_size != negotiated_maximum_message_size_) {
            return rejected_update(state_,
                                   DisconnectCode::LimitViolation,
                                   "client confirmation changed the negotiated message limit",
                                   true);
        }
        state_ = HandshakeState::Established;
        return {{},
                true,
                DisconnectCode::None,
                {},
                negotiated_maximum_message_size_};
    }

    return rejected_update(state_,
                           DisconnectCode::UnexpectedMessage,
                           "handshake entered an invalid state",
                           true);
}

HandshakeState ProtocolHandshake::state() const noexcept { return state_; }

std::uint32_t ProtocolHandshake::negotiated_maximum_message_size() const noexcept {
    return negotiated_maximum_message_size_;
}

const HandshakeConfig& ProtocolHandshake::config() const noexcept { return config_; }

const char* disconnect_code_name(const DisconnectCode code) noexcept {
    switch (code) {
    case DisconnectCode::None:
        return "none";
    case DisconnectCode::Normal:
        return "normal";
    case DisconnectCode::MalformedMessage:
        return "malformed_message";
    case DisconnectCode::ProtocolVersionMismatch:
        return "protocol_version_mismatch";
    case DisconnectCode::SchemaVersionMismatch:
        return "schema_version_mismatch";
    case DisconnectCode::RoleMismatch:
        return "role_mismatch";
    case DisconnectCode::LimitViolation:
        return "limit_violation";
    case DisconnectCode::UnexpectedMessage:
        return "unexpected_message";
    case DisconnectCode::MessageTooLarge:
        return "message_too_large";
    }
    return "unknown";
}

} // namespace easy3d::detail
