# Authoritative network arenas

This finite headless sample runs cooperative and competitive arena rules over
real GameNetworkingSockets loopback. Clients own only their attack-request RPC.
The authority validates ownership, match phase, target type/team and range,
then changes health, score and the replicated match phase.

```powershell
python examples/08_network_arenas/main.py --mode cooperative --clients 4
python examples/08_network_arenas/main.py --mode competitive --clients 4
```

Cooperative clients destroy one shared objective and all receive one score.
Competitive clients have distinct teams; player zero eliminates player one and
receives one score. Both finish in `MATCH_END`. This is a bounded local
integration sample, not rendered combat, matchmaking, authentication, anti-cheat
or a performance/capacity claim.
