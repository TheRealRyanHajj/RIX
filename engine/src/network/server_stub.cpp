#include "easy3d/network.hpp"

namespace easy3d {

struct NetworkServer::Impl final {};

NetworkServer::NetworkServer(NetworkServerConfig) {
    throw NetworkError("GameNetworkingSockets server is not enabled in this build");
}

NetworkServer::~NetworkServer() = default;

void NetworkServer::start() {
    throw NetworkError("GameNetworkingSockets server is unavailable");
}

void NetworkServer::stop(std::string) {}

NetworkServerState NetworkServer::state() const noexcept {
    return NetworkServerState::Stopped;
}

std::uint16_t NetworkServer::port() const noexcept { return 0; }

std::string NetworkServer::bind_address() const { return {}; }

std::vector<ConnectionId> NetworkServer::connections() const { return {}; }

SendStatus NetworkServer::send(ConnectionId,
                               std::span<const std::uint8_t>,
                               NetworkDelivery) {
    return SendStatus::InvalidConnection;
}

void NetworkServer::disconnect(ConnectionId, std::string) {
    throw NetworkError("GameNetworkingSockets server is unavailable");
}

std::vector<TransportEvent> NetworkServer::poll(std::size_t) { return {}; }

TransportStats NetworkServer::stats() const { return {}; }

} // namespace easy3d
