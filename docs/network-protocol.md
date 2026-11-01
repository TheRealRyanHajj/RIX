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

## Not implemented yet

There is no public socket address, listener, client, server, wire frame,
handshake, schema/version negotiation, timeout, discovery, firewall behavior,
replication or RPC yet. Python bytes leave the process only in later concrete
transport APIs; the current backend exercise is an in-process native socket
pair. Phase 3.3 defines the first bounded wire header and handshake, and Phase
3.4 adapts live connections to the transport contract. Until those milestones
pass, no application interoperability, identity or authentication claim is
made.

## Threading and ownership

A concrete backend may receive data on a native callback/worker thread. It must
copy validated bounded data into its event queue and return; it must not call
Python, mutate a `Scene`, or retain a borrowed Python buffer. The gameplay or
server thread polls events and applies protocol state at its documented safe
boundary. Shutdown must stop producers before destroying their queues.
