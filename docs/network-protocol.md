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

## Not implemented yet

There is no rendered-Game attachment, discovery, firewall automation, DNS,
replication or RPC yet. Phase 3.8 supplies a supported two-process sample and
abrupt-disconnect/port-collision integration. Transport encryption also does not
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
