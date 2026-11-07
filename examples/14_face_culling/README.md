# Face-culling visual validation

Run the scene from the repository root:

```powershell
python examples\14_face_culling\main.py --view outside
python examples\14_face_culling\main.py --view inside-double
python examples\14_face_culling\main.py --view inside-front
```

The outside view shows an ordinary outward-facing cube and a double-sided
plane. The two inside views place the camera inside a normal-mapped
double-sided blue room and a front-cull orange room respectively. All modes
retain ordinary depth testing and shadow reception. Use `--seconds 5` for a
bounded smoke run.
