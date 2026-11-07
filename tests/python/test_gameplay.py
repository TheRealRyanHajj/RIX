from __future__ import annotations

import pytest

from rix import (
    Cube,
    Enemy,
    Entity,
    Game,
    Health,
    HitscanWeapon,
    Interaction,
    Player,
    Respawner,
    Scoreboard,
    Scene,
    SpawnPoint,
    Team,
    TeamRoster,
)


def test_health_damage_heal_death_and_reset_events() -> None:
    game = Game()
    actor = Entity("actor")
    source = Entity("source")
    health = Health(actor, 100)
    damaged: list[float] = []
    deaths: list[Entity | None] = []
    health.on_damage(lambda event: damaged.append(event.amount))
    health.on_death(lambda event: deaths.append(event.source))

    assert health.damage(30, source=source).current == pytest.approx(70)  # type: ignore[union-attr]
    assert health.heal(10) == pytest.approx(10)
    assert health.damage(500, source=source).current == 0  # type: ignore[union-attr]
    assert damaged == [30, 80]
    assert deaths == [source]
    assert not health.alive
    health.reset()
    assert health.current == 100 and health.alive
    assert Health.for_entity(Entity._from_handle(game.scene, actor._handle)) is health
    game.close()


def test_hitscan_damage_cooldown_and_cover_use_native_queries() -> None:
    game = Game()
    shooter = Entity("shooter")
    shooter.position = (0, 0, 2)
    target = Cube(z=-3, collider=True, name="target")
    target_health = Health(target, 100)
    weapon = HitscanWeapon(shooter, damage=25, range=20, cooldown=0.2)

    shot = weapon.fire(direction=(0, 0, -1))
    assert shot is not None and shot.hit is not None and shot.hit.entity == target
    assert target_health.current == 75
    assert weapon.fire(direction=(0, 0, -1)) is None
    weapon.advance(0.2)

    cover = Cube(z=0, collider=True, name="cover")
    blocked = weapon.fire(direction=(0, 0, -1))
    assert blocked is not None and blocked.hit is not None
    assert blocked.hit.entity == cover and blocked.damage is None
    assert target_health.current == 75
    game.close()


def test_respawn_scoreboard_and_distance_validated_interaction() -> None:
    game = Game()
    actor = Entity("actor")
    health = Health(actor, 50)
    health.damage(50)
    respawner = Respawner(
        [
            SpawnPoint((1, 2, 3), (0, 90, 0), team="blue"),
            SpawnPoint((-2, 1, 4), team="red"),
        ],
        seed=7,
    )
    chosen = respawner.respawn(actor, team="blue")
    assert chosen.team == "blue"
    assert tuple(actor.position) == pytest.approx((1, 2, 3))
    assert actor.ry == pytest.approx(90)
    assert health.current == 50

    scores = Scoreboard()
    scores.add_player("blue")
    scores.add_player("red", score=2)
    scores.add("blue", 3)
    assert scores.ranking == (("blue", 3), ("red", 2))

    used: list[Entity] = []
    switch = Entity("switch")
    switch.position = (1, 2, 4)
    interaction = Interaction(switch, used.append, distance=2)
    assert interaction.interact(actor) and used == [actor]
    actor.position = (20, 0, 0)
    assert not interaction.interact(actor)
    game.close()


def test_enemy_preset_is_visible_customizable_and_uses_character_motor() -> None:
    game = Game()
    target = Entity("target")
    target.position = (0, 0, -5)
    enemy = Enemy(target=target, health=60, speed=2.5, name="Chaser")
    assert enemy.visual.parent == enemy
    assert enemy.health.maximum == 60
    enemy.fixed_update(1 / 60)
    game.scene._native.step_physics(1 / 60)
    assert enemy.position.z < 0
    enemy.behavior = "idle"
    enemy.fixed_update(1 / 60)
    game.close()


def test_team_roster_balancing_and_entity_lifetime() -> None:
    game = Game()
    red = Team("Red", "red")
    blue = Team("Blue", "#3366ff")
    roster = TeamRoster(red, blue)
    first = Cube()
    second = Cube()
    assert roster.assign(first, roster.smallest()) is red
    assert roster.assign(second, roster.smallest()) is blue
    assert roster.team_of(first) is red
    assert roster.members("Blue") == (second,)

    handle = first.destroy_after(0.01)
    game._scheduler.begin_run()
    game._callback_active = True
    game._gameplay_thread_id = __import__("threading").get_ident()
    try:
        game._scheduler.advance(game.scene, 1 / 60)
        game.scene._commit_deferred(game._scheduler.destroy_callback)
    finally:
        game._callback_active = False
        game._gameplay_thread_id = None
    assert not first.is_alive
    assert not handle.active
    assert roster.remove(second)
    game.close()


def test_entity_health_and_managed_player_weapon_use_existing_systems() -> None:
    game = Game()
    player = Player(position=(0, 1, 2), controls=False)
    target = Cube(position=(0, 1, -3), collider=True)
    health = target.add_health(100)
    assert target.health is health
    weapon = player.add_weapon(damage=20, cooldown=0.1, range=20)
    assert player.weapon is weapon and weapon.managed

    shot = weapon.fire(origin=(0, 1, 2), direction=(0, 0, -1))
    assert shot is not None and shot.hit is not None and shot.hit.entity == target
    assert health.current == 80 and not weapon.ready
    game._scheduler.begin_run()
    game._scheduler.advance(game.scene, 0.1)
    assert weapon.ready

    player.destroy()
    assert not weapon.managed
    game.close()


def test_managed_entity_helpers_cancel_when_scene_is_replaced() -> None:
    game = Game()
    player = Player(controls=False)
    weapon = player.add_weapon()
    replacement = Scene("replacement")
    game.load_scene(replacement)
    assert not weapon.managed
    game.close()
