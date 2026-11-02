#pragma once

#include "easy3d/core.hpp"

#include <atomic>
#include <cstdint>

namespace easy3d::platform {

void run_window_loop(const EngineConfig& config,
                     const Scene* scene,
                     const std::atomic_bool& stop_requested,
                     std::atomic_uint64_t& frame_count,
                     std::atomic<double>& last_frame_seconds,
                     std::atomic_uint32_t& viewport_width,
                     std::atomic_uint32_t& viewport_height,
                     RendererStatsAtomic& renderer_stats,
                     InputSystem& input,
                     AudioSystem& audio,
                     Engine::FrameCallback frame_callback);

} // namespace easy3d::platform

