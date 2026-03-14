"""Sprites for the Defense game."""

import importlib.resources
import pygame


class Pilgrim(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        ref = importlib.resources.files("defense.static.gfx").joinpath("pilgrim.png")
        with importlib.resources.as_file(ref) as path:
            self.image = pygame.image.load(str(path)).convert_alpha()
        self.rect = self.image.get_rect(topleft=(x, y))
