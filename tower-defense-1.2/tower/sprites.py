# -*- coding: utf-8 -*-
import enum
import operator
import random
from dataclasses import dataclass, field
from itertools import accumulate, chain, cycle, repeat, count
from typing import Generator, Optional, Dict
import pygame as pg
from structlog import get_logger
from pygame.math import Vector2 as Vector

from tower.constants import (
    ALLOWED_BG_SPRITES,
    ALLOWED_SHRUBS,
    CACHE,
    FONT_NAME,
    IMAGE_SPRITES,
    ANIMATIONS,
    SOUND_FOOTSTEPS,
    SOUND_TURRET,
    SOUNDS,
    TILE_HEIGHT,
    TILE_WIDTH,
    VISION_RECT,
)
from tower.helpers import create_surface, extend, interpolate

log = get_logger()


class AnimationState(enum.Enum):

    """
    Possible animation states for a sprite
    """

    stopped = "stopped"
    # for enemies
    walking = "walking"
    dying = "dying"
    # for projectiles
    exploding = "exploding"

    @classmethod
    def state_kills_sprite(cls, state):
        """
        Return True if, upon reaching the end of an animation for
        `state`, if the sprite should be killed.

        This is useful if you want to run an animation until it
        expires (like a dying animation) and then have the animation
        routine auto-kill the sprite.

        This, of course, will not trigger for animation generators
        that never cause a `StopIteration`, nor for sprites where this
        not desired, even if the animation is finite.
        """
        return state in (cls.exploding, cls.dying)


class SpriteState(enum.Enum):

    """
    Possible states for movable sprites (like enemies)
    """

    unknown = "unknown"
    moving = "moving"
    stopped = "stopped"


class Layer(enum.IntEnum):

    """
    Enum of all possible layers you can assign a sprite. Note the
    numbered ordering: lower numbers are drawn _before_ higher
    numbers.
    """

    background = 0
    decal = 10
    turret = 20
    turret_sights = 21
    shrub = 25
    enemy = 30
    projectile = 40
    hud = 60


class Sprite(pg.sprite.Sprite):
    """
    Base class for sprites.
    """

    # The layer the sprite is drawn against. By default it's the background.
    _layer = Layer.background

    @classmethod
    def create_from_sprite(
        cls,
        index,
        groups,
        sounds=None,
        image_tiles=IMAGE_SPRITES,
        orientation=0,
        flipped_x=False,
        flipped_y=False,
        **kwargs,
    ):
        """
        Class method that creates a sprite from a tileset, by
        default `IMAGE_SPRITES`.
        """
        image = image_tiles[(flipped_x, flipped_y, index)]
        rect = image.get_rect()
        return cls(
            image=image,
            image_tiles=image_tiles,
            index=index,
            groups=groups,
            sounds=sounds,
            rect=rect,
            orientation=orientation,
            **kwargs,
        )

    @classmethod
    def create_from_surface(cls, groups, surface, sounds=None, orientation=0, **kwargs):
        """
        Class method that creates a sprite from surface.
        """
        rect = surface.get_rect()
        return cls(
            groups=groups,
            image=surface,
            index=None,
            sounds=sounds,
            rect=rect,
            orientation=orientation,
            **kwargs,
        )

    def __init__(
        self,
        groups,
        image_tiles=None,
        index=None,
        rect=None,
        sounds=None,
        channel=None,
        image=None,
        frames=None,
        animation_state=AnimationState.stopped,
        position=(0, 0),
        orientation=0,
        flipped_x=False,
        flipped_y=False,
    ):
        """
        Traditional constructor for the `pg.sprite.Sprite` class,
        as it does not (easily) support dataclasses.
        """
        super().__init__(groups)
        self.image = image
        self.image_tiles = image_tiles
        self.index = index
        self.rect = rect
        self.frames = frames
        self.sounds = sounds
        self.orientation = orientation
        self.channel = channel
        self.animation_state = animation_state
        self.sprite_offset = Vector(0, 0)
        self.angle = self.generate_rotation()
        self._last_angle = None
        self.flipped_x = flipped_x
        self.flipped_y = flipped_y
        if self.image is not None:
            self.mask = pg.mask.from_surface(self.image)
            self.surface = self.image.copy()
            self.rotate(self.orientation)
        if self.rect is not None and position is not None:
            self.move(position)

    def move(self, position, center: bool = True):
        """
        Moves the sprite by changing the position of the
        rectangle. By default it moves the center; otherwise, the top
        left.
        """
        assert self.rect is not None, "No rect!"
        if center:
            self.rect.center = position
        else:
            self.rect.topleft = position

    def rotate_cache_key(self):
        """
        Returns a tuple of fields used as a cache key to speed up rotations
        """
        return (self.flipped_x, self.flipped_y, self.index)

    def rotate(self, angle):
        """
        Rotates the sprite and regenerates its mask.
        """
        # Do not rotate if the desired angle is the same as the last
        # angle we rotated to.
        if angle == self._last_angle:
            return
        try:
            k = (self.rotate_cache_key(), angle)
            new_image = CACHE[k]
        except KeyError:
            new_image = pg.transform.rotate(self.surface, angle % 360)
            CACHE[k] = new_image
        new_rect = new_image.get_rect(center=self.rect.center)
        self.image = new_image
        self.rect = new_rect
        self.mask = pg.mask.from_surface(self.image)
        self._last_angle = angle

    def generate_rotation(self):
        """
        Repeats the sprite's default orientation forever.

        This is typically done only for sprites with a fixed
        orientation that never changes.
        """
        return repeat(self.orientation)

    def set_orientation(self, orientation):
        """
        Updates the orientation to `orientation`.
        """
        self.orientation = orientation
        self.angle = self.generate_rotation()
        self.rotate(next(self.angle))

    def update(self):
        """
        Called by the game loop every frame.
        """
        angle = next(self.angle)
        self.rotate(angle)
        self.animate()

    def animate(self):
        # If we're called upon to animate, we must have frames that we
        # can animate. If not, we do nothing.
        if self.frames is not None:
            # Given out animation state, determine the roll of
            # animation frames to use. For instance, dying is a
            # different set of animations than what we'd use when
            # we're moving
            roll = self.frames[self.animation_state]
            if roll is not None:
                try:
                    # Because roll is a generator, we request the next
                    # frame. But! It's possible there is no next
                    # frame: we may have a finite number of frames
                    # (like dying) as opposed to infinite frames (like
                    # a walking animation)
                    next_frame_index = next(roll)
                    if next_frame_index != self.index:
                        self.set_sprite_index(next_frame_index)
                except StopIteration:
                    # When you exhaust a generator it raises
                    # `StopIteration`. We catch the exception and ask
                    # the Animation system if our animation state, now
                    # that we've run out of animations to play,
                    # results in the sprite dying.
                    if AnimationState.state_kills_sprite(self.animation_state):
                        self.kill()
                    # Regardless, we stop our animation state at this point.
                    self.animation_state = AnimationState.stopped

    def play(self):
        """
        Plays a sound if there is a sound generator attached; the
        mixer is initialized; and a channel is assigned.
        """
        if self.sounds is not None and pg.mixer and self.channel is not None:
            effect_name = next(self.sounds)
            if effect_name is not None:
                effect = SOUNDS[effect_name]
                # Do not attempt to play if the channel is busy.
                if not self.channel.get_busy():
                    self.channel.play(effect, fade_ms=10)

    def set_sprite_index(self, index):
        """
        Sets the sprite to `index` and updates the image accordingly.
        """
        self.image = self.image_tiles[(self.flipped_x, self.flipped_y, index)]
        self.surface = self.image.copy()
        self.rect = self.image.get_rect(center=self.rect.center)
        self.mask = pg.mask.from_surface(self.image)
        self.index = index
        self.rotate(self.orientation)


class Background(Sprite):
    """
    Default background sprite. Unlike normal sprites, this one does not rotate.
    """

    _layer = Layer.background

    def update(self):
        pass


class DirectedSprite(Sprite):
    """
    Subclass of `Sprite` that understands basic motion and rotation.

    Given a `path` generator, iterate through it one game tick at a
    time, updating the position and rotation. When the generator is
    exhausted, change the sprite `state` to `SpriteState.stopped`.
    """

    def __init__(self, path, state=SpriteState.unknown, **kwargs):
        super().__init__(**kwargs)
        self.state = state
        self.path = path

    def update(self):
        try:
            self.animate()
            if self.path is not None:
                self.state = SpriteState.moving
                position, angle = next(self.path)
                self.move(position)
                self.rotate(angle + next(self.angle))
            self.play()
        except StopIteration:
            self.state = SpriteState.stopped


class Enemy(DirectedSprite):
    """
    Subclass of `DirectedSprite` that additionally adds subtle
    rotation to the Enemy to mimic human gait.
    """

    _layer = Layer.enemy

    def __init__(self, health: int = 100, **kwargs):
        # Tracks the offset, if any, if the image is flipped
        self.sprite_offset = Vector(0, 0)
        self.health = health
        super().__init__(**kwargs)

    def update(self):
        try:
            self.animate()
            if self.path is not None:
                # If we're dying we stop moving.
                if self.animation_state == AnimationState.dying:
                    return
                self.state = SpriteState.moving
                position, _, flipx = next(self.path)
                # The state of flipx has changed since we were last
                # invoked; that happens whenever our orientation is
                # supposed to change.
                if flipx != self.flipped_x:
                    # Acknowledge flipx is changed and update the internal state.
                    self.flipped_x = flipx
                    # Calculate the centroid of our CURRENT mask,
                    # before we ask `set_sprite_index` to flip our
                    # image.
                    centroid = self.mask.centroid()
                    # Change to our current index (but actually flip
                    # it because we set flipped_x before)
                    self.set_sprite_index(self.index)
                    # Now get the _new_ centroid
                    new_centroid = self.mask.centroid()
                    # The delta between both centroids is the offset
                    # we must apply to our movement to ensure the
                    # flipped image is placed in the exact same
                    # position as before
                    self.sprite_offset = Vector(new_centroid) - Vector(centroid)
                if flipx:
                    self.move(position - self.sprite_offset)
                else:
                    self.move(position)
            self.play()
        except StopIteration:
            self.state = SpriteState.stopped


class Turret(Sprite):
    """
    Turret sprite that rotates in a sweeping motion in the direction of `orientation`.

    Additionally, the turret tracks whether it is capable of firing based on `cooldown` and `cooldown_remaining`.
    """

    _layer = Layer.turret

    def __init__(self, cooldown, cooldown_remaining, **kwargs):
        super().__init__(**kwargs)
        self.cooldown = cooldown
        self.cooldown_remaining = cooldown_remaining

    def update(self):
        super().update()
        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= 1

    def generate_rotation(self):
        return repeat(0)

    def shoot(self):
        """
        Returns True if this turret is capable of firing.
        """
        if self.cooldown_remaining == 0:
            self.cooldown_remaining = self.cooldown
            self.play()
            return True
        return False


class Shrub(Background):
    """
    Background subclass that changes the layer to `Layer.shrub`.
    """

    _layer = Layer.shrub


class Decal(Background):
    """
    Background subclass that changes the layer to `Layer.decal`.
    """

    _layer = Layer.decal


class Projectile(DirectedSprite):
    """
    Background subclass that changes the layer to `Layer.projectile`
    """

    _layer = Layer.projectile

    def update(self):
        super().update()
        if self.state == SpriteState.stopped:
            self.animation_state = AnimationState.exploding


class Text(DirectedSprite):
    """
    Subclass of `DirectedSprite` that allows for rendering text in
    addition to basic directed movement.

    Can optionally store an `action` that represents an action to be
    taken if the item is invoked somehow.
    """

    def __init__(self, text, color, size, action=None, path=None, **kwargs):
        self.color = color
        self.size = size
        self.font = pg.font.Font(FONT_NAME, size)
        self.action = action
        self.rect = pg.Rect(0, 0, 0, 0)
        self.set_text(text)
        super().__init__(path=path, image=self.image, rect=self.rect, **kwargs)

    def rotate_cache_key(self):
        """
        Returns a tuple of fields used as a cache key to speed up rotations
        """
        return (
            self.flipped_x,
            self.flipped_y,
            self.index,
            self.text,
            self.size,
        )

    def set_text(self, text):
        self.text = text
        self.render_text()

    def render_text(self):
        self.image = self.font.render(self.text, True, self.color)
        self.surface = self.image
        self.rect = self.image.get_rect(center=self.rect.center)


class HUDText(Text):
    """
    Subclass of `Text` that stores a game `mode` and updates the
    rendered text every frame with vital game stats. However, due to
    how the `Text` sprite re-renders, we need to additionally store
    the old texto ensure we only force re-renders when the text
    actually has changed.
    """

    _layer = Layer.hud

    def __init__(self, mode, **kwargs):
        super().__init__(**kwargs)
        self.mode = mode
        self._old_text = None

    def update(self):
        text = f"Killed: {self.mode.killed} Escaped: {self.mode.escaped} Intensity: {self.mode.intensity} Max turrets: {self.mode.max_defenses}"
        if text != self._old_text:
            self.set_text(text)
        self._old_text = text
        super().update()


def create_animation_roll(frames: Dict[AnimationState, Generator[int, None, None]]):
    """
    Takes a dictionary of animation states (as keys) and frame
    generators (as values) and fills out the missing ones with `None`.
    """
    for state in AnimationState:
        if state not in frames:
            frames[state] = None
    return frames


def create_turret_sweep(orientation, sweep_degrees, speed=3):
    """
    Creates a turret sweep generator that points in `orientation`
    and sweeps between `sweep_degrees`.
    """
    half_sweep = sweep_degrees // 2
    return cycle(
        extend(
            chain(
                range(orientation - half_sweep, orientation + half_sweep),
                reversed(range(orientation - half_sweep, orientation + half_sweep)),
            ),
            speed,
        ),
    )


class Vision(Sprite):
    """
    Vision sprite that represents what a turret can see.
    """

    _layer = Layer.turret_sights

    @classmethod
    def create_vision(cls, rect, **kwargs):
        """
        Draws a vision of `rect` size and then proceeds to create
        a regular sprite from a surface.
        """
        surface = create_surface(size=rect.size)
        surface.fill((0, 0, 128, 128))
        surface.set_colorkey((0, 128, 128))
        pg.draw.rect(surface, (0, 128, 128), rect, width=2)
        return cls.create_from_surface(surface=surface, **kwargs)

    def __init__(self, turret, **kwargs):
        """
        Creates a vision belonging to `turret`.
        """
        self.turret = turret
        super().__init__(**kwargs)

    def generate_rotation(self):
        return create_turret_sweep(self.orientation, sweep_degrees=60)

    def rotate(self, angle):
        # rotate the rectangle shape so it points, length-wise,
        # away. If you reverse the width/height you may need to alter
        # this angle!
        new_angle = angle + 90
        new_image = pg.transform.rotozoom(self.surface, new_angle, 1)
        turret = self.turret
        # Determine where to put the rectangle relative to the turret
        v = Vector(
            0,
            (self.surface.get_rect().height // 2 + turret.surface.get_rect().top),
        )
        # Recall that rotating a vector and applying a rotation using
        # the transform library is different! The transform library
        # "understands" the coordinate system used by computers;
        # namely, that origin (0,0) is in the top-left corner of the
        # screen as opposed to the bottom-right used in cartesian
        # coordinate systems.
        #
        # Vectors, on the other hand, use regular geometry and as such
        # we must negate the angle to ensure the rotation is correct
        # when we add that vector to the computer's coordinate system.
        rv = v.rotate(-new_angle)
        new_rect = new_image.get_rect(center=turret.rect.center + rv)
        self.image = new_image
        self.rect = new_rect
        self.mask = pg.mask.from_surface(self.image)


@dataclass
class SpriteManager:
    """
    Sprite Manager that manages the creation and placement of sprites.

    The `sprites` group is the internal store of sprites currently
    managed by the sprite manager. This is usually the case when
    you're picking and placing sprites during map editing or game
    play.

    The `layers` group is a reference to the primary layers group used
    for the game loop renderer.

    `indices` is a generator of indices the user can cycle through
    with the scroll wheel.

    `channels` is a reference to the dictionary of named channels to
    actual sound mixer channels.

    `_last_index` and `_last_orientation` track the most recent index
    and orientation.
    """

    sprites: pg.sprite.LayeredUpdates
    layers: pg.sprite.LayeredUpdates
    indices: Optional[Generator[int, None, None]]
    channels: dict
    _last_index: Optional[int] = field(init=False, default=None)
    _last_orientation: int = field(init=False, default=0)

    def update(self):
        """
        Pass-through to the internal sprite group's update method.
        """
        return self.sprites.update()

    def clear(self, dest, background):
        """
        Pass-through to the internal sprite group's clear method.
        """
        return self.sprites.clear(dest, background)

    def draw(self, surface):
        """
        Pass-through to the internal sprite group's draw method.
        """
        return self.sprites.draw(surface)

    def empty(self):
        """
        Pass-through to the sprite group's empty method.
        """
        self.sprites.empty()

    def kill(self):
        """
        Kills all sprites in the internal sprites group.
        """
        for sprite in self.sprites:
            sprite.kill()

    def increment_orientation(self, relative_orientation):
        """
        Increments each sprite's relative orientation by `relative_orientation`.
        """
        for sprite in self.sprites:
            rot = sprite.orientation
            rot += relative_orientation
            rot %= 360
            sprite.set_orientation(rot)
            self._last_orientation = rot

    def move(self, position):
        """
        Moves all sprites in the internal sprite group to `position`.

        However, a special case is made for background layer items, as
        they are ALWAYS aligned on a grid. Those sprites are instead
        'snapped' to the nearest grid tile.

        All other sprites are moved by their center position.
        """
        x, y = position
        for sprite in self.sprites:
            if sprite.layer == Layer.background:
                gx, gy = (x - (x % TILE_WIDTH), y - (y % TILE_HEIGHT))
                sprite.move((gx, gy), center=False)
            else:
                sprite.move((x, y))

    def place(self, position, clear_after=True):
        """
        Places all sprites in the internal sprite group at `position`.

        This is typically the outcome of left-clicking on the game map
        to place sprites.
        """
        for sprite in self.sprites:
            sprite.move(position)
            if clear_after:
                self.sprites.remove(sprite)

    def reset(self):
        """
        Resets the last index and orientation.
        """
        self._last_index = None
        self._last_orientation = 0

    def cycle_index(self):
        """
        Cycles the index of sprites to the next one in the
        generator and updates the sprite index of all sprites
        accordingly.

        Note this only works with background and shrub sprites.
        """
        if self.indices is None:
            return
        new_index = next(self.indices)
        for sprite in self.sprites:
            if sprite.layer in (Layer.background, Layer.shrub):
                sprite.set_sprite_index(new_index)
        self._last_index = new_index

    @property
    def selected(self):
        """
        Returns true the internal sprite group is 'truthy' ---
        that is, if it has elements.
        """
        return bool(self.sprites)

    def select_sprites(self, sprites, position=None):
        """
        Selects `sprites` by adding them to the internal sprite
        group and optionally moves them all to `position`.
        """
        self.sprites.add(sprites)
        if position is not None:
            self.move(position)

    def create_background(self, position, orientation=None, index=None):
        """
        Factory that creates a background sprite at a given
        `position`, with optional `index` and `orientation`.
        """
        if index is None:
            index = self._last_index
        self.indices = cycle(ALLOWED_BG_SPRITES)
        if orientation is None:
            orientation = self._last_orientation
        background = Background.create_from_sprite(
            sounds=None,
            groups=[self.layers],
            index=next(self.indices) if index is None else index,
            orientation=orientation,
        )
        return background

    def create_shrub(self, position, orientation=None, index=None):
        """
        Factory that creates a shrub sprite at a given `position`,
        with optional `index` and `orientation`.
        """
        if index is None:
            index = self._last_index
        self.indices = cycle(ALLOWED_SHRUBS)
        if orientation is None:
            orientation = self._last_orientation
        shrub = Shrub.create_from_sprite(
            sounds=None,
            groups=[self.layers],
            index=next(self.indices) if index is None else index,
            orientation=orientation,
        )
        return shrub

    def create_enemy(self, position, path):
        """
        Factory that creates a enemy sprite at a given `position` with a `path`.
        """
        enemy = Enemy.create_from_sprite(
            index="enemy_1_walk_001",
            sounds=cycle(chain([SOUND_FOOTSTEPS], repeat(None, 120))),
            channel=self.channels["footsteps"],
            animation_state=AnimationState.walking,
            frames=create_animation_roll(
                {
                    AnimationState.walking: cycle(extend(ANIMATIONS["enemy_walk"], 2)),
                    AnimationState.dying: chain(
                        iter(ANIMATIONS["enemy_die"]),
                        # Repeat the last frame for a little while
                        # before the sprite is killed.
                        repeat(ANIMATIONS["enemy_die"][-1], 20),
                    ),
                },
            ),
            path=path,
            groups=[self.layers],
            state=SpriteState.moving,
        )
        enemy.move(position)
        return [enemy]

    def create_projectile(self, source, target, speed=4, max_distance=150):
        """
        Factory that creates a projectile sprite starting at `source`
        and moves toward `target` at `speed` before disappearing if it
        reaches `max_distance`.
        """
        # v1 is our target -- aiming for the center of the sprite rect.
        v1 = Vector(target.rect.center)
        # v1 is our source -- starting at the center of the sprite rect.
        v2 = Vector(source.rect.center)

        # Calculate the unit vector of (v1-v2) then multiply it by `speed`
        vh = (v1 - v2).normalize() * speed
        path = zip(
            # Using accumulate we can repeatedly build up sums of v2 +
            # (vh * N) where N is the N'th iteration.
            #
            # Thus, the resulting generator yields:
            #
            #  [v2,
            #   v2 + vh,
            #   v2 + vh + vh,
            #   ...,
            #   v2 + (N * vh )] until `max_distance`.
            accumulate(repeat(vh, max_distance), func=operator.add, initial=v2),
            # It's a rock, so let's make it rotate a bit as it flies
            count(random.randint(0, 180)),
        )
        projectile = Projectile.create_from_sprite(
            position=source.rect.center,
            groups=[self.layers],
            orientation=0,
            index="projectile",
            frames=create_animation_roll(
                {
                    AnimationState.exploding: extend(
                        ANIMATIONS["projectile_explode"], 2
                    ),
                },
            ),
            path=path,
            sounds=None,
        )
        projectile.move(source.rect.center)
        return [projectile]

    def create_turret(self, position, orientation: int = 90):
        """
        Create a turret (and associated sprites) at `position`
        with optional `orientation`.
        """
        turret = Turret.create_from_sprite(
            position=position,
            groups=[self.layers],
            index="turret",
            cooldown=30,
            sounds=cycle(chain([SOUND_TURRET])),
            channel=self.channels["turrets"],
            cooldown_remaining=0,
            orientation=0,
        )
        turret.move(position)
        vision = Vision.create_vision(
            rect=VISION_RECT,
            turret=turret,
            position=position,
            groups=[self.layers],
            orientation=orientation,
        )
        vision.move(position)
        return [turret, vision]
