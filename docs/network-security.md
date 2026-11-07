# Network security and trust boundaries

RIX networking assumes an untrusted network and a server-authoritative game.
GameNetworkingSockets supplies its supported authenticated/encrypted transport
behavior; application messages and replicated state still require explicit
validation and authority rules.

## Safe application messages

- `Session` frames are bounded UTF-8 JSON with explicit bytes tagging.
- Pickle, class loading, code evaluation, and arbitrary object graphs are not
  supported.
- Non-finite numbers, control characters where prohibited, non-string mapping
  keys, excessive nesting/container counts, malformed UTF-8/JSON, and frames
  above the negotiated limit are rejected.
- `register_message()` declares exact required field types and whether extra
  fields are allowed. A malformed or schema-invalid peer is disconnected and
  the polling call raises `NetworkError`.
- Protocol version, schema version, and maximum message size are negotiated
  during a bounded handshake before application traffic is accepted.

## Replication and RPC authority

- Prefab IDs, variable IDs/types/sizes, transform support, and RPC IDs are
  registered locally before the registry freezes.
- Remote input never supplies a Python import path or method name.
- Client `NetworkVar` mirrors are read-only. The authority owns object IDs,
  spawn/despawn, values, transforms, health, scores, and final physics state.
- RPC schemas fix direction, typed bounded arguments, delivery mode, rate
  limit, and optional ownership requirement. Sequence checks reject replayed or
  stale calls before invoking a handler.
- Disconnect cleanup removes ownership and can despawn objects according to
  the explicit server policy.
- Character prediction sends inputs, not trusted final positions. The server
  motor produces corrections and clients replay only bounded unacknowledged
  input.

## Resource bounds

Server/client constructors bound message size, event queue capacity,
connections, handshake time, peer idle time, and polling counts. Replication
bounds object count, transform history, payloads, snapshot baselines, spatial
interest, and optional per-client byte budgets. Send calls report backpressure
instead of silently claiming delivery.

Applications must still validate game-specific requests. A reliable packet
does not prove that a purchase, hit, inventory change, score, or interaction is
legal. Put those decisions in server-side handlers and reject requests that do
not satisfy range, cooldown, ownership, phase, or other game rules.

Session startup is transactional. If an application lifecycle callback raises
while `Session.host()` is publishing its initial local-player connection, RIX
stops the native listener, clears identities, restores the closed role, and
re-raises the callback error. The same Session and port can then be reused.

## Deliberate non-claims

Direct IP does not solve NAT traversal. LAN discovery is an untrusted hint, not
authentication. The optional `SignalingServer` is a connection-owned,
self-hosted endpoint directory; it is deliberately not an authenticated hosted
service or packet relay. A room result does not make the advertised endpoint
reachable. Do not expose the reference directory or a game server to the public
internet without application-specific authentication, abuse controls, logging,
deployment hardening, and operational monitoring. RIX also makes no generic
deterministic Python/Jolt rollback claim.
