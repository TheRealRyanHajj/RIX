# Third-party notices and immutable pins

Easy3D is private/proprietary, but the following build and runtime components
retain their own permissive licenses. Full license texts are present in each
fetched source tree during configuration; release packaging must reproduce all
applicable notices.

| Component | Phase 0 pin | License | Use |
|---|---|---|---|
| SDL | `829a65d769d935c4852f8159e964312c0957260a` (`release-3.4.18`) | zlib | Native window and events |
| bgfx.cmake | `1af3832b87ad0588c05f1f0bd7ee17a7b14d2315` | CC0-1.0 | CMake integration |
| bgfx | `b2513038f4b753ebeced40821c193978daa0492f` | BSD-2-Clause | Renderer |
| bx | `da13683750ff8df8f44a5a15f637b6ae9460a04b` | BSD-2-Clause | bgfx support library |
| bimg | `64a34f7441af8f06e40ccab08d76bbf5e59e55b1` | BSD-2-Clause | bgfx image support |
| pybind11 | `3.1.0` | BSD-3-Clause | Python native binding |
| scikit-build-core | `1.1.1` | Apache-2.0 | Python build backend |
| pytest | `9.2.0` (development extra only) | MIT | Python tests |
| MinGW-w64 runtime | compiler-matched (diagnostic GNU builds only) | MinGW-w64 runtime terms | GNU runtime support; MSVC builds do not include it |

This inventory is not a claim that transitive OS/compiler components are
redistributed. Before shipping a wheel, audit the actual wheel contents and
include the corresponding complete license texts.

