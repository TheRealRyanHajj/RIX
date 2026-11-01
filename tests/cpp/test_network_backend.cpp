#include "easy3d/network.hpp"

#include <iostream>
#include <stdexcept>

namespace {

int fail(const int code, const char* const message) {
    std::cerr << message << '\n';
    return code;
}

} // namespace

int main() {
    try {
        const easy3d::NetworkBackendInfo info = easy3d::network_backend_info();
        if (!info.available || info.name != "GameNetworkingSockets" ||
            info.version != "1.6.1" || info.crypto_provider != "Windows BCrypt") {
            return fail(1, "GameNetworkingSockets backend metadata is incorrect");
        }

        easy3d::NetworkBackendRuntime outer;
        if (!outer.ready()) {
            return fail(2, "GameNetworkingSockets runtime did not initialize");
        }
        {
            easy3d::NetworkBackendRuntime nested;
            if (!nested.ready() || !nested.loopback_smoke_test()) {
                return fail(3, "GameNetworkingSockets loopback smoke test failed");
            }
        }
        if (!outer.ready() || !outer.loopback_smoke_test()) {
            return fail(4, "nested runtime teardown killed the shared backend");
        }

        std::cout << "easy3d_network_backend_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "easy3d_network_backend_tests: FAIL: " << error.what() << '\n';
        return 5;
    }
}
