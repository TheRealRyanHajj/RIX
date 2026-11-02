# Third-party notices and immutable pins

Easy3D is private/proprietary, but the following build and runtime components
retain their own permissive licenses. Full license texts are present in each
fetched source tree during configuration; release packaging must reproduce all
applicable notices.

| Component | Immutable pin | License | Use |
|---|---|---|---|
| SDL | `829a65d769d935c4852f8159e964312c0957260a` (`release-3.4.18`) | zlib | Native window, events and audio-device output |
| bgfx.cmake | `1af3832b87ad0588c05f1f0bd7ee17a7b14d2315` | CC0-1.0 | CMake integration |
| bgfx | `b2513038f4b753ebeced40821c193978daa0492f` | BSD-2-Clause | Renderer |
| bx | `da13683750ff8df8f44a5a15f637b6ae9460a04b` | BSD-2-Clause | bgfx support library |
| bimg | `64a34f7441af8f06e40ccab08d76bbf5e59e55b1` | BSD-2-Clause | bgfx image support |
| LodePNG (bundled by bimg) | bimg pin above | zlib | PNG decoding |
| stb_image (bundled by bimg) | bimg pin above | MIT (selected alternative) | JPEG decoding |
| stb_truetype (bundled by bgfx) | bgfx pin above | MIT (selected alternative) | Built-in font atlas rasterization |
| Roboto Regular font data (bundled by bgfx) | bgfx pin above | Apache-2.0 | Built-in ASCII HUD text |
| GLM | `0af55ccecd98d4e5a8d1fad7de25ba429d60e863` (`1.0.1`) | MIT | Private native math implementation |
| tinyobjloader | `2945a967c5303b2c8c14174117c45f3302591150` (`v2.0.0rc13`) | MIT | OBJ/MTL parsing |
| cgltf | `bbeb5b0b070ddacddac6852fb72143eb68454937` (`v1.15`) | MIT | glTF 2.0/GLB parsing |
| Jolt Physics | `e77f175595e64cb44218cc9d9d56fc365ad0e36a` (`v5.6.0`) | MIT ([text](JoltPhysics.txt)) | Native rigid-body simulation |
| GameNetworkingSockets | `d534c19aa760df3fb75fd20db13ba1932b8a5463` (`v1.6.1`) | BSD-3-Clause | Private reliable/unreliable transport backend |
| Protocol Buffers | `b407e8416e3893036aee5af9a12bd9b6a0e2b2e6` (`v29.3`, C++ `5.29.3`) | BSD-3-Clause | GNS message generation/runtime |
| Abseil | `4a2c63365eff8823a5221db86ef490e828306f9d` | Apache-2.0 | Protobuf support library |
| utf8_range (bundled by Protobuf) | Protobuf pin above | MIT | Protobuf UTF-8 validation |
| Windows BCrypt | Windows operating-system component | Microsoft Windows | GNS AES/SHA provider; not redistributed |
| pybind11 | `3.1.0` | BSD-3-Clause | Python native binding |
| scikit-build-core | `1.1.1` | Apache-2.0 | Python build backend |
| pytest | `9.2.0` (development extra only) | MIT | Python tests |
| MinGW-w64 runtime | compiler-matched (diagnostic GNU builds only) | MinGW-w64 runtime terms | GNU runtime support; MSVC builds do not include it |

This inventory is not a claim that transitive OS/compiler components are
redistributed. Before shipping a wheel, audit the actual wheel contents and
include the corresponding complete license texts.

