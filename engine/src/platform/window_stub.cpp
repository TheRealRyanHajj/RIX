#include "platform/window.hpp"

namespace easy3d::platform {

void run_window_loop(const EngineConfig&,
                     const Scene*,
                     const std::atomic_bool&,
                     std::atomic_uint64_t&,
                     std::atomic<double>&,
                     std::atomic_uint32_t&,
                     std::atomic_uint32_t&,
                     RendererStatsAtomic&,
                     InputSystem&,
                     AudioSystem&,
                     Engine::FrameCallback) {
    throw EngineError("RIX was built without the Windows graphics backend");
}

} // namespace easy3d::platform

