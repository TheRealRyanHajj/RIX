#include "easy3d/network.hpp"

#include <steam/steamnetworkingsockets.h>
#include <steam/isteamnetworkingutils.h>

#include <chrono>
#include <cmath>
#include <cstring>
#include <mutex>
#include <thread>

namespace easy3d {
namespace {

std::mutex runtime_mutex;
std::size_t runtime_owners = 0;
std::mutex impairment_mutex;

} // namespace

NetworkBackendInfo network_backend_info() {
    return {true, "GameNetworkingSockets", "1.6.1", "Windows BCrypt"};
}

void set_network_backend_impairment(
    const std::int32_t lag_milliseconds,
    const float jitter_average_milliseconds,
    const float jitter_maximum_milliseconds,
    const float loss_percent) {
    if (lag_milliseconds < 0 || lag_milliseconds > 5000 ||
        !std::isfinite(jitter_average_milliseconds) ||
        !std::isfinite(jitter_maximum_milliseconds) ||
        jitter_average_milliseconds < 0.0F ||
        jitter_average_milliseconds > 2000.0F ||
        jitter_maximum_milliseconds < jitter_average_milliseconds ||
        jitter_maximum_milliseconds > 5000.0F ||
        !std::isfinite(loss_percent) || loss_percent < 0.0F ||
        loss_percent > 100.0F) {
        throw std::invalid_argument("network impairment values are outside backend bounds");
    }
    const std::scoped_lock lock(impairment_mutex);
    ISteamNetworkingUtils* const utilities = SteamNetworkingUtils();
    if (utilities == nullptr) {
        throw NetworkError(
            "GameNetworkingSockets must be initialized before applying impairment");
    }
    const float jitter_percent = jitter_average_milliseconds > 0.0F ? 100.0F : 0.0F;
    const bool applied =
        utilities->SetGlobalConfigValueInt32(
            k_ESteamNetworkingConfig_FakePacketLag_Send, lag_milliseconds) &&
        utilities->SetGlobalConfigValueFloat(
            k_ESteamNetworkingConfig_FakePacketLoss_Send, loss_percent) &&
        utilities->SetGlobalConfigValueFloat(
            k_ESteamNetworkingConfig_FakePacketJitter_Send_Avg,
            jitter_average_milliseconds) &&
        utilities->SetGlobalConfigValueFloat(
            k_ESteamNetworkingConfig_FakePacketJitter_Send_Max,
            jitter_maximum_milliseconds) &&
        utilities->SetGlobalConfigValueFloat(
            k_ESteamNetworkingConfig_FakePacketJitter_Send_Pct,
            jitter_percent);
    if (!applied) {
        throw NetworkError("GameNetworkingSockets rejected impairment settings");
    }
}

void clear_network_backend_impairment() {
    const std::scoped_lock lock(impairment_mutex);
    ISteamNetworkingUtils* const utilities = SteamNetworkingUtils();
    if (utilities == nullptr) return;
    utilities->SetGlobalConfigValueInt32(k_ESteamNetworkingConfig_FakePacketLag_Send, 0);
    utilities->SetGlobalConfigValueFloat(k_ESteamNetworkingConfig_FakePacketLoss_Send, 0.0F);
    utilities->SetGlobalConfigValueFloat(
        k_ESteamNetworkingConfig_FakePacketJitter_Send_Avg, 0.0F);
    utilities->SetGlobalConfigValueFloat(
        k_ESteamNetworkingConfig_FakePacketJitter_Send_Max, 100.0F);
    utilities->SetGlobalConfigValueFloat(
        k_ESteamNetworkingConfig_FakePacketJitter_Send_Pct, 0.0F);
}

NetworkBackendRuntime::NetworkBackendRuntime() {
    const std::scoped_lock lock(runtime_mutex);
    if (runtime_owners == 0) {
        SteamNetworkingErrMsg message{};
        if (!GameNetworkingSockets_Init(nullptr, message)) {
            throw NetworkError(std::string{"GameNetworkingSockets initialization failed: "} +
                               message);
        }
    }
    ++runtime_owners;
    acquired_ = true;
}

NetworkBackendRuntime::~NetworkBackendRuntime() {
    const std::scoped_lock lock(runtime_mutex);
    if (!acquired_) {
        return;
    }
    acquired_ = false;
    if (--runtime_owners == 0) {
        GameNetworkingSockets_Kill();
    }
}

bool NetworkBackendRuntime::ready() const noexcept {
    const std::scoped_lock lock(runtime_mutex);
    return acquired_ && runtime_owners > 0 && SteamNetworkingSockets() != nullptr;
}

bool NetworkBackendRuntime::loopback_smoke_test() const {
    if (!ready()) {
        throw NetworkError("GameNetworkingSockets runtime is not initialized");
    }

    ISteamNetworkingSockets* const sockets = SteamNetworkingSockets();
    HSteamNetConnection sender = k_HSteamNetConnection_Invalid;
    HSteamNetConnection receiver = k_HSteamNetConnection_Invalid;
    if (!sockets->CreateSocketPair(&sender, &receiver, true, nullptr, nullptr)) {
        throw NetworkError("GameNetworkingSockets could not create a loopback socket pair");
    }

    const auto close_pair = [&]() {
        sockets->CloseConnection(sender, 0, "Easy3D backend smoke complete", false);
        sockets->CloseConnection(receiver, 0, "Easy3D backend smoke complete", false);
    };
    constexpr char payload[] = "easy3d-gns-smoke";
    const EResult result = sockets->SendMessageToConnection(
        sender, payload, sizeof(payload), k_nSteamNetworkingSend_Reliable, nullptr);
    if (result != k_EResultOK) {
        close_pair();
        throw NetworkError("GameNetworkingSockets loopback send was rejected");
    }

    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (std::chrono::steady_clock::now() < deadline) {
        sockets->RunCallbacks();
        SteamNetworkingMessage_t* message = nullptr;
        if (sockets->ReceiveMessagesOnConnection(receiver, &message, 1) == 1) {
            const bool matches =
                message->m_cbSize == static_cast<int>(sizeof(payload)) &&
                std::memcmp(message->m_pData, payload, sizeof(payload)) == 0;
            message->Release();
            close_pair();
            return matches;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    close_pair();
    throw NetworkError("GameNetworkingSockets loopback receive timed out");
}

} // namespace easy3d
