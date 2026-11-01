#include "easy3d/network.hpp"

namespace easy3d {

struct NetworkClient::Impl final {};

NetworkClient::NetworkClient(NetworkClientConfig) {
    throw NetworkError("GameNetworkingSockets client is not enabled in this build");
}

NetworkClient::~NetworkClient() = default;

void NetworkClient::connect(std::string, std::uint16_t) {
    throw NetworkError("GameNetworkingSockets client is unavailable");
}

ConnectionId NetworkClient::connection() const noexcept { return {}; }

NetworkClientState NetworkClient::state() const noexcept {
    return NetworkClientState::Disconnected;
}

std::string NetworkClient::remote_address() const { return {}; }

NetworkConnectionMetrics NetworkClient::metrics() const { return {}; }

SendStatus NetworkClient::send(ConnectionId,
                               std::span<const std::uint8_t>,
                               NetworkDelivery) {
    return SendStatus::InvalidConnection;
}

void NetworkClient::disconnect(ConnectionId, std::string) {
    throw NetworkError("GameNetworkingSockets client is unavailable");
}

std::vector<TransportEvent> NetworkClient::poll(std::size_t) { return {}; }

TransportStats NetworkClient::stats() const { return {}; }

} // namespace easy3d
