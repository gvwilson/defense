"""Sprites for the Defense game."""

import importlib.resources
import pygame

from .grid import GRID_COLS, GRID_ROWS, cell_to_pixel


class Pilgrim(pygame.sprite.Sprite):
    _image = None

    @classmethod
    def _load_image(cls):
        if cls._image is None:
            ref = importlib.resources.files("defense.static.gfx").joinpath("pilgrim.png")
            with importlib.resources.as_file(ref) as path:
                cls._image = pygame.image.load(str(path)).convert_alpha()
        return cls._image

    @staticmethod
    def waypoints():
        """Generate pixel positions for the pilgrim's staircase path.

        Moves one cell right then one cell down, repeating until the edge
        of the grid is reached.
        """
        col, row = 0, 0
        yield cell_to_pixel(col, row)
        while True:
            col += 1
            if col >= GRID_COLS:
                break
            yield cell_to_pixel(col, row)
            row += 1
            if row >= GRID_ROWS:
                break
            yield cell_to_pixel(col, row)

    def __init__(self, path):
        super().__init__()
        self.image = self._load_image()
        self.path = path
        start = next(self.path)
        self.rect = self.image.get_rect(topleft=start)

    def update(self):
        try:
            self.rect.topleft = next(self.path)
        except StopIteration:
            self.kill()
