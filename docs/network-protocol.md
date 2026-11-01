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

## Not implemented yet

There is no wire frame, socket address, listener, client, server, encryption,
handshake, schema/version negotiation, timeout, discovery, firewall behavior,
replication or RPC in Phase 3.1. Python bytes never leave the process through
this simulator.

Phase 3.2 will adapt pinned GameNetworkingSockets to the transport contract and
record its Protobuf/crypto build and license details. Phase 3.3 will define the
first bounded wire header and handshake. Until those milestones pass, no
interoperability or security claim is made.

## Threading and ownership

A concrete backend may receive data on a native callback/worker thread. It must
copy validated bounded data into its event queue and return; it must not call
Python, mutate a `Scene`, or retain a borrowed Python buffer. The gameplay or
server thread polls events and applies protocol state at its documented safe
boundary. Shutdown must stop producers before destroying their queues.
