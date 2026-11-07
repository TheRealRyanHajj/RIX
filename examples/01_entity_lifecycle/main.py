"""Generation-safe entity and scene ownership example."""

from rix import Entity, Game, InvalidEntityError, Scene


def main() -> None:
    world = Scene("lifecycle example")
    with world:
        player = Entity("player")
        prop = Entity("prop")

    game = Game("RIX scene lifecycle")
    game.load_scene(world)
    print(f"loaded {world.name!r} with {world.entity_count} entities")

    old_id = prop.id
    prop.destroy()
    replacement = world.create_entity("replacement")
    print(f"destroyed id={old_id}; replacement id={replacement.id}")

    try:
        print(prop.name)
    except InvalidEntityError as error:
        print(f"stale access rejected: {error}")

    game.unload_scene(clear=True)
    world.close()
    print(f"scene closed={world.closed}; player alive={player.is_alive}")


if __name__ == "__main__":
    main()
