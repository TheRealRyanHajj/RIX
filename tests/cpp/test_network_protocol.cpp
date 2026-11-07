#include "easy3d/network.hpp"
#include "easy3d/network_protocol.hpp"

#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using easy3d::detail::DisconnectCode;
using easy3d::detail::HandshakeConfig;
using easy3d::detail::HandshakeState;
using easy3d::detail::NetworkRole;
using easy3d::detail::ProtocolHandshake;

constexpr std::size_t message_type_offset = 6;
constexpr std::size_t frame_flags_offset = 7;
constexpr std::size_t payload_length_offset = 8;
constexpr std::size_t payload_offset = 12;
constexpr std::size_t peer_role_offset = payload_offset + 6;
constexpr std::size_t peer_reserved_offset = payload_offset + 7;
constexpr std::size_t peer_limit_offset = payload_offset + 8;

int fail(const int code, const char* const message) {
    std::cerr << message << '\n';
    return code;
}
void write_u32(std::vector<std::uint8_t>& data,
               const std::size_t offset,
               const std::uint32_t value) {
    data.at(offset) = static_cast<std::uint8_t>(value & 0xffU);
    data.at(offset + 1) = static_cast<std::uint8_t>((value >> 8U) & 0xffU);
    data.at(offset + 2) = static_cast<std::uint8_t>((value >> 16U) & 0xffU);
    data.at(offset + 3) = static_cast<std::uint8_t>((value >> 24U) & 0xffU);
}
struct CompletedHandshake final {
    ProtocolHandshake client;
    ProtocolHandshake server;

    CompletedHandshake(HandshakeConfig client_config, HandshakeConfig server_config)
        : client(client_config), server(server_config) {
        const std::vector<std::uint8_t> hello = client.start();
        if (!server.start().empty()) {
            throw std::runtime_error("server emitted an initial handshake message");
        }
        const auto accepted = server.receive(hello);
        if (accepted.outbound.empty() || accepted.established) {
            throw std::runtime_error("server did not produce a pending acceptance");
        }
        const auto confirmed = client.receive(accepted.outbound);
        if (!confirmed.established || confirmed.outbound.empty()) {
            throw std::runtime_error("client did not produce its confirmation");
        }
        const auto established = server.receive(confirmed.outbound);
        if (!established.established || !established.outbound.empty()) {
            throw std::runtime_error("server did not complete the handshake");
        }
    }
};

easy3d::detail::HandshakeUpdate reject_hello(std::vector<std::uint8_t> hello) {
    ProtocolHandshake server({NetworkRole::Server});
    static_cast<void>(server.start());
    return server.receive(hello);
}
} // namespace

int main() {
    try {
        HandshakeConfig client_config{NetworkRole::Client};
        client_config.maximum_message_size = 32 * 1024;
        HandshakeConfig server_config{NetworkRole::Server};
        server_config.maximum_message_size = 16 * 1024;
        CompletedHandshake compatible(client_config, server_config);
        if (compatible.client.state() != HandshakeState::Established ||
            compatible.server.state() != HandshakeState::Established ||
            compatible.client.negotiated_maximum_message_size() != 16 * 1024 ||
            compatible.server.negotiated_maximum_message_size() != 16 * 1024) {
            return fail(1, "compatible peers did not negotiate the bounded minimum");
        }
        easy3d::SimulatedNetwork transport;
        static_cast<void>(transport.first().poll(1));
        static_cast<void>(transport.second().poll(1));
        ProtocolHandshake transported_client({NetworkRole::Client});
        ProtocolHandshake transported_server({NetworkRole::Server});
        const auto transported_hello = transported_client.start();
        static_cast<void>(transported_server.start());
        if (transport.first().send(transport.first().connection(),
                                   transported_hello,
                                   easy3d::NetworkDelivery::Reliable) !=
            easy3d::SendStatus::Queued) {
            return fail(25, "client hello was not accepted by the transport");
        }
        transport.advance(0.0);
        const auto hello_events = transport.second().poll(1);
        if (hello_events.size() != 1 ||
            hello_events[0].delivery != easy3d::NetworkDelivery::Reliable) {
            return fail(26, "client hello did not cross the reliable transport");
        }
        const auto transported_accept =
            transported_server.receive(hello_events[0].payload);
        if (transport.second().send(transport.second().connection(),
                                    transported_accept.outbound,
                                    easy3d::NetworkDelivery::Reliable) !=
            easy3d::SendStatus::Queued) {
            return fail(27, "server acceptance was not accepted by the transport");
        }
        transport.advance(0.0);
        const auto accept_events = transport.first().poll(1);
        const auto transported_confirm =
            transported_client.receive(accept_events.at(0).payload);
        if (transport.first().send(transport.first().connection(),
                                   transported_confirm.outbound,
                                   easy3d::NetworkDelivery::Reliable) !=
            easy3d::SendStatus::Queued) {
            return fail(28, "client confirmation was not accepted by the transport");
        }
        transport.advance(0.0);
        const auto confirm_events = transport.second().poll(1);
        if (!transported_server.receive(confirm_events.at(0).payload).established ||
            transported_client.state() != HandshakeState::Established) {
            return fail(29, "handshake did not complete across the transport contract");
        }
        try {
            static_cast<void>(compatible.client.start());
            return fail(2, "a handshake could be started twice");
        } catch (const std::logic_error&) {
            // Expected local API misuse protection.
        }

        HandshakeConfig incompatible_protocol{NetworkRole::Server};
        incompatible_protocol.protocol_version = 2;
        ProtocolHandshake protocol_client({NetworkRole::Client});
        ProtocolHandshake protocol_server(incompatible_protocol);
        const auto protocol_hello = protocol_client.start();
        static_cast<void>(protocol_server.start());
        const auto protocol_rejection = protocol_server.receive(protocol_hello);
        const auto propagated_protocol_rejection =
            protocol_client.receive(protocol_rejection.outbound);
        if (protocol_rejection.disconnect_code !=
                DisconnectCode::ProtocolVersionMismatch ||
            propagated_protocol_rejection.disconnect_code !=
                DisconnectCode::ProtocolVersionMismatch ||
            protocol_client.state() != HandshakeState::Rejected) {
            return fail(3, "protocol mismatch was not rejected and propagated");
        }

        HandshakeConfig incompatible_schema{NetworkRole::Server};
        incompatible_schema.schema_version = 9;
        ProtocolHandshake schema_client({NetworkRole::Client});
        ProtocolHandshake schema_server(incompatible_schema);
        const auto schema_hello = schema_client.start();
        static_cast<void>(schema_server.start());
        const auto schema_rejection = schema_server.receive(schema_hello);
        if (schema_rejection.disconnect_code != DisconnectCode::SchemaVersionMismatch) {
            return fail(4, "schema mismatch was not rejected");
        }

        ProtocolHandshake source_client({NetworkRole::Client});
        std::vector<std::uint8_t> valid_hello = source_client.start();
        std::vector<std::uint8_t> wrong_role = valid_hello;
        wrong_role[peer_role_offset] = static_cast<std::uint8_t>(NetworkRole::Server);
        if (reject_hello(std::move(wrong_role)).disconnect_code !=
            DisconnectCode::RoleMismatch) {
            return fail(5, "wrong peer role was not rejected");
        }

        std::vector<std::uint8_t> invalid_role = valid_hello;
        invalid_role[peer_role_offset] = 99;
        if (reject_hello(std::move(invalid_role)).disconnect_code !=
            DisconnectCode::RoleMismatch) {
            return fail(6, "invalid peer role was not rejected");
        }

        std::vector<std::uint8_t> zero_limit = valid_hello;
        write_u32(zero_limit, peer_limit_offset, 0);
        if (reject_hello(std::move(zero_limit)).disconnect_code !=
            DisconnectCode::LimitViolation) {
            return fail(7, "zero peer message limit was not rejected");
        }

        std::vector<std::uint8_t> excessive_limit = valid_hello;
        write_u32(excessive_limit,
                  peer_limit_offset,
                  easy3d::detail::hard_maximum_message_size + 1);
        if (reject_hello(std::move(excessive_limit)).disconnect_code !=
            DisconnectCode::LimitViolation) {
            return fail(8, "excessive peer message limit was not rejected");
        }

        std::vector<std::uint8_t> bad_magic = valid_hello;
        bad_magic[0] ^= 0xffU;
        if (reject_hello(std::move(bad_magic)).disconnect_code !=
            DisconnectCode::MalformedMessage) {
            return fail(9, "bad handshake magic was not rejected");
        }

        if (reject_hello({1, 2, 3}).disconnect_code !=
            DisconnectCode::MalformedMessage) {
            return fail(10, "truncated handshake was not rejected");
        }

        std::vector<std::uint8_t> bad_flags = valid_hello;
        bad_flags[frame_flags_offset] = 1;
        if (reject_hello(std::move(bad_flags)).disconnect_code !=
            DisconnectCode::MalformedMessage) {
            return fail(11, "nonzero frame flags were not rejected");
        }

        std::vector<std::uint8_t> bad_reserved = valid_hello;
        bad_reserved[peer_reserved_offset] = 1;
        if (reject_hello(std::move(bad_reserved)).disconnect_code !=
            DisconnectCode::MalformedMessage) {
            return fail(12, "nonzero peer reserved byte was not rejected");
        }

        std::vector<std::uint8_t> unknown_type = valid_hello;
        unknown_type[message_type_offset] = 99;
        if (reject_hello(std::move(unknown_type)).disconnect_code !=
            DisconnectCode::UnexpectedMessage) {
            return fail(13, "unknown handshake message type was not rejected");
        }

        std::vector<std::uint8_t> wrong_length = valid_hello;
        wrong_length.pop_back();
        if (reject_hello(std::move(wrong_length)).disconnect_code !=
            DisconnectCode::MalformedMessage) {
            return fail(14, "mismatched payload length was not rejected");
        }

        std::vector<std::uint8_t> declared_oversize = valid_hello;
        write_u32(declared_oversize, payload_length_offset, 501);
        if (reject_hello(std::move(declared_oversize)).disconnect_code !=
            DisconnectCode::MessageTooLarge) {
            return fail(15, "oversized declared payload was not rejected");
        }

        if (reject_hello(std::vector<std::uint8_t>(
                             easy3d::detail::maximum_handshake_frame_size + 1, 0))
                .disconnect_code != DisconnectCode::MessageTooLarge) {
            return fail(16, "oversized handshake frame was not rejected before parsing");
        }

        std::vector<std::uint8_t> unexpected_confirm = valid_hello;
        unexpected_confirm[message_type_offset] = 3;
        if (reject_hello(std::move(unexpected_confirm)).disconnect_code !=
            DisconnectCode::UnexpectedMessage) {
            return fail(17, "out-of-order client confirmation was not rejected");
        }

        ProtocolHandshake malicious_limit_client({NetworkRole::Client});
        ProtocolHandshake malicious_limit_server({NetworkRole::Server});
        const auto malicious_hello = malicious_limit_client.start();
        static_cast<void>(malicious_limit_server.start());
        auto malicious_accept = malicious_limit_server.receive(malicious_hello).outbound;
        write_u32(malicious_accept,
                  peer_limit_offset,
                  easy3d::detail::default_maximum_message_size + 1);
        if (malicious_limit_client.receive(malicious_accept).disconnect_code !=
            DisconnectCode::LimitViolation) {
            return fail(18, "server could raise the client message-size limit");
        }

        ProtocolHandshake confirm_client({NetworkRole::Client});
        ProtocolHandshake confirm_server({NetworkRole::Server});
        const auto confirm_hello = confirm_client.start();
        static_cast<void>(confirm_server.start());
        const auto confirm_accept = confirm_server.receive(confirm_hello);
        auto changed_confirm = confirm_client.receive(confirm_accept.outbound).outbound;
        write_u32(changed_confirm, peer_limit_offset, 1);
        if (confirm_server.receive(changed_confirm).disconnect_code !=
            DisconnectCode::LimitViolation) {
            return fail(19, "client could change the negotiated limit in confirmation");
        }

        ProtocolHandshake reject_client({NetworkRole::Client});
        ProtocolHandshake reject_server(incompatible_protocol);
        const auto reject_hello_frame = reject_client.start();
        static_cast<void>(reject_server.start());
        auto invalid_utf8_reject = reject_server.receive(reject_hello_frame).outbound;
        invalid_utf8_reject.back() = 0xffU;
        if (reject_client.receive(invalid_utf8_reject).disconnect_code !=
            DisconnectCode::MalformedMessage) {
            return fail(20, "invalid UTF-8 disconnect reason was not rejected");
        }

        const auto post_established = compatible.server.receive(valid_hello);
        if (post_established.disconnect_code != DisconnectCode::UnexpectedMessage ||
            compatible.server.state() != HandshakeState::Rejected) {
            return fail(21, "post-establishment handshake message was not rejected");
        }

        try {
            HandshakeConfig invalid_config{NetworkRole::Client};
            invalid_config.maximum_message_size = 0;
            ProtocolHandshake invalid(invalid_config);
            return fail(22, "zero local message-size limit was accepted");
        } catch (const std::invalid_argument&) {
            // Expected.
        }

        if (std::string(easy3d::detail::disconnect_code_name(
                DisconnectCode::SchemaVersionMismatch)) !=
                "schema_version_mismatch" ||
            std::string(easy3d::detail::disconnect_code_name(
                static_cast<DisconnectCode>(65535))) != "unknown") {
            return fail(23, "disconnect code names are not stable");
        }

        std::cout << "easy3d_network_protocol_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "easy3d_network_protocol_tests: FAIL: " << error.what() << '\n';
        return 99;
    }
}
