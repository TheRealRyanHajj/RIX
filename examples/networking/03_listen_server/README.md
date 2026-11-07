# Listen-server arrangement

This finite headless example uses the real transport. One authority and one
isolated local client complete the same handshake used by remote clients; only
the authority owns simulation ticks.

```powershell
python examples\networking\03_listen_server\main.py
```

It is a connection-arrangement example, not a simulated endpoint or load test.
