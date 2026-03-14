# -*- coding: utf-8 -*-
import importlib.resources
import pygame as pg


def load(module_path, name):
    return importlib.resources.path(module_path, name)


def import_sound(asset_name: str):
    """
    Imports, as a sound effect, `asset_name`.
    """
    with load("tower.assets.audio", asset_name) as resource:
        return pg.mixer.Sound(resource)


def import_image(asset_name: str):
    """
    Imports, as an image, `asset_name`.
    """
    with load("tower.assets.gfx", asset_name) as resource:
        return pg.image.load(resource).convert_alpha()


def import_level(asset_name: str):
    """
    Imports as level named `asset_name`.
    """
    with load("tower.assets.levels", asset_name) as resource:
        return resource.open()
