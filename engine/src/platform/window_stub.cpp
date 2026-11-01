#include "platform/window.hpp"

namespace easy3d::platform {

void run_window_loop(const EngineConfig&,
                     const Scene*,
                     const std::atomic_bool&,
                     std::atomic_uint64_t&,
                     std::atomic<double>&,
                     RendererStatsAtomic&,
                     InputSystem&,
                     Engine::FrameCallback) {
    throw EngineError("Easy3D was built without the Windows graphics backend");
}

} // namespace easy3d::platform

