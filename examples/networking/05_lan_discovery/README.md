# LAN discovery and connection

LAN discovery is an opt-in UDP control plane; gameplay still uses the normal
encrypted transport and explicit Session connection.

```powershell
python examples\networking\05_lan_discovery\server.py
python examples\networking\05_lan_discovery\client.py
```

For deterministic same-machine testing, pass `--target 127.0.0.1` to the
client. Discovery is an untrusted hint and is currently IPv4 only.
