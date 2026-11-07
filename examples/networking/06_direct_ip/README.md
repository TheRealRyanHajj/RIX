# Direct-IP connection

```powershell
python examples\networking\06_direct_ip\server.py --bind 0.0.0.0 --port 7782
python examples\networking\06_direct_ip\client.py 127.0.0.1:7782
```

For internet use the address and UDP port must already be reachable. This does
not claim NAT traversal, room codes, hosted matchmaking, or relay service.
