# -*- coding: utf-8 -*-
import random
from dataclasses import dataclass, field
from itertools import chain
from typing import Optional, Tuple

import pygame as pg
from structlog import get_logger
from pygame.math import Vector2 as Vector

from tower.constants import (
    MOVABLE_TILE_IDS,
    START_TILE_ID,
    STOP_TILE_ID,
    TILES_X,
    TILES_Y,
)
from tower.helpers import angle_to, interpolate, tile_positions, pairwise

log = get_logger()


def get_portals(tile_map, start_tile_index, stop_tile_index):
    """
    Given a `tile_map`, walk through tile-by-tile and record all
    start and stop positions.

    The tiles used for either is controlled by `start_tile_index` and
    `stop_tile_index`.

    Return two sets, each containing the stop or start positions.
    """
    start_positions = set()
    stop_positions = set()
    for (gy, gx, _, _) in tile_positions():
        tile = tile_map[gy][gx]
        if tile.index == start_tile_index:
            start_positions.add((gx, gy))
        elif tile.index == stop_tile_index:
            stop_positions.add((gx, gy))
    return start_positions, stop_positions


@dataclass
class GridTile:
    """
    Helper class that builds up a graph of vertices and edges,
    with each vertex (`GridTile`) representing a legitimate, walkable
    surface, such as a road tile.

    Any (or all) of the four cardinal directions (N, S, E, W) are set
    if, and only if, there is an adjacent walkable grid
    tile. Otherwise it is `None`.

    This class remembers the `tile` sprite that it belongs to along
    with a tuple of its grid `position`.
    """

    tile: pg.sprite.Sprite
    position: Tuple[int, int]
    east: Optional["GridTile"] = field(repr=False, default=None)
    west: Optional["GridTile"] = field(repr=False, default=None)
    north: Optional["GridTile"] = field(repr=False, default=None)
    south: Optional["GridTile"] = field(repr=False, default=None)


def dfs_find_path(start_tile: GridTile, stop_positions):
    """
    Given a starting tile `start_tile` and a set of
    `stop_positions` recursively -- using Depth-First Search --
    attempt to find *a* path to one of `stop_positions`.

    Note this is not a shortest path algorithm like Dijkstra's
    Shortest Path or A*. Instead it randomly walks in a cardinal
    direction until it finds a valid stop position. At that point it
    exits the search and returns the path.

    This approach is more organic as it allows for enemies to wander
    towards a goal without necessarily picking the optimal path.

    The general principle of how `_walk` works is simple:

    1. When _walk is invoked it's given a path list (it might be empty)
    and the current tile it needs to investigate. if that tile is
    already in `visited` or `None`, return an empty list.

    2. Add the current tile to `visited` and check if the current tile
    is a stop position. If it is, return the current tile + our path.

    3. Given four cardinal directions (N, S, E, W) shuffle them and
    call _walk on them, passing in our existing `path` plus the
    current tile.

    4. If the return value of _walk is not an empty list, we exit ---
    we found a path from start to stop. If it is not, try another
    cardinal direction, and go to 1.
    """

    # Keep track of visited grid tiles
    visited = {}

    def _walk(
        path: list,
        current_tile: Optional[GridTile],
    ):
        # If the current_tile is None (i.e,. it is out of bounds or is
        # not a valid direction) _or_ if we've visited the tile
        # before, return an empty list indicating no path was found.
        if current_tile is None or current_tile.position in visited:
            return []
        # Make a note that we've now visited this position.
        visited[current_tile.position] = current_tile
        # If the current tile's position is a valid stop position then
        # we have a path from the start to a stop tile. return the
        # `path` we've travelled thus far and also include the current
        # tile as that is the stop tile.
        if current_tile.position in stop_positions:
            return path + [current_tile]
        # All possible cardinal directions. Some may be None; that's
        # OK, the recursive call checks if it's dealing with a None
        # entry at the beginning.
        directions = [
            current_tile.east,
            current_tile.west,
            current_tile.north,
            current_tile.south,
        ]
        # This is optional. By shuffling the directions list, we
        # ensure that the enemies never take the same identical path
        # through to a position. Leave it out to make it totally
        # deterministic
        random.shuffle(directions)
        for direction in directions:
            # Recursively call _walk with the current path travelled
            # so far (plus our current tile) and the next tile
            # (`direction`) to check along.
            subpath = _walk(path + [current_tile], direction)
            # If we get a subpath back from _walk, then that means it
            # found a solution --- we can then exit knowing that we've
            # found _a_ path to a stop position
            if subpath:
                return subpath
        return []

    return _walk([], start_tile)


def get_directions(start_tile: GridTile, stop_positions):
    """
    Find a path from `start_tile` to any of
    `stop_positions`. Return a list of vectors from each tile's center
    rect position to the next.
    """
    try:
        vectors = []
        for a, b in pairwise(dfs_find_path(start_tile, stop_positions)):
            v2 = Vector(b.tile.rect.center)
            v1 = Vector(a.tile.rect.center)
            vectors.append(
                (
                    v1,
                    v2,
                )
            )
    except StopIteration:
        pass
    return vectors


def walk_grid(tile_map, visited, gx, gy, valid_tile_indices):
    """
    Given a 2d grid of `tile_map`, recursively walk through it one
    grid position at a time and build a graph of `GridTile` if the
    tile index is one of `valid_tile_indices`.
    """
    if not 0 <= gx < TILES_X or not 0 <= gy < TILES_Y:
        return None
    if tile := visited.get((gx, gy)):
        return tile
    tile = tile_map[gy][gx]
    if tile.index in valid_tile_indices or tile.index in (
        STOP_TILE_ID,
        START_TILE_ID,
    ):
        tile = GridTile(tile=tile, position=(gx, gy))
        visited[(gx, gy)] = tile
        # Recursively check each cardinal direction
        tile.east = walk_grid(tile_map, visited, gx + 1, gy, valid_tile_indices)
        tile.west = walk_grid(tile_map, visited, gx - 1, gy, valid_tile_indices)
        tile.north = walk_grid(tile_map, visited, gx, gy - 1, valid_tile_indices)
        tile.south = walk_grid(tile_map, visited, gx, gy + 1, valid_tile_indices)
        return tile
    return None


def make_enemy_path(start_tile, stop_position, jitter=10, speed=40, turn_speed=8):
    """
    Given a `start_tile` and a `stop_position` and `jitter` create
    an interpolated path from start to finish that an enemy (or
    another enemy) can walk.

    `speed` governs how quickly an enemy moves from one tile to the
    next. `turn_speed` controls how fast enemies turn when they have
    to rotate to move in another direction
    """
    # Add a bit of jitter to the start and end position so they don't
    # all spawn and despawn at the same relative point. That'd look weird.
    jitter = random.randint(-jitter, jitter)
    # Use a hardcoded offset to ensure the sprite's feet are placed
    # within the sprite. This is because we calculate everything from
    # the center of a sprite but then randomize the X,Y coordinate it
    # starts at. So to avoid the sprite appearing outside its
    # designated tile we subtract a little from the Y coordinate.
    jv = Vector(jitter, -30 + jitter)
    for v1, v2 in pairwise(
        chain.from_iterable(
            interpolate(t, speed) for t in get_directions(start_tile, stop_position)
        )
    ):
        # Required; if v1 == v2, then v1 - v2 = 0, which is impossible to normalize.
        if v1 == v2:
            continue
        # Calculate the dot-product between the normalized vectors of
        # v1 and v2.  Recall that normalizing "scales" a vector so its
        # magnitude (length) is 1.
        dot = v1.normalize().dot((v2 - v1).normalize())
        # If the dot product is less than zero then we are going
        # right-to-left instead of left-to-right. That means we have to
        # flip the sprite (or it'd look like the sprite is walking backwards)
        flipx = dot < 0
        yield (
            v2 + jv,
            0,
            flipx,
        )


def update_path_finding(tile_map):
    """
    Given a tile map, calculate all possible start/stop
    combinations that an enemy can move between.

    This code is clever enough to distinguish between separate
    'islands' of stop/start positions that do not overlap at all.
    """
    start_positions, stop_positions = get_portals(tile_map, START_TILE_ID, STOP_TILE_ID)
    paths = []
    while start_positions:
        visited = {}
        gx, gy = start_positions.pop()
        start_tile = walk_grid(tile_map, visited, gx, gy, MOVABLE_TILE_IDS)
        # Determine which stop tiles are reachable from start_positions
        for stop_position in stop_positions:
            try:
                paths.append((start_tile, visited[stop_position]))
            except KeyError:
                pass

    return paths
