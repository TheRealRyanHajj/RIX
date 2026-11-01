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

## Not implemented yet

There is no public listener/server, discovery, firewall automation, DNS,
replication or RPC yet. Phase 3.5 supplies the authoritative headless server;
Phase 3.8 supplies a supported two-process sample and abrupt-disconnect/port
collision integration. Transport encryption also does not establish account or
player identity; authentication remains a separate extension boundary.

## Threading and ownership

The current direct-IP client services its connection-specific GNS callback only
through `RunCallbacks()` inside `poll()`. The callback mutates native connection
state and never calls Python, mutates a `Scene`, or retains a borrowed Python
buffer. Application events contain copied bounded data. Python callbacks and
protocol event handling run afterward on the gameplay thread that called
`poll()`. A client is single-owner; concurrent calls from multiple threads are
unsupported.
