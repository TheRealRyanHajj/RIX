"""One-process listen host with isolated authority and local client roles."""

from __future__ import annotations

import argparse

from easy3d import Entity, ListenServer, Scene, network


class HostLogic(Entity):
    def __init__(self, host: ListenServer, *, scene: Scene) -> None:
        self.host = host
        self.ticks = 0
        super().__init__("HostAuthorityLogic", scene=scene)

    def fixed_update(self, _dt: float) -> None:
        self.ticks += 1
        if self.ticks == 3:
            self.host.client.send(b"local host input")
        elif self.ticks == 6 and self.host.authority_connection is not None:
            self.host.authority.send(
                self.host.authority_connection,
                b"authoritative host snapshot",
            )
        elif self.ticks == 12:
            self.host.stop("listen-host example complete")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--tick-rate", type=float, default=60.0)
    arguments = parser.parse_args()

    def event(_host: ListenServer, tagged: network.ListenEvent) -> None:
        print(
            f"{tagged.role.value:9} host={tagged.local_host} "
            f"{tagged.event.type.value:12} id={tagged.event.connection.value} "
            f"payload={tagged.event.payload!r}"
        )

    host = ListenServer(
        bind_address="127.0.0.1",
        port=arguments.port,
        tick_rate=arguments.tick_rate,
        on_event=event,
    )
    scene = Scene("ListenAuthority")
    logic = HostLogic(host, scene=scene)
    host.load_scene(scene)
    host.run()
    print(f"listen host stopped after {logic.ticks} authoritative ticks")


if __name__ == "__main__":
    main()
