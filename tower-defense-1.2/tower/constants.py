# -*- coding: utf-8 -*-
from typing import Dict, Tuple
from itertools import chain
import glob
import pygame as pg
from structlog import get_logger

log = get_logger()


SOUNDS = {
    "footstep_1": "footstep01.ogg",
    "footstep_2": "footstep02.ogg",
    "footstep_3": "footstep03.ogg",
    "footstep_4": "footstep04.ogg",
    "thud": "thud.wav",
    "beep": "beep.ogg",
}

# Sound IDs to what they're used as.
SOUND_TURRET = "thud"
SOUND_FOOTSTEPS = "footstep_4"
SOUND_ESCAPED = "beep"

# Mapping of sprite ID to asset filename
SPRITES = {
    "game_logo": "game_logo.png",
    "land": "land.png",
    "road": "road.png",
    "road_edge": "road_edge.png",
    "road_large_corner": "road_large_corner.png",
    "road_small_corner": "road_small_corner.png",
    "road_escape": "road_escape.png",
    "road_spawn": "road_spawn.png",
    "decor_1": "decor_1.png",
    "decor_2": "decor_2.png",
    "decor_3": "decor_3.png",
    "decor_4": "decor_4.png",
    "decor_5": "decor_5.png",
    "decor_6": "decor_6.png",
    "decor_7": "decor_7.png",
    "decor_8": "decor_8.png",
    "decor_10": "decor_10.png",
    "decor_11": "decor_11.png",
    "decor_12": "decor_12.png",
    "decor_13": "decor_13.png",
    "decor_14": "decor_14.png",
    "decor_15": "decor_15.png",
    "decor_16": "decor_16.png",
    "decor_17": "decor_17.png",
    "decor_18": "decor_18.png",
    "stone_1": "stone_1.png",
    "stone_2": "stone_2.png",
    "stone_3": "stone_3.png",
    "stone_4": "stone_4.png",
    "bush_1": "bush_1.png",
    "bush_3": "bush_3.png",
    "backdrop": "main_bg.png",
    "blank": "blank.png",
    "turret": "tower.png",
    "projectile": "rock.png",
}

# We'll want our animations stored in such a way that we can render
# them in the right order. The files are numbered 001 to 00N for this
# reason.
ANIMATIONS = {
    "enemy_walk": ["enemy_1_walk_{:03}".format(frame) for frame in range(1, 19 + 1)],
    "enemy_die": ["enemy_1_die_{:03}".format(frame) for frame in range(1, 19 + 1)],
    "projectile_explode": ["rock_{:03}".format(frame) for frame in range(1, 4 + 1)],
}

# Don't forget to load them into our main SPRITES dictionary that does
# the actual image loading.
for animation in chain.from_iterable(ANIMATIONS.values()):
    SPRITES[animation] = f"{animation}.png"

# Load in the animations into the SPRITES dict.

# None means use pygame's default
FONT_NAME = None
FONT_SIZE = 20


# Turret vision rectangle. Note that if you change the dimensions you
# may have to rotate it also when it is created so it points in the
# right direction.
VISION_RECT = pg.Rect(0, 0, 32, 400)

# Desired framerate.
DESIRED_FPS = 60

# list of sprite IDs that count as background
ALLOWED_BG_SPRITES = [
    "road",
    "road_edge",
    "road_large_corner",
    "road_small_corner",
    "road_escape",
    "road_spawn",
]
# list of sprite IDs that count as shrubs
ALLOWED_SHRUBS = [
    "stone_1",
    "stone_2",
    "stone_3",
    "stone_4",
    "bush_1",
    "bush_3",
    "decor_1",
    "decor_2",
    "decor_3",
    "decor_4",
    "decor_5",
    "decor_6",
    "decor_7",
    "decor_8",
    "decor_10",
    "decor_11",
    "decor_12",
    "decor_13",
    "decor_14",
    "decor_15",
    "decor_16",
    "decor_17",
    "decor_18",
]

# Set of tile IDS that count as legitimate surfaces for enemies to
# walk on.
MOVABLE_TILE_IDS = {"road"}
# Tile ID where enemies start
START_TILE_ID = "road_spawn"
# Tile ID where enemies stop (and thus "escape")
STOP_TILE_ID = "road_escape"

# Tile width and height. This _must_ match the dimensions of the
# images or you'll wind up with black borders!
TILE_HEIGHT = 64
TILE_WIDTH = 64

# Pygame uses integers to represent mouse buttons; this makes it more
# obvious which is which.
MOUSE_LEFT, MOUSE_MIDDLE, MOUSE_RIGHT = 1, 2, 3

# Number of tiles in the Y and X axes
TILES_Y = 16
TILES_X = 24

# Defaults for the elimination game mode when game over is achieved,
# and when the intensity increases after killing a number of enemies.
MAX_ESCAPED = 20
INTENSITY_FREQUENCY = 20

# Size of the screen, scaled proportionally to the number of desires tiles on the x/y axes.
SCREENRECT = pg.Rect(0, 0, TILE_WIDTH * TILES_X, TILE_HEIGHT * TILES_Y)


# Key indices used for selecting sprites for placement
KEY_TURRET = 0
KEY_BACKGROUND = 1
KEY_SHRUB = 2
KEY_ENEMY = 4


# Holds the converted and imported sprite images. The key is a tuple
# of (flipped_x, flipped_y, sprite_name)
IMAGE_SPRITES: Dict[Tuple[bool, bool, str], pg.Surface] = {}

# List of colors to draw the debug paths with
PATH_COLORS = ["turquoise1", "blue1", "firebrick1", "gold1"]

CACHE = {}
