# Two-process direct-IP sample

Open two terminals in the repository root after installing Easy3D. For local
loopback, start the server:

```powershell
python examples/06_two_process/main.py server --bind 127.0.0.1 --port 7777 --one-shot
```

Then run the client:

```powershell
python examples/06_two_process/main.py client --address 127.0.0.1 --port 7777
```

The client completes the real GNS/Phase 3.3 handshake, sends one bounded
request, validates the server reply and disconnects. `--one-shot` makes the
server exit after that client; omit it to keep accepting later clients until
the configured timeout. `--peer-timeout` configures connected-peer liveness
detection separately from the overall sample timeout; its default is 10
seconds and observation remains poll/backend-scheduling dependent.

For two Windows machines on the same LAN, bind the server to `0.0.0.0` and pass
its numeric LAN IPv4 address to the client. Windows Defender Firewall must allow
the Python/game executable's inbound UDP game port on the Private profile.
Easy3D does not change firewall rules. Guest Wi-Fi isolation, VPNs and router
policy can block peers. The opt-in discovery API can suggest an address, but
the direct numeric command remains the fallback.

This is a transport exit-gate sample only. It exchanges application bytes; it
does not spawn or synchronize entities, authenticate players, assign ownership,
run RPCs, or attach a rendered `Game`. Those begin in Phase 4.
