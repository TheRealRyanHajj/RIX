# RIX beginner learning path

Follow these lessons in order. They teach Python game code first; CMake,
bindings, components, quaternions, and raw physics configuration are deferred
until the advanced lesson.

1. [Your First Game](your-first-3d-game.md)
2. [Drawing Cubes and Spheres](creating-objects.md)
3. [Moving Objects](moving-objects.md)
4. [Reading Input](reading-input.md)
5. [Working With the Game Loop](working-with-the-game-loop.md)
6. [Adding a Player](making-a-player.md)
7. [Using Physics](adding-physics.md)
8. [Adding Enemies](adding-enemies.md)
9. [Playing Sounds](playing-sounds.md)
10. [Making UI](making-a-menu.md)
11. [Creating Multiple Levels](creating-multiple-levels.md)
12. [Using Classes](using-classes.md)
13. [State Machines and Timers](using-state-machines.md)
14. [Advanced Engine Features](advanced-engine-apis.md)
15. [Lighting and Skies](lighting-and-skies.md)
16. [Adding RIX to an Existing Pygame Project](migrating-a-pygame-project.md)

Runnable versions live in `examples/beginner`. Run them from the repository
root with the same interpreter used to install RIX.

## Multiplayer and state systems

These focused tutorials follow the approved multiplayer/state learning path:

1. [Sending a Network Message](sending-a-network-message.md)
2. [Hosting a Pygame Game](hosting-a-pygame-game.md)
3. [Joining a Game](joining-a-game.md)
4. [Creating a Dedicated Server](creating-a-dedicated-server.md)
5. [Synchronizing Objects](synchronizing-objects.md)
6. [Making a Multiplayer FPS](making-a-multiplayer-fps.md)
7. [Creating Your First State Machine](creating-your-first-state-machine.md)
8. [Making a Menu](making-a-menu-screen.md)
9. [Creating Enemy AI](creating-enemy-ai-states.md)
10. [Using a Pause Screen](using-a-pause-screen.md)
11. [Using State Machines on a Server](server-side-state-machines.md)

Each begins with the smallest public-API form. The networking examples under
`examples/networking` provide the corresponding independent processes.
