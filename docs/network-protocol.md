# Easy3D network protocol status

This document distinguishes the implemented transport boundary from future
wire-protocol work. It does not specify functionality that has not shipped.

## Implemented in Phase 3.1

- `easy3d::NetworkTransport` defines send, disconnect, poll and statistics at
  the native data-plane boundary.
- `ConnectionId` is an opaque nonzero 64-bit identity local to one transport
  process. It is not an entity ID, network-object ID, account or authentication
  identity.
- A message carries bounded bytes plus reliable/unreliable delivery intent.
  Sends explicitly report queued, invalid connection, oversize payload or full
  queue.
- Connected, disconnected and message events are copied into a bounded FIFO.
  Queue exhaustion is counted and raised as `NetworkError`; it is never an
  unbounded allocation or silent success.
- `easy3d.network.SimulatedLink` supplies two manually advanced endpoints with
  seeded latency, jitter and loss. Equal-delivery-time messages retain sequence
  order and expose immutable event/statistic snapshots.

The native simulator models datagrams below a reliability layer. It preserves
the delivery label for protocol tests but does not retransmit a lost reliable
message.

Phase 5.3 adds validated synthetic profiles. LAN is 5 ms one-way/2 ms
jitter/0% loss; regional is 40/10 ms/1%; adverse is 100/30 ms/5%. Each creates
a seeded `SimulatedLink` for exact traces. `impair_backend(profile)` applies the
same shape to GameNetworkingSockets' process-global fake-send controls for
scoped loopback tests, so real reliable retransmission and ordering remain
active. Scopes cannot overlap and reset on exit. They are test inputs, not
production connection configuration or measured network distributions.

## Implemented in Phase 3.2

- GameNetworkingSockets 1.6.1 is pinned at commit
  `d534c19aa760df3fb75fd20db13ba1932b8a5463` and linked statically behind the
  Easy3D boundary. No third-party networking types enter the public API.
- Protobuf 5.29.3 is built at commit
  `b407e8416e3893036aee5af9a12bd9b6a0e2b2e6`; its `protoc` and static runtime
  come from that same source revision. Both Protobuf and GameNetworkingSockets
  compile as C++17 to keep their `string_view` ABI identical.
- Windows BCrypt supplies the supported platform AES/SHA primitives; the
  upstream bundled Donna implementation supplies Curve25519/Ed25519. No
  OpenSSL binary is redistributed. ICE/WebRTC is disabled for this direct-IP
  foundation.
- A process-global, mutex-protected reference count owns initialization and
  shutdown. Nested owners cannot kill the runtime while another owner remains.
- Native and Python smoke tests create a GameNetworkingSockets socket pair,
  send one reliable bounded payload, poll callbacks, verify exact bytes, and
  release both connections. This proves the actual backend rather than a mock.
- `easy3d.network.backend_info()` exposes immutable build diagnostics and
  `backend_smoke_test()` repeats the loopback check on demand.

## Implemented in Phase 3.3

The internal handshake is a transport-independent state machine. All integer
fields use little-endian byte order. A handshake frame is capped at 512 bytes
and begins with this 12-byte envelope:

| Offset | Size | Field | Required value |
|---:|---:|---|---|
| 0 | 4 | Magic | ASCII `E3DN` |
| 4 | 2 | Wire-format version | `1` |
| 6 | 1 | Message type | `1` hello, `2` accept, `3` confirm, `4` reject |
| 7 | 1 | Reserved flags | `0` |
| 8 | 4 | Payload byte count | Exact remaining frame size, at most 500 |

Hello, accept and confirm carry the same fixed 12-byte peer declaration:

| Offset | Size | Field | Rule |
|---:|---:|---|---|
| 0 | 2 | Application protocol version | Exact match, currently `1` |
| 2 | 4 | Schema version | Exact match, currently `1` |
| 6 | 1 | Role | `1` client or `2` server |
| 7 | 1 | Reserved | `0` |
| 8 | 4 | Maximum application message size | `1..1,048,576` bytes |

The reliable sequence is client hello → server accept → client confirm.
The server accept advertises the smaller of both peer limits; the client cannot
raise that limit and must echo it unchanged in its confirmation. The server
accepts only a client role and the client accepts only a server role. The
client is established after producing its confirmation; the server is
established only after verifying it.

A rejection payload contains a stable 16-bit disconnect code, a 16-bit byte
length and 1–256 bytes of validated UTF-8 text. C0/C1 control characters,
overlong sequences, surrogates and invalid Unicode are rejected so a peer
cannot inject control text into diagnostics. Defined protocol codes are:

- `1000` malformed message
- `1001` protocol version mismatch
- `1002` schema version mismatch
- `1003` role mismatch
- `1004` limit violation
- `1005` unexpected message/state
- `1006` message too large
- `1007` connection/handshake timeout
- `1008` local transport failure
- `1009` authoritative server stopped
- `1010` server connection limit reached

GNS reserves application close reasons below 1000. The adapter therefore uses
private transport sentinel `1011` for a graceful close and maps it back to the
public Easy3D code `1` at both endpoints; `1011` is never emitted as an
application event or protocol rejection.

Parsing checks the outer 512-byte cap and declared length before reading or
copying payload data. Local state-machine misuse raises a C++ logic error;
untrusted peer input becomes a bounded rejection and stable disconnect code.
No Python object serialization is used.

## Implemented in Phase 3.4

`easy3d.network.Client` owns one asynchronous direct-IP GNS connection. It
accepts numeric IPv4 or IPv6 plus a nonzero port; DNS, discovery and room codes
are intentionally separate policies. `connect()` enters `connecting` and
returns. Repeated `poll()` calls run GNS callbacks, consume at most 256 native
messages per call, drive the reliable Phase 3.3 handshake and enforce the
configured monotonic deadline across transport connection and handshake.

Application `connected` is emitted only after the client sends its validated
confirmation. Before that point, unreliable frames or non-handshake bytes are
protocol errors. After establishment, any message larger than the negotiated
limit closes the peer; accepted payloads are copied into the existing bounded
event queue. Reliable/unreliable intent and GNS message sequence are preserved.
Queue overflow is counted, raised once, and leaves the event that fit available
for the next poll.

Clean local close, protocol rejection, deadline expiry, GNS local failure and
remote close all produce one immutable disconnected event. Easy3D codes remain
in the app range above; native GNS/OS codes outside that range are preserved as
integers rather than mislabelled. Local reason text is capped at 120 bytes to
fit the backend diagnostic field and rejects controls. A disconnected client
has no active connection ID but retains its normalized remote address and
counter snapshot for diagnostics.

Metrics include application message/byte/rejection/overflow counters plus GNS
ping, recent incoming/outgoing bytes per second, pending reliable/unreliable
bytes and the negotiated limit. Rates are observations, not bandwidth promises.
Python connect/disconnect callbacks run synchronously while the owning thread
calls `poll()`; no native callback enters Python.

## Implemented in Phase 3.5

`easy3d.network.Server` owns one numeric direct-IP GNS listen socket, one poll
group and a bounded map of native peer records. An incoming transport is not an
application player: it receives an opaque local connection ID and becomes
visible through `connected`/`connections` only after the Phase 3.3 server
handshake validates the client's confirmation. A monotonic per-peer deadline
removes silent pre-handshake sockets. The configured player limit includes
handshaking sockets so incomplete peers cannot bypass the bound.

`poll()` is the sole callback and message pump. It accepts connections, drains
at most 256 messages, advances every handshake, applies each negotiated payload
limit and copies application events into one bounded queue. Reliable and
unreliable sends target established opaque IDs. Stop, application disconnect,
remote close, protocol rejection, timeout, queue overflow and transport failure
clean their peer records without exposing GNS handles. The listener closes
accepted peers before closing the listen socket because GNS documents listener
close as ungraceful for attached connections; this preserves code `1009` for
remote clients.

The Python server uses the existing `SimulationScheduler` at a configured
fixed tick rate. Network callbacks and scene scripts run on the `run`, `step`
or `poll` caller, never from a GNS callback. `stop()` only signals while a run
loop is active and is safe to request from another Python thread. No `Engine`,
SDL window or bgfx renderer is constructed.

Client and server owners separately configure GNS connected-peer liveness with
`peer_timeout` (default 10 seconds). This is distinct from initial connection
and handshake deadlines. Liveness callbacks are still delivered only while the
owner polls, and backend/OS failure codes outside Easy3D's stable application
range remain integers rather than being relabelled.

## Implemented in Phase 3.6

`ListenServer` does not add a wire mode or privileged in-process shortcut. It
starts the Phase 3.5 authority, connects an ordinary Phase 3.4 client to its
numeric loopback address, and completes the same Phase 3.3 handshake before
startup returns. Bytes in either direction pass through GNS and the existing
bounded queues. Additional remote clients use the same authority listener.

Authority and local client events are tagged separately. Their opaque IDs are
local to their respective transports and may coincidentally have the same
64-bit value; no cross-role comparison creates identity or ownership. Only the
authority object owns a `Scene` or advances the scheduler/physics. The client
is pumped after each authoritative tick and cannot cause a second
`fixed_update`, authority callback or physics step. The host receives no
transport-level privilege beyond sharing a machine and loopback path.

## Implemented in Phase 3.7

LAN discovery is a separate opt-in IPv4 UDP query/response protocol, not a GNS
gameplay message. Every datagram is at most 512 bytes and begins with a 12-byte
little-endian envelope: magic `E3DD`, 16-bit wire version `1`, 8-bit type (`1`
query or `2` response), zero 8-bit flags, and an exact 32-bit payload length.
A query payload is one nonzero random 64-bit nonce.

A response repeats the query nonce and carries a nonzero 64-bit server-instance
ID, 16-bit gameplay port, 16-bit application protocol version, 32-bit schema
version, 16-bit UTF-8 name length and exactly that many name bytes. Names are
non-empty, control-free and at most 128 bytes. Integers are range checked and
trailing, truncated, oversized, wrong-version and invalid-UTF-8 datagrams are
dropped. The browser accepts only its current nonce within a finite response
window and only from the configured UDP discovery port.

The announcer replies by unicast to the query's ephemeral source. Work per poll,
repeat responses per source and remembered source state are bounded. Browser
results use a bounded TTL/LRU cache and expose exact protocol/schema
compatibility. Nonces correlate a response with a recent query; they are not an
authentication or anti-spoofing mechanism. Discovery never starts a GNS
connection, and the Phase 3.3 handshake still validates any address the user
later selects.

## Implemented in Phase 3.8

`examples/06_two_process` runs the public `Server` and `Client` in independent
Python processes. The client completes the format-1 handshake, sends one exact
bounded request, validates one exact reply and closes. Server and client
readiness are distinct: a client is ready after sending confirmation, while the
server is ready for application identity only after polling and validating that
confirmation.

Subprocess integration covers clean loopback exchange, a second listener's
same-port bind rejection while the first listener remains usable, abrupt server
termination observed by the client, and abrupt client termination observed by
the server. Abrupt tests do not assert one stable disconnect code because the
backend/OS owns that failure reason. They assert recovery to a disconnected
application event and bounded process completion. This remains byte transport;
no entity synchronization, RPC, ownership or authentication format exists yet.

## Implemented in Phase 4.1

Lifecycle replication uses reliable application messages with a 12-byte
little-endian envelope: magic `E3DR`, 16-bit wire version `1`, 8-bit type, zero
flags and exact 32-bit payload length. Every lifecycle frame is at most 64
bytes. Types are snapshot begin (`1`), spawn (`2`), despawn (`3`) and snapshot
end (`4`).

Begin carries nonzero uint64 epoch, uint32 object count, uint32 prefab-schema
version and a 16-byte canonical registry fingerprint. Spawn carries nonzero
uint64 network-object ID plus nonzero uint32 prefab ID. Despawn carries the
object ID. End repeats the epoch. The server sends begin, current spawns sorted
by ID, then end to each established peer before later live lifecycle updates.

Clients require exact framing, known types/prefabs, matching schema/fingerprint,
declared count, matching epoch, unique IDs and configured object bounds. A
network-object ID is allocated monotonically by one authority and never derived
from a scene handle or reused in that authority session. Client-authored `E3DR`
frames are forbidden. This format contains no prefab field state, transform,
owner, RPC or Python serialization.

## Implemented in Phase 4.2

Value update type `5` uses the `E3DR` envelope followed by uint64 object ID,
uint16 field ID, uint8 declared type, uint64 monotonically increasing field
version, uint32 byte length and exact bytes. Types are bool, signed little-
endian int64, finite IEEE float64, strict control-free UTF-8 and opaque bytes.
Prefab fingerprints include canonical field ID/name/type/default/bound data.
Values are reliable, bounded to 60 KiB, and must match the frozen schema.
Snapshots stream every current field after its spawn; clients require every
declared field exactly once before accepting snapshot end. Live stale,
duplicate, unknown or type-mismatched updates are rejected. Clients cannot send
lifecycle/value magic to the authority.

## Implemented in Phase 4.3

Transform update type `6` uses the `E3DR` envelope and a fixed 64-byte payload:
uint64 network-object ID, uint64 snapshot sequence, uint64 simulation tick,
then ten little-endian IEEE float32 values for local position `(x,y,z)`, unit
quaternion `(w,x,y,z)` and nonzero scale `(x,y,z)`. The complete frame is 76
bytes. Prefab fingerprints include whether this fixed transform schema is
registered.

Live frames use unreliable delivery because a later sequence replaces missing
state. Sequences increase per authority flush; ticks cannot decrease. A client
retains a bounded ordered history per object, drops unknown, stale, duplicate
or older-tick frames, and replaces a same-tick sample only with a newer
sequence. Non-finite values, zero quaternions/scales, undeclared transforms and
invalid framing are protocol errors. Late-join streams include the current
transform baseline for each object relevant to that connection before snapshot
end.

The optional relevance predicate is authority-local policy and is not encoded
on the wire. It suppresses only type-6 traffic; reliable lifecycle and type-5
field state remain visible. There is no acknowledgement/baseline recovery,
spatial interest grid, extrapolation, prediction or reconciliation in this
format revision.

## Implemented in Phase 4.4

RPC call type `7` uses the `E3DR` envelope and a bounded payload beginning with
uint64 network-object ID, uint16 RPC ID, nonzero uint64 caller invocation
sequence and uint8 argument count. Each positional argument then contains uint8
declared primitive type, uint32 byte length and exact bytes. Calls have at most
16 arguments and a 60 KiB total payload. Types and value validation are the
same as type-5 fields; no callable/class/module name or Python object is sent.

The frozen prefab fingerprint includes RPC ID/name, direction, delivery,
ownership requirement, rate limit and argument type/bounds. Client-to-server
calls require a known object, matching direction/schema, a sequence newer than
that connection's last call and optional exact owner connection. The authority
drops calls beyond the registered one-second limit without execution. Unknown,
malformed, wrong-direction, replayed or ownership-tampered calls close the
offending connection. Server-to-client calls receive the inverse validation.
Reliable/unreliable is selected by schema and does not change authority.

## Implemented in Phase 4.8

Resync request type `8` is a reliable client control with exactly one nonzero
uint64 caller sequence. The server requires a snapshot-ready peer, strictly
newer sequence and a 250 ms minimum accepted interval. It temporarily removes
the peer from live recipients, queues a fresh ordinary snapshot and restores
readiness only after end is queued. Duplicate/replayed or malformed requests
disconnect; excess valid requests inside the interval are ignored. The request
contains no entity IDs or state.

## Not implemented yet

There is no rendered-Game attachment, firewall automation, DNS, replicated
ownership transfer or resynchronization yet. LAN discovery is IPv4/local-subnet
only.
Transport encryption also does not
establish account or player identity; authentication remains a separate
extension boundary.

## Threading and ownership

The direct-IP client and server service GNS callbacks only through
`RunCallbacks()` inside their owning poll. Native callbacks mutate native
connection state and never call Python, mutate a `Scene`, or retain a borrowed
Python buffer. Application events contain copied bounded data. Python callbacks
and protocol handling run afterward on the owning gameplay thread. Transport
objects are single-owner; concurrent operations are unsupported except the
high-level server's thread-safe `stop()` request.
