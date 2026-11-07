cmake_minimum_required(VERSION 3.26)

file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION" easy3d_source_version LIMIT_COUNT 1)
if(NOT easy3d_source_version MATCHES "^[0-9]+\\.[0-9]+\\.[0-9]+$")
    message(FATAL_ERROR "VERSION must contain exactly one MAJOR.MINOR.PATCH release version")
endif()

project(RIX VERSION "${easy3d_source_version}" LANGUAGES C CXX)

include(CTest)
include(FetchContent)

if(DEFINED EASY3D_ENABLE_GRAPHICS AND NOT DEFINED RIX_ENABLE_GRAPHICS)
    set(RIX_ENABLE_GRAPHICS "${EASY3D_ENABLE_GRAPHICS}" CACHE BOOL
        "Build the SDL3/bgfx Windows window backend")
endif()
if(DEFINED EASY3D_ENABLE_NETWORKING AND NOT DEFINED RIX_ENABLE_NETWORKING)
    set(RIX_ENABLE_NETWORKING "${EASY3D_ENABLE_NETWORKING}" CACHE BOOL
        "Build the GameNetworkingSockets Windows backend")
endif()
if(DEFINED EASY3D_BUILD_PYTHON AND NOT DEFINED RIX_BUILD_PYTHON)
    set(RIX_BUILD_PYTHON "${EASY3D_BUILD_PYTHON}" CACHE BOOL
        "Build the Python extension")
endif()
if(DEFINED EASY3D_BUILD_BENCHMARKS AND NOT DEFINED RIX_BUILD_BENCHMARKS)
    set(RIX_BUILD_BENCHMARKS "${EASY3D_BUILD_BENCHMARKS}" CACHE BOOL
        "Build the tiny native benchmark harness")
endif()
if(DEFINED EASY3D_REGENERATE_SHADERS AND NOT DEFINED RIX_REGENERATE_SHADERS)
    set(RIX_REGENERATE_SHADERS "${EASY3D_REGENERATE_SHADERS}" CACHE BOOL
        "Build shaderc and regenerate committed D3D11 shaders")
endif()

option(RIX_ENABLE_GRAPHICS "Build the SDL3/bgfx Windows window backend" ${WIN32})
option(RIX_ENABLE_NETWORKING "Build the GameNetworkingSockets Windows backend" ${WIN32})
option(RIX_BUILD_PYTHON "Build the Python extension" ON)
option(RIX_BUILD_BENCHMARKS "Build the tiny native benchmark harness" ON)
option(RIX_REGENERATE_SHADERS "Build shaderc and regenerate committed D3D11 shaders" OFF)

if(RIX_ENABLE_GRAPHICS AND NOT WIN32)
    message(FATAL_ERROR "The Phase 0 graphics backend currently supports Windows only")
endif()
if(RIX_ENABLE_NETWORKING AND NOT WIN32)
    message(FATAL_ERROR "The initial GameNetworkingSockets backend supports Windows only")
endif()

configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/engine/include/easy3d/version.hpp.in"
    "${CMAKE_CURRENT_BINARY_DIR}/generated/easy3d/version.hpp"
    @ONLY
)

# GLM 1.0.1. RIX owns its public math types; GLM remains private.
set(GLM_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(GLM_BUILD_INSTALL OFF CACHE BOOL "" FORCE)
set(GLM_ENABLE_CXX_20 ON CACHE BOOL "" FORCE)
FetchContent_Declare(
    glm
    GIT_REPOSITORY https://github.com/g-truc/glm.git
    GIT_TAG 0af55ccecd98d4e5a8d1fad7de25ba429d60e863
    GIT_SHALLOW FALSE
)
FetchContent_MakeAvailable(glm)

# tinyobjloader v2.0.0rc13. OBJ parsing stays private behind RIX assets.
set(TINYOBJLOADER_BUILD_TEST_LOADER OFF CACHE BOOL "" FORCE)
FetchContent_Declare(
    tinyobjloader
    GIT_REPOSITORY https://github.com/tinyobjloader/tinyobjloader.git
    GIT_TAG 2945a967c5303b2c8c14174117c45f3302591150
    GIT_SHALLOW FALSE
)
set(easy3d_saved_skip_install_rules "${CMAKE_SKIP_INSTALL_RULES}")
set(CMAKE_SKIP_INSTALL_RULES ON)
FetchContent_MakeAvailable(tinyobjloader)
set(CMAKE_SKIP_INSTALL_RULES "${easy3d_saved_skip_install_rules}")
unset(easy3d_saved_skip_install_rules)
# tinyobjloader is a private static implementation detail. Suppress its
# headers, library and package metadata from editable wheels while satisfying
# CMake's parent install-script inclusion.
file(WRITE "${tinyobjloader_BINARY_DIR}/cmake_install.cmake"
    "# tinyobjloader is statically linked and not installed.\n")

# cgltf 1.15. Header-only glTF 2.0 parsing remains private to assets.
FetchContent_Declare(
    cgltf
    GIT_REPOSITORY https://github.com/jkuhlmann/cgltf.git
    GIT_TAG bbeb5b0b070ddacddac6852fb72143eb68454937
    GIT_SHALLOW FALSE
)
FetchContent_MakeAvailable(cgltf)

# Jolt Physics 5.6.0. The native integration remains private behind RIX's
# world/body handles and is built as a static, CPU-only library.
set(JPH_BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(OVERRIDE_CXX_FLAGS OFF CACHE BOOL "" FORCE)
set(INTERPROCEDURAL_OPTIMIZATION OFF CACHE BOOL "" FORCE)
set(ENABLE_ALL_WARNINGS OFF CACHE BOOL "" FORCE)
set(ENABLE_INSTALL OFF CACHE BOOL "" FORCE)
set(USE_STATIC_MSVC_RUNTIME_LIBRARY OFF CACHE BOOL "" FORCE)
set(CPP_EXCEPTIONS_ENABLED ON CACHE BOOL "" FORCE)
set(CPP_RTTI_ENABLED ON CACHE BOOL "" FORCE)
set(FLOATING_POINT_EXCEPTIONS_ENABLED OFF CACHE BOOL "" FORCE)
set(DEBUG_RENDERER_IN_DEBUG_AND_RELEASE OFF CACHE BOOL "" FORCE)
set(PROFILER_IN_DEBUG_AND_RELEASE OFF CACHE BOOL "" FORCE)
set(ENABLE_OBJECT_STREAM OFF CACHE BOOL "" FORCE)
set(JPH_USE_DX12 OFF CACHE BOOL "" FORCE)
set(JPH_USE_VK OFF CACHE BOOL "" FORCE)
set(JPH_USE_MTL OFF CACHE BOOL "" FORCE)
set(JPH_USE_CPU_COMPUTE OFF CACHE BOOL "" FORCE)
set(USE_SSE4_1 OFF CACHE BOOL "" FORCE)
set(USE_SSE4_2 OFF CACHE BOOL "" FORCE)
set(USE_AVX OFF CACHE BOOL "" FORCE)
set(USE_AVX2 OFF CACHE BOOL "" FORCE)
set(USE_AVX512 OFF CACHE BOOL "" FORCE)
set(USE_LZCNT OFF CACHE BOOL "" FORCE)
set(USE_TZCNT OFF CACHE BOOL "" FORCE)
set(USE_F16C OFF CACHE BOOL "" FORCE)
set(USE_FMADD OFF CACHE BOOL "" FORCE)
FetchContent_Declare(
    JoltPhysics
    GIT_REPOSITORY https://github.com/jrouwe/JoltPhysics.git
    GIT_TAG e77f175595e64cb44218cc9d9d56fc365ad0e36a
    GIT_SHALLOW FALSE
    SOURCE_SUBDIR Build
)
FetchContent_MakeAvailable(JoltPhysics)

if(RIX_ENABLE_NETWORKING)
    # Protobuf 5.29.3. Build protoc and its exactly matching static runtime from
    # the same immutable source so generated GameNetworkingSockets messages
    # cannot acquire a host/runtime version mismatch.
    set(easy3d_saved_cxx_standard "${CMAKE_CXX_STANDARD}")
    set(easy3d_saved_cxx_standard_required "${CMAKE_CXX_STANDARD_REQUIRED}")
    set(CMAKE_CXX_STANDARD 17)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)
    set(protobuf_BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(protobuf_BUILD_CONFORMANCE OFF CACHE BOOL "" FORCE)
    set(protobuf_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(protobuf_BUILD_PROTOBUF_BINARIES ON CACHE BOOL "" FORCE)
    set(protobuf_BUILD_PROTOC_BINARIES ON CACHE BOOL "" FORCE)
    set(protobuf_BUILD_LIBPROTOC ON CACHE BOOL "" FORCE)
    set(protobuf_BUILD_LIBUPB OFF CACHE BOOL "" FORCE)
    set(protobuf_BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
    set(protobuf_MSVC_STATIC_RUNTIME OFF CACHE BOOL "" FORCE)
    set(protobuf_INSTALL OFF CACHE BOOL "" FORCE)
    set(ABSL_PROPAGATE_CXX_STD ON CACHE BOOL "" FORCE)
    set(ABSL_ENABLE_INSTALL OFF CACHE BOOL "" FORCE)
    FetchContent_Declare(
        Protobuf
        GIT_REPOSITORY https://github.com/protocolbuffers/protobuf.git
        GIT_TAG b407e8416e3893036aee5af9a12bd9b6a0e2b2e6
        GIT_SHALLOW FALSE
        GIT_SUBMODULES_RECURSE TRUE
        OVERRIDE_FIND_PACKAGE
    )
    FetchContent_MakeAvailable(Protobuf)

    include("${protobuf_SOURCE_DIR}/cmake/protobuf-generate.cmake")
    if(NOT COMMAND protobuf_generate_cpp)
        function(protobuf_generate_cpp output_sources output_headers)
            set(proto_files ${ARGN})
            if(NOT proto_files)
                message(SEND_ERROR "protobuf_generate_cpp requires .proto inputs")
                return()
            endif()
            protobuf_generate(
                APPEND_PATH
                LANGUAGE cpp
                OUT_VAR generated_files
                PROTOS ${proto_files}
            )
            set(generated_sources)
            set(generated_headers)
            foreach(generated_file IN LISTS generated_files)
                if(generated_file MATCHES "cc$")
                    list(APPEND generated_sources "${generated_file}")
                else()
                    list(APPEND generated_headers "${generated_file}")
                endif()
            endforeach()
            set(${output_sources} ${generated_sources} PARENT_SCOPE)
            set(${output_headers} ${generated_headers} PARENT_SCOPE)
        endfunction()
    endif()
    set(Protobuf_VERSION "${protobuf_VERSION}")

    # GameNetworkingSockets 1.6.1. BCrypt avoids an extra redistributable
    # crypto library. ICE/WebRTC remains disabled for this direct-IP backend.
    set(BUILD_STATIC_LIB ON CACHE BOOL "" FORCE)
    set(BUILD_SHARED_LIB OFF CACHE BOOL "" FORCE)
    set(BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(BUILD_TOOLS OFF CACHE BOOL "" FORCE)
    set(ENABLE_ICE OFF CACHE BOOL "" FORCE)
    set(USE_STEAMWEBRTC OFF CACHE BOOL "" FORCE)
    set(USE_CRYPTO "BCrypt" CACHE STRING "" FORCE)
    set(Protobuf_USE_STATIC_LIBS ON CACHE BOOL "" FORCE)
    FetchContent_Declare(
        GameNetworkingSockets
        GIT_REPOSITORY https://github.com/ValveSoftware/GameNetworkingSockets.git
        GIT_TAG d534c19aa760df3fb75fd20db13ba1932b8a5463
        GIT_SHALLOW FALSE
    )
    set(easy3d_saved_skip_install_rules "${CMAKE_SKIP_INSTALL_RULES}")
    set(CMAKE_SKIP_INSTALL_RULES ON)
    FetchContent_MakeAvailable(GameNetworkingSockets)
    set(CMAKE_SKIP_INSTALL_RULES "${easy3d_saved_skip_install_rules}")
    unset(easy3d_saved_skip_install_rules)
    file(WRITE "${gamenetworkingsockets_BINARY_DIR}/cmake_install.cmake"
        "# GameNetworkingSockets is statically linked and not installed.\n")
    if(easy3d_saved_cxx_standard)
        set(CMAKE_CXX_STANDARD "${easy3d_saved_cxx_standard}")
    else()
        unset(CMAKE_CXX_STANDARD)
    endif()
    if(easy3d_saved_cxx_standard_required)
        set(CMAKE_CXX_STANDARD_REQUIRED "${easy3d_saved_cxx_standard_required}")
    else()
        unset(CMAKE_CXX_STANDARD_REQUIRED)
    endif()
    unset(easy3d_saved_cxx_standard)
    unset(easy3d_saved_cxx_standard_required)
endif()

set(easy3d_core_sources
    engine/src/audio/audio.cpp
    engine/src/assets/image.cpp
    engine/src/assets/gltf.cpp
    engine/src/assets/model.cpp
    engine/src/core/engine.cpp
    engine/src/input/input.cpp
    engine/src/math/math.cpp
    engine/src/network/network.cpp
    engine/src/network/protocol.cpp
    engine/src/physics/physics.cpp
    engine/src/renderer/camera.cpp
    engine/src/renderer/mesh.cpp
    engine/src/scene/scene.cpp
)

if(RIX_ENABLE_NETWORKING)
    list(APPEND easy3d_core_sources
        engine/src/network/backend_gns.cpp
        engine/src/network/client_gns.cpp
        engine/src/network/server_gns.cpp
    )
else()
    list(APPEND easy3d_core_sources
        engine/src/network/backend_stub.cpp
        engine/src/network/client_stub.cpp
        engine/src/network/server_stub.cpp
    )
endif()

if(RIX_ENABLE_GRAPHICS)
    # SDL 3.4.18, immutable release commit.
    set(SDL_SHARED OFF CACHE BOOL "" FORCE)
    set(SDL_STATIC ON CACHE BOOL "" FORCE)
    set(SDL_TEST_LIBRARY OFF CACHE BOOL "" FORCE)
    set(SDL_TESTS OFF CACHE BOOL "" FORCE)
    set(SDL_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(SDL_INSTALL OFF CACHE BOOL "" FORCE)
    FetchContent_Declare(
        SDL3
        GIT_REPOSITORY https://github.com/libsdl-org/SDL.git
        GIT_TAG 829a65d769d935c4852f8159e964312c0957260a
        GIT_SHALLOW FALSE
    )
    FetchContent_MakeAvailable(SDL3)

    # Official bgfx CMake integration. This commit pins bgfx, bx and bimg too.
    # Runtime builds consume reviewed DXBC headers committed beside their
    # source. Maintainers can explicitly rebuild them with the pinned shaderc.
    set(BGFX_BUILD_TOOLS ${RIX_REGENERATE_SHADERS} CACHE BOOL "" FORCE)
    set(BGFX_BUILD_TOOLS_BIN2C OFF CACHE BOOL "" FORCE)
    set(BGFX_BUILD_TOOLS_SHADER ${RIX_REGENERATE_SHADERS} CACHE BOOL "" FORCE)
    set(BGFX_BUILD_TOOLS_GEOMETRY OFF CACHE BOOL "" FORCE)
    set(BGFX_BUILD_TOOLS_TEXTURE OFF CACHE BOOL "" FORCE)
    set(BGFX_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(BGFX_BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(BGFX_INSTALL OFF CACHE BOOL "" FORCE)
    set(BGFX_CUSTOM_TARGETS OFF CACHE BOOL "" FORCE)
    set(BGFX_CONFIG_RENDERER_WEBGPU OFF CACHE BOOL "" FORCE)
    set(BGFX_CONFIG_VIDEO OFF CACHE BOOL "" FORCE)
    FetchContent_Declare(
        bgfx_cmake
        GIT_REPOSITORY https://github.com/bkaradzic/bgfx.cmake.git
        GIT_TAG 1af3832b87ad0588c05f1f0bd7ee17a7b14d2315
        GIT_SHALLOW FALSE
    )
    FetchContent_MakeAvailable(bgfx_cmake)
    FetchContent_GetProperties(bgfx SOURCE_DIR EASY3D_BGFX_SOURCE_DIR)
    list(APPEND easy3d_core_sources
        engine/src/platform/window_win32.cpp
        engine/src/renderer/bgfx_renderer.cpp
    )

    set(EASY3D_SHADER_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/engine/src/renderer/shaders")
    if(RIX_REGENERATE_SHADERS)
        set(BGFX_SHADER_INCLUDE_PATH "${EASY3D_BGFX_SOURCE_DIR}/src")
        set(EASY3D_SHADER_INCLUDE_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated/shaders/dxbc")
        bgfx_compile_shaders(
            TYPE VERTEX
            SHADERS
                "${EASY3D_SHADER_SOURCE_DIR}/vs_solid_color.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/vs_solid_color_instanced.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/vs_textured.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/vs_textured_instanced.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/vs_postprocess.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/vs_shadow.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/vs_shadow_instanced.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/vs_point_shadow.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/vs_point_shadow_instanced.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/vs_ui.sc"
            VARYING_DEF "${EASY3D_SHADER_SOURCE_DIR}/varying.def.sc"
            OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated/shaders"
            OUT_FILES_VAR EASY3D_VERTEX_SHADER_HEADERS
            PROFILES s_5_0
            AS_HEADERS
        )
        bgfx_compile_shaders(
            TYPE FRAGMENT
            SHADERS
                "${EASY3D_SHADER_SOURCE_DIR}/fs_solid_color.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/fs_textured.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/fs_postprocess.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/fs_sky.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/fs_shadow.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/fs_point_shadow.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/fs_ui.sc"
            VARYING_DEF "${EASY3D_SHADER_SOURCE_DIR}/varying.def.sc"
            OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated/shaders"
            OUT_FILES_VAR EASY3D_FRAGMENT_SHADER_HEADERS
            PROFILES s_5_0
            AS_HEADERS
        )
        list(APPEND easy3d_core_sources
            ${EASY3D_VERTEX_SHADER_HEADERS}
            ${EASY3D_FRAGMENT_SHADER_HEADERS}
        )
    else()
        set(EASY3D_SHADER_INCLUDE_DIR "${EASY3D_SHADER_SOURCE_DIR}/generated/dxbc")
        list(APPEND easy3d_core_sources
            "${EASY3D_SHADER_INCLUDE_DIR}/vs_solid_color.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/vs_solid_color_instanced.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/fs_solid_color.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/vs_textured.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/vs_textured_instanced.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/fs_textured.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/vs_postprocess.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/fs_postprocess.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/fs_sky.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/vs_shadow.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/vs_shadow_instanced.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/vs_point_shadow.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/vs_point_shadow_instanced.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/fs_shadow.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/fs_point_shadow.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/vs_ui.sc.bin.h"
            "${EASY3D_SHADER_INCLUDE_DIR}/fs_ui.sc.bin.h"
        )
    endif()
else()
    list(APPEND easy3d_core_sources engine/src/platform/window_stub.cpp)
endif()

add_library(easy3d_core STATIC ${easy3d_core_sources})
add_library(Easy3D::core ALIAS easy3d_core)
add_library(RIX::core ALIAS easy3d_core)
target_compile_features(easy3d_core PUBLIC cxx_std_20)
set_target_properties(easy3d_core PROPERTIES
    CXX_EXTENSIONS OFF
    POSITION_INDEPENDENT_CODE ON
)
target_include_directories(easy3d_core
    PUBLIC
        "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/engine/include>"
        "$<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/generated>"
    PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/engine/src"
        "${cgltf_SOURCE_DIR}"
)
target_link_libraries(easy3d_core PRIVATE glm::glm tinyobjloader Jolt)

if(RIX_ENABLE_NETWORKING)
    target_compile_definitions(easy3d_core PRIVATE EASY3D_HAS_GNS=1)
    target_link_libraries(easy3d_core PRIVATE GameNetworkingSockets::static)
endif()

if(MSVC)
    target_compile_options(easy3d_core PRIVATE /W4 /permissive- /EHsc /Zc:__cplusplus)
else()
    target_compile_options(easy3d_core PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
endif()

if(RIX_ENABLE_GRAPHICS)
    target_compile_definitions(easy3d_core PRIVATE EASY3D_HAS_GRAPHICS=1)
    target_include_directories(easy3d_core PRIVATE
        "${EASY3D_SHADER_INCLUDE_DIR}"
        "${EASY3D_BGFX_SOURCE_DIR}/3rdparty/stb"
        "${EASY3D_BGFX_SOURCE_DIR}/examples/common/imgui"
    )
    target_link_libraries(easy3d_core PRIVATE SDL3::SDL3-static bgfx bimg bimg_decode bimg_encode)
endif()

if(RIX_BUILD_PYTHON)
    find_package(pybind11 CONFIG REQUIRED)
    pybind11_add_module(_rix MODULE bindings/module.cpp)
    target_compile_features(_rix PRIVATE cxx_std_20)
    target_link_libraries(_rix PRIVATE RIX::core)
    if(MSVC)
        target_compile_options(_rix PRIVATE /W4 /permissive- /EHsc /Zc:__cplusplus)
    else()
        target_compile_options(_rix PRIVATE -Wall -Wextra -Wpedantic)
    endif()
    if(MINGW)
        # Keep diagnostic MinGW builds self-contained. The supported release
        # toolchain remains MSVC, whose runtime handling is different.
        target_link_options(_rix PRIVATE -static-libgcc -static-libstdc++)
        target_link_libraries(_rix PRIVATE "-Wl,-Bstatic" winpthread "-Wl,-Bdynamic")
        get_filename_component(EASY3D_MINGW_BIN_DIR "${CMAKE_CXX_COMPILER}" DIRECTORY)
        set(EASY3D_MINGW_WINPTHREAD_DLL
            "${EASY3D_MINGW_BIN_DIR}/libwinpthread-1.dll")
        if(EXISTS "${EASY3D_MINGW_WINPTHREAD_DLL}")
            install(FILES "${EASY3D_MINGW_WINPTHREAD_DLL}" DESTINATION rix)
        endif()
    endif()
    install(TARGETS _rix
        LIBRARY DESTINATION rix
        RUNTIME DESTINATION rix
    )
endif()

if(BUILD_TESTING)
    add_executable(easy3d_core_tests tests/cpp/test_core.cpp)
    target_compile_features(easy3d_core_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_core_tests PRIVATE RIX::core)
    add_test(NAME rix.core COMMAND easy3d_core_tests)

    add_executable(easy3d_scene_tests tests/cpp/test_scene.cpp)
    target_compile_features(easy3d_scene_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_scene_tests PRIVATE RIX::core)
    add_test(NAME rix.scene COMMAND easy3d_scene_tests)

    add_executable(easy3d_math_transform_tests tests/cpp/test_math_transform.cpp)
    target_compile_features(easy3d_math_transform_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_math_transform_tests PRIVATE RIX::core)
    add_test(NAME rix.math_transform COMMAND easy3d_math_transform_tests)

    add_executable(easy3d_mesh_tests tests/cpp/test_mesh.cpp)
    target_compile_features(easy3d_mesh_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_mesh_tests PRIVATE RIX::core)
    add_test(NAME rix.mesh COMMAND easy3d_mesh_tests)

    add_executable(easy3d_camera_tests tests/cpp/test_camera.cpp)
    target_compile_features(easy3d_camera_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_camera_tests PRIVATE RIX::core)
    add_test(NAME rix.camera COMMAND easy3d_camera_tests)

    add_executable(easy3d_model_tests tests/cpp/test_model.cpp)
    target_compile_features(easy3d_model_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_model_tests PRIVATE RIX::core)
    add_test(NAME rix.model COMMAND easy3d_model_tests)

    add_executable(easy3d_gltf_tests tests/cpp/test_gltf.cpp)
    target_compile_features(easy3d_gltf_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_gltf_tests PRIVATE RIX::core)
    add_test(NAME rix.gltf COMMAND easy3d_gltf_tests)

    add_executable(easy3d_render_component_tests tests/cpp/test_render_components.cpp)
    target_compile_features(easy3d_render_component_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_render_component_tests PRIVATE RIX::core)
    add_test(NAME rix.render_components COMMAND easy3d_render_component_tests)

    add_executable(easy3d_lighting_debug_tests tests/cpp/test_lighting_debug.cpp)
    target_compile_features(easy3d_lighting_debug_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_lighting_debug_tests PRIVATE RIX::core)
    add_test(NAME rix.lighting_debug COMMAND easy3d_lighting_debug_tests)

    add_executable(easy3d_frustum_tests tests/cpp/test_frustum.cpp)
    target_compile_features(easy3d_frustum_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_frustum_tests PRIVATE RIX::core)
    add_test(NAME rix.frustum COMMAND easy3d_frustum_tests)

    add_executable(easy3d_input_tests tests/cpp/test_input.cpp)
    target_compile_features(easy3d_input_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_input_tests PRIVATE RIX::core)
    add_test(NAME rix.input COMMAND easy3d_input_tests)

    add_executable(easy3d_audio_tests tests/cpp/test_audio.cpp)
    target_compile_features(easy3d_audio_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_audio_tests PRIVATE RIX::core)
    add_test(NAME rix.audio COMMAND easy3d_audio_tests)

    add_executable(easy3d_network_tests tests/cpp/test_network.cpp)
    target_compile_features(easy3d_network_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_network_tests PRIVATE RIX::core)
    add_test(NAME rix.network COMMAND easy3d_network_tests)

    add_executable(easy3d_network_protocol_tests tests/cpp/test_network_protocol.cpp)
    target_compile_features(easy3d_network_protocol_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_network_protocol_tests PRIVATE RIX::core)
    add_test(NAME rix.network_protocol COMMAND easy3d_network_protocol_tests)

    if(RIX_ENABLE_NETWORKING)
        add_executable(easy3d_network_backend_tests tests/cpp/test_network_backend.cpp)
        target_compile_features(easy3d_network_backend_tests PRIVATE cxx_std_20)
        target_link_libraries(easy3d_network_backend_tests PRIVATE RIX::core)
        add_test(NAME rix.network_backend COMMAND easy3d_network_backend_tests)

        add_executable(easy3d_network_client_tests tests/cpp/test_network_client.cpp)
        target_compile_features(easy3d_network_client_tests PRIVATE cxx_std_20)
        target_link_libraries(easy3d_network_client_tests
            PRIVATE RIX::core GameNetworkingSockets::static)
        add_test(NAME rix.network_client COMMAND easy3d_network_client_tests)

        add_executable(easy3d_network_server_tests tests/cpp/test_network_server.cpp)
        target_compile_features(easy3d_network_server_tests PRIVATE cxx_std_20)
        target_link_libraries(easy3d_network_server_tests
            PRIVATE RIX::core GameNetworkingSockets::static)
        add_test(NAME rix.network_server COMMAND easy3d_network_server_tests)
    endif()

    add_executable(easy3d_physics_tests tests/cpp/test_physics.cpp)
    target_compile_features(easy3d_physics_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_physics_tests PRIVATE RIX::core)
    add_test(NAME rix.physics COMMAND easy3d_physics_tests)

    if(RIX_ENABLE_GRAPHICS)
        add_executable(easy3d_texture_tests tests/cpp/test_texture.cpp)
        target_compile_features(easy3d_texture_tests PRIVATE cxx_std_20)
        target_link_libraries(easy3d_texture_tests PRIVATE RIX::core)
        add_test(NAME rix.texture COMMAND easy3d_texture_tests)
    endif()
endif()

if(RIX_BUILD_BENCHMARKS)
    add_executable(easy3d_core_benchmark tests/cpp/benchmark_core.cpp)
    target_compile_features(easy3d_core_benchmark PRIVATE cxx_std_20)
    target_link_libraries(easy3d_core_benchmark PRIVATE RIX::core)
endif()

if(RIX_ENABLE_GRAPHICS)
    # Visible/manual diagnostic only: never registered with CTest.
    add_executable(easy3d_window_lifecycle tests/cpp/window_lifecycle.cpp)
    target_compile_features(easy3d_window_lifecycle PRIVATE cxx_std_20)
    target_link_libraries(easy3d_window_lifecycle PRIVATE RIX::core)

    add_executable(easy3d_geometry_lifecycle tests/cpp/geometry_lifecycle.cpp)
    target_compile_features(easy3d_geometry_lifecycle PRIVATE cxx_std_20)
    target_link_libraries(easy3d_geometry_lifecycle PRIVATE RIX::core)
endif()

