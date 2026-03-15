"""Helper functions for the Defense game."""

from itertools import tee


def pairwise(iterable):
    """Return successive overlapping pairs from iterable: (s0,s1), (s1,s2), ..."""
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def interpolate(waypoints, steps):
    """Yield pixel positions along the path defined by waypoints.

    steps: number of frames to spend travelling between each pair of waypoints.
    Positions are integer (x, y) tuples suitable for assigning to rect.topleft.
    The final waypoint is yielded once after all segments are complete.
    """
    waypoints = list(waypoints)
    for start, end in pairwise(waypoints):
        x1, y1 = start
        x2, y2 = end
        for j in range(steps):
            t = j / steps
            yield (int(x1 + t * (x2 - x1)), int(y1 + t * (y2 - y1)))
    if waypoints:
        yield waypoints[-1]
