from collections.abc import Callable
from typing import Final

class EngineError(RuntimeError): ...
class AssetError(EngineError): ...
class MissingAssetError(AssetError): ...
class InvalidEntityError(ReferenceError): ...
class PhysicsError(EngineError): ...
class NetworkError(EngineError): ...

class _TextureColorSpace:
    LINEAR: Final[_TextureColorSpace]
    SRGB: Final[_TextureColorSpace]
    __members__: Final[dict[str, _TextureColorSpace]]
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> int: ...
    def __int__(self) -> int: ...
    def __index__(self) -> int: ...

def _load_image_info(
    path: str, color_space: _TextureColorSpace
) -> tuple[str, int, int, int, bool]: ...

class _TextureCache:
    def __init__(self) -> None: ...
    def load(
        self, path: str, color_space: _TextureColorSpace, hot_reload: bool = True
    ) -> tuple[str, int, int, int, bool]: ...
    def poll_changes(self, interval_ms: int = 0) -> int: ...
    def clear(self) -> None: ...
    @property
    def size(self) -> int: ...

class _DynamicImage:
    def __init__(
        self, width: int, height: int, rgba8: bytes, srgb: bool = True
    ) -> None: ...
    def update(self, width: int, height: int, rgba8: bytes) -> None: ...
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def revision(self) -> int: ...
    def _rgba8(self) -> bytes: ...

_NativeModelInfo = tuple[
    str,
    int,
    list[tuple[str, int, int, int, int]],
    list[
        tuple[
            str,
            tuple[float, float, float, float],
            str | None,
            float,
            float,
            float,
            str | None,
            str | None,
            str | None,
            str | None,
            str | None,
            float,
            bool,
            bool,
        ]
    ],
    list[str],
]

def _load_obj_info(path: str) -> _NativeModelInfo: ...
_NativeSkeletonInfo = tuple[
    str,
    list[
        tuple[
            str,
            int,
            tuple[float, float, float],
            tuple[float, float, float, float],
            tuple[float, float, float],
            tuple[float, ...],
        ]
    ],
]
_NativeAnimationChannel = tuple[
    int,
    str,
    str,
    list[float],
    list[tuple[float, float, float, float]],
]
_NativeAnimationInfo = tuple[str, float, list[_NativeAnimationChannel]]
def _load_gltf_info(
    path: str,
) -> tuple[_NativeModelInfo, _NativeSkeletonInfo | None, list[_NativeAnimationInfo]]: ...

class _ModelCache:
    def __init__(self) -> None: ...
    def load(self, path: str) -> _NativeModelInfo: ...
    def clear(self) -> None: ...
    @property
    def size(self) -> int: ...

def engine_version() -> str: ...
def native_add(a: int, b: int) -> int: ...
def _raise_engine_error(message: str) -> None: ...
def _quat_from_euler(x: float, y: float, z: float) -> tuple[float, float, float, float]: ...
def _quat_to_euler(
    w: float, x: float, y: float, z: float
) -> tuple[float, float, float]: ...

class _NativeInput:
    def _begin_frame(self) -> None: ...
    def _end_frame(self) -> None: ...
    def _set_control(self, control: str, value: float) -> None: ...
    def _add_pointer_motion(
        self, x: float, y: float, delta_x: float, delta_y: float
    ) -> None: ...
    def _add_wheel(self, x: float, y: float) -> None: ...
    def _set_focused(self, focused: bool) -> None: ...
    def _set_pointer_lock_active(self, active: bool) -> None: ...
    def _set_gamepad_connected(self, connected: bool, name: str = "") -> None: ...
    def bind_action(
        self,
        action: str,
        bindings: list[tuple[str, float, float]],
        replace: bool = True,
    ) -> None: ...
    def unbind_action(self, action: str) -> None: ...
    def clear_actions(self) -> None: ...
    def action_state(self, action: str) -> tuple[float, bool, bool, bool]: ...
    def action_bindings(self, action: str) -> list[tuple[str, float, float]]: ...
    def control_value(self, control: str) -> float: ...
    def control_state(self, control: str) -> tuple[float, bool, bool, bool]: ...
    @property
    def pointer_state(self) -> tuple[float, float, float, float, float, float]: ...
    @property
    def focused(self) -> bool: ...
    @property
    def pointer_lock_requested(self) -> bool: ...
    @pointer_lock_requested.setter
    def pointer_lock_requested(self, value: bool) -> None: ...
    @property
    def pointer_lock_active(self) -> bool: ...
    @property
    def gamepad_connected(self) -> bool: ...
    @property
    def gamepad_name(self) -> str: ...
    @property
    def action_count(self) -> int: ...

class Engine:
    def __init__(
        self,
        title: str = "RIX",
        width: int = 1280,
        height: int = 720,
        vsync: bool = True,
        fps_limit: float = 0.0,
        graphics_preset: str = "medium",
    ) -> None: ...
    def run(self, frame_callback: Callable[[float], None] | None = None) -> None: ...
    def tick(
        self,
        frame_callback: Callable[[float], None] | None = None,
        fps_limit: float = -1.0,
    ) -> float: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...
    def begin_external_window(
        self, native_window: int, width: int, height: int
    ) -> None: ...
    def resize_external_window(self, width: int, height: int) -> None: ...
    def render_external_window(self) -> None: ...
    def render_external_offscreen(self) -> None: ...
    def readback_external_window_rgba8(self) -> bytes: ...
    def render_external_viewport_rgba8(
        self,
        px: float,
        py: float,
        pz: float,
        qw: float,
        qx: float,
        qy: float,
        qz: float,
        vertical_fov_degrees: float,
        near_plane: float,
        far_plane: float,
        orthographic: bool,
        orthographic_height: float,
        width: int,
        height: int,
    ) -> bytes: ...
    def request_external_viewport_rgba8(
        self,
        px: float,
        py: float,
        pz: float,
        qw: float,
        qx: float,
        qy: float,
        qz: float,
        vertical_fov_degrees: float,
        near_plane: float,
        far_plane: float,
        orthographic: bool,
        orthographic_height: float,
        width: int,
        height: int,
    ) -> int: ...
    def poll_external_viewport_rgba8(self, request_id: int) -> bytes | None: ...
    def wait_external_viewport_rgba8(self, request_id: int) -> bytes: ...
    def cancel_external_viewport_rgba8(self, request_id: int) -> None: ...
    def end_external_window(self) -> None: ...
    def set_scene(self, scene: _NativeScene | None = None) -> None: ...
    def audio_create_pcm16_sound(
        self, data: bytes, channels: int, sample_rate: int
    ) -> int: ...
    def audio_play(
        self,
        sound: int,
        volume: float = 1.0,
        loop: bool = False,
        spatial: bool = False,
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
        minimum_distance: float = 1.0,
        maximum_distance: float = 50.0,
    ) -> int: ...
    def audio_stop(self, voice: int) -> None: ...
    def audio_set_volume(self, voice: int, volume: float) -> None: ...
    def audio_set_position(
        self, voice: int, position: tuple[float, float, float]
    ) -> None: ...
    def audio_voice_playing(self, voice: int) -> bool: ...
    @property
    def is_running(self) -> bool: ...
    @property
    def frame_count(self) -> int: ...
    @property
    def last_frame_seconds(self) -> float: ...
    @property
    def viewport_size(self) -> tuple[int, int]: ...
    @property
    def graphics_preset(self) -> str: ...
    @property
    def renderer_stats(
        self,
    ) -> tuple[
        int,
        int,
        int,
        int,
        int,
        int,
        bool,
        bool,
        bool,
        bool,
        int,
        float,
        float,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
    ]: ...
    @property
    def input(self) -> _NativeInput: ...
    @property
    def audio_backend_active(self) -> bool: ...
    @property
    def audio_sound_count(self) -> int: ...
    @property
    def audio_active_voice_count(self) -> int: ...

class EntityHandle:
    @property
    def world_id(self) -> int: ...
    @property
    def index(self) -> int: ...
    @property
    def generation(self) -> int: ...
    @property
    def id(self) -> int: ...
    @property
    def valid(self) -> bool: ...

class _NativeScene:
    def __init__(self, name: str = "Scene") -> None: ...
    @property
    def name(self) -> str: ...
    @name.setter
    def name(self, value: str) -> None: ...
    @property
    def active(self) -> bool: ...
    @active.setter
    def active(self, value: bool) -> None: ...
    @property
    def world_id(self) -> int: ...
    @property
    def entity_count(self) -> int: ...
    def create_entity(self, name: str = "Entity") -> EntityHandle: ...
    def destroy_entity(self, handle: EntityHandle) -> None: ...
    def clear(self) -> None: ...
    def is_alive(self, handle: EntityHandle) -> bool: ...
    def entity_handles(self) -> list[EntityHandle]: ...
    def entity_name(self, handle: EntityHandle) -> str: ...
    def set_entity_name(self, handle: EntityHandle, name: str) -> None: ...
    def entity_enabled(self, handle: EntityHandle) -> bool: ...
    def set_entity_enabled(self, handle: EntityHandle, enabled: bool) -> None: ...
    def entity_visible(self, handle: EntityHandle) -> bool: ...
    def set_entity_visible(self, handle: EntityHandle, visible: bool) -> None: ...
    def entity_local_position(self, handle: EntityHandle) -> tuple[float, float, float]: ...
    def set_entity_local_position(
        self, handle: EntityHandle, x: float, y: float, z: float
    ) -> None: ...
    def entity_local_rotation(
        self, handle: EntityHandle
    ) -> tuple[float, float, float, float]: ...
    def set_entity_local_rotation(
        self, handle: EntityHandle, w: float, x: float, y: float, z: float
    ) -> None: ...
    def entity_local_scale(self, handle: EntityHandle) -> tuple[float, float, float]: ...
    def set_entity_local_scale(
        self, handle: EntityHandle, x: float, y: float, z: float
    ) -> None: ...
    def entity_world_transform(
        self, handle: EntityHandle
    ) -> tuple[
        tuple[float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float],
    ]: ...
    def entity_parent(self, handle: EntityHandle) -> EntityHandle | None: ...
    def entity_children(self, handle: EntityHandle) -> list[EntityHandle]: ...
    def set_entity_parent(
        self,
        child: EntityHandle,
        parent: EntityHandle | None = None,
        keep_world: bool = False,
    ) -> None: ...
    def entity_velocity(self, handle: EntityHandle) -> tuple[float, float, float]: ...
    def set_entity_velocity(
        self, handle: EntityHandle, velocity: tuple[float, float, float]
    ) -> None: ...
    def entity_acceleration(self, handle: EntityHandle) -> tuple[float, float, float]: ...
    def set_entity_acceleration(
        self, handle: EntityHandle, acceleration: tuple[float, float, float]
    ) -> None: ...
    def entity_angular_velocity(
        self, handle: EntityHandle
    ) -> tuple[float, float, float]: ...
    def set_entity_angular_velocity(
        self, handle: EntityHandle, velocity: tuple[float, float, float]
    ) -> None: ...
    def entity_angular_acceleration(
        self, handle: EntityHandle
    ) -> tuple[float, float, float]: ...
    def set_entity_angular_acceleration(
        self, handle: EntityHandle, acceleration: tuple[float, float, float]
    ) -> None: ...
    def entity_character_yaw_offset(self, handle: EntityHandle) -> float: ...
    def reset_entity_motion(self, handle: EntityHandle) -> None: ...
    def add_primitive_renderer(
        self,
        handle: EntityHandle,
        kind: str,
        color: tuple[float, float, float, float],
        texture: str | None = None,
        pixels_per_unit: float = 16.0,
        texture_filter: str = "nearest",
        texture_mode: str = "auto",
        normal_map: str | None = None,
        roughness_map: str | None = None,
        metallic_map: str | None = None,
        emissive_map: str | None = None,
        ambient_occlusion_map: str | None = None,
        normal_strength: float = 1.0,
        hot_reload: bool = True,
        atlas_dimensions: tuple[float, float, float] = (1.0, 1.0, 1.0),
        cull_mode: str = "back",
    ) -> None: ...
    def add_model_renderer(
        self,
        handle: EntityHandle,
        path: str,
        color: tuple[float, float, float, float],
        cull_mode: str | None = None,
    ) -> None: ...
    def has_render_component(self, handle: EntityHandle) -> bool: ...
    def render_component_info(
        self, handle: EntityHandle
    ) -> tuple[
        str,
        tuple[float, float, float, float],
        str | None,
        bool,
        float,
        float,
        float,
        bool,
        bool,
        float,
        str,
        str,
        float,
        bool,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        tuple[float, float, float],
        str,
    ]: ...
    def set_render_color(
        self, handle: EntityHandle, color: tuple[float, float, float, float]
    ) -> None: ...
    def set_render_lit(self, handle: EntityHandle, lit: bool) -> None: ...
    def set_render_cull_mode(self, handle: EntityHandle, cull_mode: str) -> None: ...
    def set_render_surface(
        self,
        handle: EntityHandle,
        metallic: float,
        roughness: float,
        emission: float,
        casts_shadows: bool,
        receives_shadows: bool,
    ) -> None: ...
    def set_render_texture(
        self,
        handle: EntityHandle,
        texture: str | None,
        pixels_per_unit: float,
        texture_filter: str,
        texture_mode: str,
        normal_map: str | None = None,
        roughness_map: str | None = None,
        metallic_map: str | None = None,
        emissive_map: str | None = None,
        ambient_occlusion_map: str | None = None,
        normal_strength: float = 1.0,
        hot_reload: bool = True,
        atlas_dimensions: tuple[float, float, float] = (1.0, 1.0, 1.0),
    ) -> None: ...
    def set_render_image(
        self,
        handle: EntityHandle,
        texture: _DynamicImage,
        pixels_per_unit: float,
        texture_filter: str,
        texture_mode: str,
        atlas_dimensions: tuple[float, float, float] = (1.0, 1.0, 1.0),
    ) -> None: ...
    def remove_render_component(self, handle: EntityHandle) -> None: ...
    def add_light_component(
        self,
        handle: EntityHandle,
        kind: str,
        color: tuple[float, float, float, float],
        intensity: float,
        range: float = 10.0,
        inner_angle: float = 30.0,
        outer_angle: float = 45.0,
        casts_shadows: bool = False,
        shadow_resolution: int = 0,
        shadow_bias: float = 0.002,
    ) -> None: ...
    def has_light_component(self, handle: EntityHandle) -> bool: ...
    def light_component_info(
        self, handle: EntityHandle
    ) -> tuple[
        str,
        tuple[float, float, float, float],
        float,
        float,
        float,
        float,
        bool,
        int,
        float,
    ]: ...
    def set_light_color(
        self, handle: EntityHandle, color: tuple[float, float, float, float]
    ) -> None: ...
    def set_light_intensity(self, handle: EntityHandle, intensity: float) -> None: ...
    def set_light_properties(
        self,
        handle: EntityHandle,
        range: float,
        inner_angle: float,
        outer_angle: float,
        casts_shadows: bool,
        shadow_resolution: int,
        shadow_bias: float,
    ) -> None: ...
    def remove_light_component(self, handle: EntityHandle) -> None: ...
    def add_collider_component(
        self,
        handle: EntityHandle,
        shape: str,
        half_extents: tuple[float, float, float],
        radius: float,
        trigger: bool,
        layer: str,
        friction: float,
        restitution: float,
    ) -> None: ...
    def has_collider_component(self, handle: EntityHandle) -> bool: ...
    def collider_component_info(
        self, handle: EntityHandle
    ) -> tuple[str, tuple[float, float, float], float, bool, str, float, float]: ...
    def remove_collider_component(self, handle: EntityHandle) -> None: ...
    def add_rigid_body_component(
        self,
        handle: EntityHandle,
        type: str,
        mass: float,
        use_gravity: bool,
    ) -> None: ...
    def has_rigid_body_component(self, handle: EntityHandle) -> bool: ...
    def rigid_body_component_info(
        self, handle: EntityHandle
    ) -> tuple[str, float, bool]: ...
    def remove_rigid_body_component(self, handle: EntityHandle) -> None: ...
    def rigid_body_linear_velocity(
        self, handle: EntityHandle
    ) -> tuple[float, float, float]: ...
    def set_rigid_body_linear_velocity(
        self, handle: EntityHandle, velocity: tuple[float, float, float]
    ) -> None: ...
    def rigid_body_angular_velocity(
        self, handle: EntityHandle
    ) -> tuple[float, float, float]: ...
    def set_rigid_body_angular_velocity(
        self, handle: EntityHandle, velocity: tuple[float, float, float]
    ) -> None: ...
    def add_rigid_body_force(
        self, handle: EntityHandle, force: tuple[float, float, float]
    ) -> None: ...
    def add_rigid_body_impulse(
        self, handle: EntityHandle, impulse: tuple[float, float, float]
    ) -> None: ...
    def teleport_rigid_body(
        self,
        handle: EntityHandle,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float, float],
    ) -> None: ...
    def add_character_controller_component(
        self,
        handle: EntityHandle,
        mode: str,
        radius: float,
        height: float,
        speed: float,
        acceleration: float,
        air_acceleration: float,
        ground_friction: float,
        stop_speed: float,
        air_speed_cap: float,
        horizontal_speed_limit: float,
        jump_speed: float,
        max_slope_degrees: float,
        step_height: float,
        sprint_multiplier: float,
        crouch_height: float,
        crouch_speed_multiplier: float,
    ) -> None: ...
    def has_character_controller_component(self, handle: EntityHandle) -> bool: ...
    def character_controller_component_info(
        self, handle: EntityHandle
    ) -> tuple[
        str,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
    ]: ...
    def remove_character_controller_component(self, handle: EntityHandle) -> None: ...
    def set_character_input(
        self,
        handle: EntityHandle,
        movement: tuple[float, float, float],
        heading_degrees: float,
        jump: bool = False,
        sprint: bool = False,
        crouch: bool = False,
    ) -> None: ...
    def set_character_sequenced_input(
        self,
        handle: EntityHandle,
        sequence: int,
        movement: tuple[float, float, float],
        heading_degrees: float,
        jump: bool = False,
        sprint: bool = False,
        crouch: bool = False,
    ) -> None: ...
    def character_input_sequence(self, handle: EntityHandle) -> int: ...
    def character_state(
        self, handle: EntityHandle
    ) -> tuple[
        tuple[float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
        bool,
        bool,
        bool,
    ]: ...
    def set_character_linear_velocity(
        self, handle: EntityHandle, velocity: tuple[float, float, float]
    ) -> None: ...
    def correct_character(
        self,
        handle: EntityHandle,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float, float],
        linear_velocity: tuple[float, float, float],
    ) -> None: ...
    def replay_character_input(
        self,
        handle: EntityHandle,
        movement: tuple[float, float, float],
        heading_degrees: float,
        jump: bool,
        sprint: bool,
        crouch: bool,
        delta_seconds: float,
    ) -> None: ...
    def teleport_character(
        self,
        handle: EntityHandle,
        position: tuple[float, float, float],
        heading_degrees: float = 0,
    ) -> None: ...
    def add_fixed_constraint(
        self, first: EntityHandle, second: EntityHandle
    ) -> object: ...
    def add_distance_constraint(
        self,
        first: EntityHandle,
        second: EntityHandle,
        first_anchor: tuple[float, float, float],
        second_anchor: tuple[float, float, float],
        minimum_distance: float = -1,
        maximum_distance: float = -1,
    ) -> object: ...
    def remove_constraint(self, handle: object) -> None: ...
    def has_constraint(self, handle: object) -> bool: ...
    def physics_raycast_all(
        self,
        origin: tuple[float, float, float],
        direction: tuple[float, float, float],
        max_distance: float,
        layer_mask: int = 15,
        include_triggers: bool = True,
        excluded: EntityHandle | None = None,
    ) -> list[
        tuple[
            EntityHandle,
            tuple[float, float, float],
            tuple[float, float, float],
            float,
            float,
        ]
    ]: ...
    def physics_overlap_sphere(
        self,
        center: tuple[float, float, float],
        radius: float,
        layer_mask: int = 15,
        include_triggers: bool = True,
        excluded: EntityHandle | None = None,
    ) -> list[
        tuple[
            EntityHandle,
            tuple[float, float, float],
            tuple[float, float, float],
            float,
            float,
        ]
    ]: ...
    def physics_overlap_box(
        self,
        center: tuple[float, float, float],
        half_extents: tuple[float, float, float],
        rotation: tuple[float, float, float, float],
        layer_mask: int = 15,
        include_triggers: bool = True,
        excluded: EntityHandle | None = None,
    ) -> list[
        tuple[
            EntityHandle,
            tuple[float, float, float],
            tuple[float, float, float],
            float,
            float,
        ]
    ]: ...
    def physics_sphere_cast_all(
        self,
        origin: tuple[float, float, float],
        radius: float,
        direction: tuple[float, float, float],
        max_distance: float,
        layer_mask: int = 15,
        include_triggers: bool = True,
        excluded: EntityHandle | None = None,
    ) -> list[
        tuple[
            EntityHandle,
            tuple[float, float, float],
            tuple[float, float, float],
            float,
            float,
        ]
    ]: ...
    def physics_capsule_cast_all(
        self,
        origin: tuple[float, float, float],
        radius: float,
        height: float,
        rotation: tuple[float, float, float, float],
        direction: tuple[float, float, float],
        max_distance: float,
        layer_mask: int = 15,
        include_triggers: bool = True,
        excluded: EntityHandle | None = None,
    ) -> list[
        tuple[
            EntityHandle,
            tuple[float, float, float],
            tuple[float, float, float],
            float,
            float,
        ]
    ]: ...
    def drain_physics_events(
        self,
    ) -> list[
        tuple[
            str,
            bool,
            EntityHandle,
            EntityHandle,
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ]: ...
    def skybox_info(self) -> tuple[
        str,
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        float,
        float,
        str | list[str] | None,
    ] | None: ...
    def set_procedural_skybox(
        self,
        top: tuple[float, float, float, float],
        horizon: tuple[float, float, float, float],
        bottom: tuple[float, float, float, float],
        brightness: float,
        rotation: float,
    ) -> None: ...
    def set_panorama_skybox(
        self, path: str, brightness: float = 1.0, rotation: float = 0.0
    ) -> None: ...
    def set_cubemap_skybox(
        self,
        paths: tuple[str, str, str, str, str, str],
        brightness: float = 1.0,
        rotation: float = 0.0,
    ) -> None: ...
    def clear_skybox(self) -> None: ...
    def camera_info(
        self,
    ) -> tuple[
        tuple[float, float, float],
        tuple[float, float, float, float],
        float,
        float,
        float,
        str,
        float,
    ]: ...
    def set_camera(
        self,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float, float],
        vertical_fov_degrees: float,
        near_plane: float,
        far_plane: float,
        projection: str,
        orthographic_height: float,
    ) -> None: ...
    def add_debug_line(
        self,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        color: tuple[float, float, float, float],
        depth_test: bool = True,
    ) -> None: ...
    def clear_debug_lines(self) -> None: ...
    def add_ui_element(
        self,
        kind: str,
        anchor: str,
        position: tuple[float, float],
        size: tuple[float, float],
        color: tuple[float, float, float, float],
        text: str = "",
        text_color: tuple[float, float, float, float] = (1, 1, 1, 1),
        font_size: float = 24,
        z_index: int = 0,
        visible: bool = True,
        enabled: bool = True,
        texture: str | None = None,
    ) -> int: ...
    def ui_element_info(
        self, id: int
    ) -> tuple[
        str,
        str,
        tuple[float, float],
        tuple[float, float],
        tuple[float, float, float, float],
        str,
        tuple[float, float, float, float],
        float,
        int,
        bool,
        bool,
        str | None,
    ]: ...
    def update_ui_element(
        self,
        id: int,
        anchor: str,
        position: tuple[float, float],
        size: tuple[float, float],
        color: tuple[float, float, float, float],
        text: str,
        text_color: tuple[float, float, float, float],
        font_size: float,
        z_index: int,
        visible: bool,
        enabled: bool,
    ) -> None: ...
    def set_ui_image(self, id: int, texture: _DynamicImage) -> None: ...
    def remove_ui_element(self, id: int) -> None: ...
    def clear_ui(self) -> None: ...
    @property
    def ui_element_count(self) -> int: ...
    def physics_gravity(self) -> tuple[float, float, float]: ...
    def set_physics_gravity(self, gravity: tuple[float, float, float]) -> None: ...
    def step_physics(self, delta_seconds: float) -> None: ...
    @property
    def physics_step_count(self) -> int: ...
    @property
    def debug_line_count(self) -> int: ...

