#include "easy3d/network.hpp"

namespace easy3d {

NetworkBackendInfo network_backend_info() {
    return {false, "unavailable", "", ""};
}

void set_network_backend_impairment(std::int32_t, float, float, float) {
    throw NetworkError("network backend impairment is unavailable in this build");
}

void clear_network_backend_impairment() {}

NetworkBackendRuntime::NetworkBackendRuntime() {
    throw NetworkError("GameNetworkingSockets backend is not enabled in this build");
}

NetworkBackendRuntime::~NetworkBackendRuntime() = default;

bool NetworkBackendRuntime::ready() const noexcept { return false; }

bool NetworkBackendRuntime::loopback_smoke_test() const { return false; }

} // namespace easy3d
