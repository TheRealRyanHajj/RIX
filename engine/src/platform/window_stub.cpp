#include "platform/window.hpp"

namespace easy3d::platform {

void run_window_loop(const EngineConfig&,
                     const std::atomic_bool&,
                     std::atomic_uint64_t&,
                     std::atomic<double>&) {
    throw EngineError("Easy3D was built without the Windows graphics backend");
}

} // namespace easy3d::platform

