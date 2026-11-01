cmake_minimum_required(VERSION 3.26)

project(Easy3D VERSION 0.1.0 LANGUAGES CXX)

include(CTest)
include(FetchContent)

option(EASY3D_ENABLE_GRAPHICS "Build the SDL3/bgfx Windows window backend" ${WIN32})
option(EASY3D_BUILD_PYTHON "Build the Python extension" ON)
option(EASY3D_BUILD_BENCHMARKS "Build the tiny native benchmark harness" ON)
option(EASY3D_REGENERATE_SHADERS "Build shaderc and regenerate committed D3D11 shaders" OFF)

if(EASY3D_ENABLE_GRAPHICS AND NOT WIN32)
    message(FATAL_ERROR "The Phase 0 graphics backend currently supports Windows only")
endif()

configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/engine/include/easy3d/version.hpp.in"
    "${CMAKE_CURRENT_BINARY_DIR}/generated/easy3d/version.hpp"
    @ONLY
)

# GLM 1.0.1. Easy3D owns its public math types; GLM remains private.
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

# tinyobjloader v2.0.0rc13. OBJ parsing stays private behind Easy3D assets.
set(TINYOBJLOADER_BUILD_TEST_LOADER OFF CACHE BOOL "" FORCE)
FetchContent_Declare(
    tinyobjloader
    GIT_REPOSITORY https://github.com/tinyobjloader/tinyobjloader.git
    GIT_TAG 2945a967c5303b2c8c14174117c45f3302591150
    GIT_SHALLOW FALSE
)
FetchContent_MakeAvailable(tinyobjloader)

set(easy3d_core_sources
    engine/src/assets/image.cpp
    engine/src/assets/model.cpp
    engine/src/core/engine.cpp
    engine/src/input/input.cpp
    engine/src/math/math.cpp
    engine/src/renderer/camera.cpp
    engine/src/renderer/mesh.cpp
    engine/src/scene/scene.cpp
)

if(EASY3D_ENABLE_GRAPHICS)
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
    set(BGFX_BUILD_TOOLS ${EASY3D_REGENERATE_SHADERS} CACHE BOOL "" FORCE)
    set(BGFX_BUILD_TOOLS_BIN2C OFF CACHE BOOL "" FORCE)
    set(BGFX_BUILD_TOOLS_SHADER ${EASY3D_REGENERATE_SHADERS} CACHE BOOL "" FORCE)
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
    list(APPEND easy3d_core_sources
        engine/src/platform/window_win32.cpp
        engine/src/renderer/bgfx_renderer.cpp
    )

    set(EASY3D_SHADER_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/engine/src/renderer/shaders")
    if(EASY3D_REGENERATE_SHADERS)
        FetchContent_GetProperties(bgfx SOURCE_DIR EASY3D_BGFX_SOURCE_DIR)
        set(BGFX_SHADER_INCLUDE_PATH "${EASY3D_BGFX_SOURCE_DIR}/src")
        set(EASY3D_SHADER_INCLUDE_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated/shaders/dxbc")
        bgfx_compile_shaders(
            TYPE VERTEX
            SHADERS
                "${EASY3D_SHADER_SOURCE_DIR}/vs_solid_color.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/vs_solid_color_instanced.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/vs_textured.sc"
                "${EASY3D_SHADER_SOURCE_DIR}/vs_textured_instanced.sc"
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
        )
    endif()
else()
    list(APPEND easy3d_core_sources engine/src/platform/window_stub.cpp)
endif()

add_library(easy3d_core STATIC ${easy3d_core_sources})
add_library(Easy3D::core ALIAS easy3d_core)
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
)
target_link_libraries(easy3d_core PRIVATE glm::glm tinyobjloader)

if(MSVC)
    target_compile_options(easy3d_core PRIVATE /W4 /permissive- /EHsc /Zc:__cplusplus)
else()
    target_compile_options(easy3d_core PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
endif()

if(EASY3D_ENABLE_GRAPHICS)
    target_compile_definitions(easy3d_core PRIVATE EASY3D_HAS_GRAPHICS=1)
    target_include_directories(easy3d_core PRIVATE
        "${EASY3D_SHADER_INCLUDE_DIR}"
    )
    target_link_libraries(easy3d_core PRIVATE SDL3::SDL3-static bgfx bimg bimg_decode)
endif()

if(EASY3D_BUILD_PYTHON)
    find_package(pybind11 CONFIG REQUIRED)
    pybind11_add_module(_easy3d MODULE bindings/module.cpp)
    target_compile_features(_easy3d PRIVATE cxx_std_20)
    target_link_libraries(_easy3d PRIVATE Easy3D::core)
    if(MSVC)
        target_compile_options(_easy3d PRIVATE /W4 /permissive- /EHsc /Zc:__cplusplus)
    else()
        target_compile_options(_easy3d PRIVATE -Wall -Wextra -Wpedantic)
    endif()
    if(MINGW)
        # Keep diagnostic MinGW builds self-contained. The supported release
        # toolchain remains MSVC, whose runtime handling is different.
        target_link_options(_easy3d PRIVATE -static-libgcc -static-libstdc++)
        target_link_libraries(_easy3d PRIVATE "-Wl,-Bstatic" winpthread "-Wl,-Bdynamic")
        get_filename_component(EASY3D_MINGW_BIN_DIR "${CMAKE_CXX_COMPILER}" DIRECTORY)
        set(EASY3D_MINGW_WINPTHREAD_DLL
            "${EASY3D_MINGW_BIN_DIR}/libwinpthread-1.dll")
        if(EXISTS "${EASY3D_MINGW_WINPTHREAD_DLL}")
            install(FILES "${EASY3D_MINGW_WINPTHREAD_DLL}" DESTINATION easy3d)
        endif()
    endif()
    install(TARGETS _easy3d
        LIBRARY DESTINATION easy3d
        RUNTIME DESTINATION easy3d
    )
endif()

if(BUILD_TESTING)
    add_executable(easy3d_core_tests tests/cpp/test_core.cpp)
    target_compile_features(easy3d_core_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_core_tests PRIVATE Easy3D::core)
    add_test(NAME easy3d.core COMMAND easy3d_core_tests)

    add_executable(easy3d_scene_tests tests/cpp/test_scene.cpp)
    target_compile_features(easy3d_scene_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_scene_tests PRIVATE Easy3D::core)
    add_test(NAME easy3d.scene COMMAND easy3d_scene_tests)

    add_executable(easy3d_math_transform_tests tests/cpp/test_math_transform.cpp)
    target_compile_features(easy3d_math_transform_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_math_transform_tests PRIVATE Easy3D::core)
    add_test(NAME easy3d.math_transform COMMAND easy3d_math_transform_tests)

    add_executable(easy3d_mesh_tests tests/cpp/test_mesh.cpp)
    target_compile_features(easy3d_mesh_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_mesh_tests PRIVATE Easy3D::core)
    add_test(NAME easy3d.mesh COMMAND easy3d_mesh_tests)

    add_executable(easy3d_camera_tests tests/cpp/test_camera.cpp)
    target_compile_features(easy3d_camera_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_camera_tests PRIVATE Easy3D::core)
    add_test(NAME easy3d.camera COMMAND easy3d_camera_tests)

    add_executable(easy3d_model_tests tests/cpp/test_model.cpp)
    target_compile_features(easy3d_model_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_model_tests PRIVATE Easy3D::core)
    add_test(NAME easy3d.model COMMAND easy3d_model_tests)

    add_executable(easy3d_render_component_tests tests/cpp/test_render_components.cpp)
    target_compile_features(easy3d_render_component_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_render_component_tests PRIVATE Easy3D::core)
    add_test(NAME easy3d.render_components COMMAND easy3d_render_component_tests)

    add_executable(easy3d_lighting_debug_tests tests/cpp/test_lighting_debug.cpp)
    target_compile_features(easy3d_lighting_debug_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_lighting_debug_tests PRIVATE Easy3D::core)
    add_test(NAME easy3d.lighting_debug COMMAND easy3d_lighting_debug_tests)

    add_executable(easy3d_frustum_tests tests/cpp/test_frustum.cpp)
    target_compile_features(easy3d_frustum_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_frustum_tests PRIVATE Easy3D::core)
    add_test(NAME easy3d.frustum COMMAND easy3d_frustum_tests)

    add_executable(easy3d_input_tests tests/cpp/test_input.cpp)
    target_compile_features(easy3d_input_tests PRIVATE cxx_std_20)
    target_link_libraries(easy3d_input_tests PRIVATE Easy3D::core)
    add_test(NAME easy3d.input COMMAND easy3d_input_tests)

    if(EASY3D_ENABLE_GRAPHICS)
        add_executable(easy3d_texture_tests tests/cpp/test_texture.cpp)
        target_compile_features(easy3d_texture_tests PRIVATE cxx_std_20)
        target_link_libraries(easy3d_texture_tests PRIVATE Easy3D::core)
        add_test(NAME easy3d.texture COMMAND easy3d_texture_tests)
    endif()
endif()

if(EASY3D_BUILD_BENCHMARKS)
    add_executable(easy3d_core_benchmark tests/cpp/benchmark_core.cpp)
    target_compile_features(easy3d_core_benchmark PRIVATE cxx_std_20)
    target_link_libraries(easy3d_core_benchmark PRIVATE Easy3D::core)
endif()

if(EASY3D_ENABLE_GRAPHICS)
    # Visible/manual diagnostic only: never registered with CTest.
    add_executable(easy3d_window_lifecycle tests/cpp/window_lifecycle.cpp)
    target_compile_features(easy3d_window_lifecycle PRIVATE cxx_std_20)
    target_link_libraries(easy3d_window_lifecycle PRIVATE Easy3D::core)

    add_executable(easy3d_geometry_lifecycle tests/cpp/geometry_lifecycle.cpp)
    target_compile_features(easy3d_geometry_lifecycle PRIVATE cxx_std_20)
    target_link_libraries(easy3d_geometry_lifecycle PRIVATE Easy3D::core)
endif()

