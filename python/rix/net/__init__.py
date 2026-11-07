"""Optional RIX multiplayer transport, sessions, replication, and discovery."""

from .._rix import NetworkError
from .discovery import (
    DEFAULT_DISCOVERY_PORT,
    DiscoveredServer,
    DiscoveryStats,
    LanDiscoveryAnnouncer,
    LanDiscoveryBrowser,
)
from .match import (
    ClientMatchState,
    MatchPhase,
    MatchStateFields,
    ServerMatchState,
    register_match_state,
)
from .messages import Message, MessageSchema, decode_message, encode_message
from .prediction import (
    CharacterCorrection,
    CharacterInputCommand,
    CorrectionStats,
    PredictedCharacterController,
    PredictionRole,
    ReconciliationResult,
    RemoteInterpolationStats,
    RemoteTransformInterpolator,
)
from .replication import (
    ClientReplication,
    DeltaBaselineStats,
    NetworkObjectId,
    NetworkTransform,
    NetworkValueType,
    NetworkVar,
    NetworkVarSpec,
    PrefabId,
    PrefabRegistration,
    PrefabRegistry,
    ReplicatedObject,
    RpcArgumentSpec,
    RpcDirection,
    RpcSpec,
    RpcStats,
    ServerReplication,
    SpatialInterest,
    TransformFlushStats,
    TransformReplicationStats,
    TransformSnapshot,
)
from .session import Player, SERVER, Session, SessionRole
from .signaling import (
    RoomEndpoint,
    SignalingClient,
    SignalingEvent,
    SignalingEventType,
    SignalingServer,
    generate_room_code,
    normalize_room_code,
)
from .transport import (
    ADVERSE_NETWORK_CONDITION,
    LAN_NETWORK_CONDITION,
    REGIONAL_NETWORK_CONDITION,
    REPRESENTATIVE_NETWORK_CONDITIONS,
    BackendImpairment,
    Client,
    ClientMetrics,
    ClientState,
    ConnectionId,
    Delivery,
    DisconnectCode,
    EventType,
    ListenEvent,
    ListenRole,
    ListenServer,
    NetworkBackendInfo,
    NetworkCondition,
    NetworkEvent,
    NetworkStats,
    NetworkTransport,
    SendStatus,
    Server,
    ServerState,
    SimulatedEndpoint,
    SimulatedLink,
    backend_info,
    backend_smoke_test,
    impair_backend,
)

__all__ = [name for name in globals() if not name.startswith("_")]
