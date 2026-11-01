#include "easy3d/core.hpp"

#include <chrono>
#include <cstdint>
#include <iostream>

int main() {
    constexpr std::int32_t iterations = 10'000'000;
    volatile int result = 0;
    const auto started = std::chrono::steady_clock::now();
    for (std::int32_t index = 0; index < iterations; ++index) {
        result = easy3d::native_add(result, index & 1);
    }
    const auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - started);
    std::cout << "iterations=" << iterations << " elapsed_seconds=" << elapsed.count()
              << " final_value=" << result << '\n';
    return 0;
}

