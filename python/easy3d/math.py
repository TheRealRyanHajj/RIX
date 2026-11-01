"""Easy3D-owned public vector and quaternion values."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
import math
from typing import Any

from ._easy3d import _quat_from_euler, _quat_to_euler


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _components(value: object, count: int, label: str) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{label} must contain {count} numbers")
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError(f"{label} must contain {count} numbers") from error
    if len(items) != count:
        raise ValueError(f"{label} must contain exactly {count} numbers")
    return tuple(_finite(item, f"{label}[{index}]") for index, item in enumerate(items))


class Vec2:
    """Two-dimensional finite vector with exact equality semantics."""

    __slots__ = ("_values", "_getter", "_setter")

    def __init__(self, x: float | Iterable[float] = 0.0, y: float | None = None) -> None:
        if y is None and not isinstance(x, (int, float)):
            values = _components(x, 2, "Vec2")
        else:
            values = (_finite(x, "x"), _finite(0.0 if y is None else y, "y"))
        self._values = values
        self._getter: Callable[[], tuple[float, float]] | None = None
        self._setter: Callable[[tuple[float, float]], None] | None = None

    @classmethod
    def _live(
        cls,
        getter: Callable[[], tuple[float, float]],
        setter: Callable[[tuple[float, float]], None],
    ) -> Vec2:
        value = cls()
        value._getter = getter
        value._setter = setter
        return value

    def _read(self) -> tuple[float, float]:
        return self._values if self._getter is None else self._getter()

    def _write(self, values: tuple[float, float]) -> None:
        self._values = values
        if self._setter is not None:
            self._setter(values)

    @property
    def x(self) -> float:
        return self._read()[0]

    @x.setter
    def x(self, value: float) -> None:
        _, y = self._read()
        self._write((_finite(value, "x"), y))

    @property
    def y(self) -> float:
        return self._read()[1]

    @y.setter
    def y(self, value: float) -> None:
        x, _ = self._read()
        self._write((x, _finite(value, "y")))

    @property
    def length_squared(self) -> float:
        return self.x * self.x + self.y * self.y

    @property
    def length(self) -> float:
        return math.sqrt(self.length_squared)

    def normalized(self) -> Vec2:
        if self.length <= 1.0e-12:
            raise ValueError("cannot normalize a zero-length Vec2")
        return self / self.length

    def dot(self, other: Vec2) -> float:
        if not isinstance(other, Vec2):
            raise TypeError("dot expects Vec2")
        return self.x * other.x + self.y * other.y

    def almost_equal(self, other: Vec2, tolerance: float = 1.0e-6) -> bool:
        return isinstance(other, Vec2) and math.isclose(
            self.x, other.x, abs_tol=tolerance, rel_tol=tolerance
        ) and math.isclose(self.y, other.y, abs_tol=tolerance, rel_tol=tolerance)

    def __iter__(self) -> Iterator[float]:
        return iter(self._read())

    def __add__(self, other: Vec2) -> Vec2:
        if not isinstance(other, Vec2):
            return NotImplemented
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        if not isinstance(other, Vec2):
            return NotImplemented
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vec2:
        value = _finite(scalar, "scalar")
        return Vec2(self.x * value, self.y * value)

    __rmul__ = __mul__

    def __truediv__(self, scalar: float) -> Vec2:
        value = _finite(scalar, "scalar")
        if value == 0.0:
            raise ZeroDivisionError("cannot divide Vec2 by zero")
        return Vec2(self.x / value, self.y / value)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Vec2) and self._read() == other._read()

    def __repr__(self) -> str:
        return f"Vec2({self.x!r}, {self.y!r})"


class Vec3:
    """Three-dimensional finite vector; entity properties return live instances."""

    __slots__ = ("_values", "_getter", "_setter")

    def __init__(
        self,
        x: float | Iterable[float] = 0.0,
        y: float | None = None,
        z: float | None = None,
    ) -> None:
        if y is None and z is None and not isinstance(x, (int, float)):
            values = _components(x, 3, "Vec3")
        else:
            values = (
                _finite(x, "x"),
                _finite(0.0 if y is None else y, "y"),
                _finite(0.0 if z is None else z, "z"),
            )
        self._values = values
        self._getter: Callable[[], tuple[float, float, float]] | None = None
        self._setter: Callable[[tuple[float, float, float]], None] | None = None

    @classmethod
    def _live(
        cls,
        getter: Callable[[], tuple[float, float, float]],
        setter: Callable[[tuple[float, float, float]], None],
    ) -> Vec3:
        value = cls()
        value._getter = getter
        value._setter = setter
        return value

    @classmethod
    def from_value(cls, value: Vec3 | Iterable[float]) -> Vec3:
        return cls(tuple(value))

    def _read(self) -> tuple[float, float, float]:
        return self._values if self._getter is None else self._getter()

    def _write(self, values: tuple[float, float, float]) -> None:
        self._values = values
        if self._setter is not None:
            self._setter(values)

    @property
    def x(self) -> float:
        return self._read()[0]

    @x.setter
    def x(self, value: float) -> None:
        _, y, z = self._read()
        self._write((_finite(value, "x"), y, z))

    @property
    def y(self) -> float:
        return self._read()[1]

    @y.setter
    def y(self, value: float) -> None:
        x, _, z = self._read()
        self._write((x, _finite(value, "y"), z))

    @property
    def z(self) -> float:
        return self._read()[2]

    @z.setter
    def z(self, value: float) -> None:
        x, y, _ = self._read()
        self._write((x, y, _finite(value, "z")))

    @property
    def length_squared(self) -> float:
        return self.x * self.x + self.y * self.y + self.z * self.z

    @property
    def length(self) -> float:
        return math.sqrt(self.length_squared)

    def normalized(self) -> Vec3:
        if self.length <= 1.0e-12:
            raise ValueError("cannot normalize a zero-length Vec3")
        return self / self.length

    def dot(self, other: Vec3) -> float:
        if not isinstance(other, Vec3):
            raise TypeError("dot expects Vec3")
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vec3) -> Vec3:
        if not isinstance(other, Vec3):
            raise TypeError("cross expects Vec3")
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def almost_equal(self, other: Vec3, tolerance: float = 1.0e-6) -> bool:
        return isinstance(other, Vec3) and all(
            math.isclose(left, right, abs_tol=tolerance, rel_tol=tolerance)
            for left, right in zip(self, other, strict=True)
        )

    def __iter__(self) -> Iterator[float]:
        return iter(self._read())

    def __add__(self, other: Vec3) -> Vec3:
        if not isinstance(other, Vec3):
            return NotImplemented
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        if not isinstance(other, Vec3):
            return NotImplemented
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __neg__(self) -> Vec3:
        return Vec3(-self.x, -self.y, -self.z)

    def __mul__(self, scalar: float) -> Vec3:
        value = _finite(scalar, "scalar")
        return Vec3(self.x * value, self.y * value, self.z * value)

    __rmul__ = __mul__

    def __truediv__(self, scalar: float) -> Vec3:
        value = _finite(scalar, "scalar")
        if value == 0.0:
            raise ZeroDivisionError("cannot divide Vec3 by zero")
        return Vec3(self.x / value, self.y / value, self.z / value)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Vec3) and self._read() == other._read()

    def __repr__(self) -> str:
        return f"Vec3({self.x!r}, {self.y!r}, {self.z!r})"


class Quat:
    """Right-handed quaternion stored as ``(w, x, y, z)``."""

    __slots__ = ("w", "x", "y", "z")

    def __init__(
        self,
        w: float | Iterable[float] = 1.0,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> None:
        if x is None and y is None and z is None and not isinstance(w, (int, float)):
            values = _components(w, 4, "Quat")
        else:
            values = (
                _finite(w, "w"),
                _finite(0.0 if x is None else x, "x"),
                _finite(0.0 if y is None else y, "y"),
                _finite(0.0 if z is None else z, "z"),
            )
        self.w, self.x, self.y, self.z = values

    @property
    def length_squared(self) -> float:
        return self.w**2 + self.x**2 + self.y**2 + self.z**2

    @property
    def length(self) -> float:
        return math.sqrt(self.length_squared)

    def normalized(self) -> Quat:
        if self.length <= 1.0e-12:
            raise ValueError("cannot normalize a zero-length Quat")
        return Quat(self.w / self.length, self.x / self.length, self.y / self.length, self.z / self.length)

    def conjugate(self) -> Quat:
        return Quat(self.w, -self.x, -self.y, -self.z)

    @classmethod
    def from_euler(cls, value: Vec3 | Iterable[float]) -> Quat:
        euler = Vec3.from_value(value)
        return cls(_quat_from_euler(euler.x, euler.y, euler.z))

    def to_euler(self) -> Vec3:
        return Vec3(_quat_to_euler(self.w, self.x, self.y, self.z))

    def rotate(self, value: Vec3 | Iterable[float]) -> Vec3:
        vector = Vec3.from_value(value)
        unit = self.normalized()
        rotated = unit * Quat(0.0, vector.x, vector.y, vector.z) * unit.conjugate()
        return Vec3(rotated.x, rotated.y, rotated.z)

    def almost_equal(self, other: Quat, tolerance: float = 1.0e-6) -> bool:
        if not isinstance(other, Quat):
            return False
        direct = (self.w, self.x, self.y, self.z)
        candidate = (other.w, other.x, other.y, other.z)
        return all(
            math.isclose(left, right, abs_tol=tolerance, rel_tol=tolerance)
            for left, right in zip(direct, candidate, strict=True)
        ) or all(
            math.isclose(left, -right, abs_tol=tolerance, rel_tol=tolerance)
            for left, right in zip(direct, candidate, strict=True)
        )

    def __iter__(self) -> Iterator[float]:
        return iter((self.w, self.x, self.y, self.z))

    def __mul__(self, other: Quat) -> Quat:
        if not isinstance(other, Quat):
            return NotImplemented
        return Quat(
            self.w * other.w - self.x * other.x - self.y * other.y - self.z * other.z,
            self.w * other.x + self.x * other.w + self.y * other.z - self.z * other.y,
            self.w * other.y - self.x * other.z + self.y * other.w + self.z * other.x,
            self.w * other.z + self.x * other.y - self.y * other.x + self.z * other.w,
        )

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Quat) and tuple(self) == tuple(other)

    def __repr__(self) -> str:
        return f"Quat({self.w!r}, {self.x!r}, {self.y!r}, {self.z!r})"
