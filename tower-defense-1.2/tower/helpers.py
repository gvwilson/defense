# -*- coding: utf-8 -*-
from structlog import get_logger
from itertools import tee

try:
    from itertools import pairwise
except ImportError:
    # Backport pairwise to older Python versions
    def pairwise(iterable):
        a, b = tee(iterable)
        next(b, None)
        return zip(a, b)


from tower.constants import TILE_WIDTH, TILE_HEIGHT, TILES_X, TILES_Y, SCREENRECT
from math import atan2, degrees, pi
import pygame as pg

log = get_logger()


def get_tile_position(position):
    """
    Given a position, calculate the grid tile position
    """
    x, y = position
    return x // TILE_WIDTH, y // TILE_HEIGHT


def tile_positions():
    """
    Given a range of TILES_Y and TILES_X, generate all grid positions along with their top-left position.
    """

    for y in range(TILES_Y):
        for x in range(TILES_X):
            yield (y, x, x * TILE_WIDTH, y * TILE_HEIGHT)


def linear(a, b, m, n):
    """
    Finds a data point between `a` and `b` such that its value is
    the `m`'th value over `n` data points:

    >>> linear(0, 10, 2, 4)
    5.0

    >>> linear(0, 10, 2, 8)
    2.5
    """
    return a + (m * (b - a) / n)


def cube(t):
    """
    Easing function for `lerp`
    """

    return (1 - t) * (1 - t) * (1 - t) + 1


def cube_in_out(t):
    """
    Easing function for `lerp`
    """

    if t < 0.5:
        return 4 * t * t * t
    p = 2 * t - 2
    return 0.5 * p * p * p + 1


def interpolate(iterable, n, fn=linear):
    """
    Interpolate `iterable` with `n` arguments generated between
    each pairwise set. The default `fn` is `linear`, for
    linear interpolation.

    Note, unlike the Vector's `lerp()` method where you're giving it
    `t` for its interval, this smoothly returns `n` values between all
    pairwise elements in `iterable`.

    Because regular arithmetic _and_ vector arithmetic behaves
    similarly, you can specify both an iterable of vectors or numbers:

    NOTE: This function calculates to `n + 1` to ensure the last
    iterable is also included in the calculation

    >>> list(interpolate([0, 10], n=5))
    [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]

    >>> list(interpolate([Vector(0,0), Vector(10,10)], n=5))
    [<Vector2(0, 0)>,
     <Vector2(2, 2)>,
     <Vector2(4, 4)>,
     <Vector2(6, 6)>,
     <Vector2(8, 8)>,
     <Vector2(10, 10)>,
    ]
    """
    return (fn(a, b, m, n) for a, b in pairwise(iterable) for m in range(0, n + 1))


def lerp(a, b, t):
    return a + (t * (b - a))


def angle_to(v1, v2):
    """
    Finds the angle between two vectors, `v1` and `v2`.

    This function is clever enough to convert between cartesian and
    screen coordinate systems and, thanks to `atan2`, all the gnarly
    computational stuff you'd otherwise have to do with normal `atan`
    is done for us.
    """
    dx, dy = v1 - v2
    rads = atan2(-dy, dx)
    rads %= 2 * pi
    degs = degrees(rads)
    return degs


def extend(iterable, repeat):
    """
    Given an iterable, repeat each element `repeat` times before
    continuing to the next.
    """
    return (elem for elem in iterable for _ in range(repeat))


def create_surface(size=SCREENRECT.size, flags=pg.SRCALPHA):
    """
    Creates a surface of `size`, which defaults to the screen
    rectangle size, with `flags`. Which by default includes alpha
    blending support.
    """
    return pg.Surface(size, flags=flags)


def get_grid_rect(gx, gy):
    """
    Returns a Rect of the grid tile (gx, gy)
    """
    return pg.Rect(gx * TILE_WIDTH, gy * TILE_HEIGHT, TILE_WIDTH, TILE_HEIGHT)
