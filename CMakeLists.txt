cmake_minimum_required(VERSION 3.26)

project(Easy3D VERSION 0.1.0 LANGUAGES CXX)

include(CTest)
include(FetchContent)

option(EASY3D_ENABLE_GRAPHICS "Build the SDL3/bgfx Windows window backend" ${WIN32})
option(EASY3D_BUILD_PYTHON "Build the Python extension" ON)
option(EASY3D_BUILD_BENCHMARKS "Build the tiny native benchmark harness" ON)

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

set(easy3d_core_sources
    engine/src/core/engine.cpp
    engine/src/math/math.cpp
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
    set(BGFX_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
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
    list(APPEND easy3d_core_sources engine/src/platform/window_win32.cpp)
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
target_link_libraries(easy3d_core PRIVATE glm::glm)

if(MSVC)
    target_compile_options(easy3d_core PRIVATE /W4 /permissive- /EHsc /Zc:__cplusplus)
else()
    target_compile_options(easy3d_core PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
endif()

if(EASY3D_ENABLE_GRAPHICS)
    target_compile_definitions(easy3d_core PRIVATE EASY3D_HAS_GRAPHICS=1)
    target_link_libraries(easy3d_core PRIVATE SDL3::SDL3-static bgfx)
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
endif()

