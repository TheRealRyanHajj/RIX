# Animation compatibility and retargeting

`Model.add_animation(name, path)` performs bounded same-rig retargeting. It is
intended for compatible exports of one named skeleton, including the audited
Mixamo YBot/Thriller pair; it is not a general humanoid solver.

RIX requires every deforming target joint to have a unique same-named source
joint and the same named parent. Extra source terminal joints are allowed. It
then checks finite rest data, per-axis rest scale ratio and non-root bone-length
ratio in `[0.25, 4]`, plus at most 120 degrees of local rest-rotation difference.
Failure identifies the missing joint or incompatible parent/rest property.

For accepted rigs, translation keys receive the source-to-target local rest
offset, rotations receive the local rest quaternion correction, and scale keys
receive the local rest ratio. The FBX importer has already normalized units,
axes, pivot stacks, and geometry transforms before this stage. Animation is
baked at the source frame rate (bounded at 120 Hz) into deterministic local TRS
keys; quaternion signs are made continuous.

Mixamo workflow:

1. Export the character and animation without altering bone names.
2. Load the character as a visible `Model`.
3. Attach the animation-only FBX with `add_animation()`.
4. Treat a compatibility exception as an asset mismatch; do not rename bones
   ad hoc or hide it with arbitrary model scaling.

Different naming schemes, missing deforming joints, changed parenting,
substantially different proportions/rest orientation, IK constraints, facial
rigs, and semantic humanoid mapping are unsupported. Convert those assets in a
DCC pipeline or add an explicit mapping/retarget profile in a future version.
