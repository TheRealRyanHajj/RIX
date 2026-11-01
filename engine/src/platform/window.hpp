#pragma once

#include "easy3d/core.hpp"

#include <atomic>
#include <cstdint>

namespace easy3d::platform {

void run_window_loop(const EngineConfig& config,
                     const std::atomic_bool& stop_requested,
                     std::atomic_uint64_t& frame_count,
                     std::atomic<double>& last_frame_seconds);

} // namespace easy3d::platform

