#include "easy3d/network.hpp"

namespace easy3d {

NetworkBackendInfo network_backend_info() {
    return {false, "unavailable", "", ""};
}

NetworkBackendRuntime::NetworkBackendRuntime() {
    throw NetworkError("GameNetworkingSockets backend is not enabled in this build");
}

NetworkBackendRuntime::~NetworkBackendRuntime() = default;

bool NetworkBackendRuntime::ready() const noexcept { return false; }

bool NetworkBackendRuntime::loopback_smoke_test() const { return false; }

} // namespace easy3d
