# -*- coding: utf-8 -*-
import enum
import json
import random
import tkinter
import tkinter.filedialog
from contextlib import contextmanager
from dataclasses import dataclass, field
from itertools import chain, repeat, tee
from typing import Generator, Optional, List

import pygame as pg
from structlog import get_logger
from pygame.math import Vector2 as Vector

from tower.constants import (
    DESIRED_FPS,
    IMAGE_SPRITES,
    PATH_COLORS,
    INTENSITY_FREQUENCY,
    KEY_BACKGROUND,
    KEY_SHRUB,
    KEY_ENEMY,
    KEY_TURRET,
    MAX_ESCAPED,
    MOUSE_LEFT,
    MOUSE_RIGHT,
    SCREENRECT,
    SOUNDS,
    SPRITES,
    TILES_X,
    TILES_Y,
)
from tower.helpers import (
    create_surface,
    lerp,
    cube,
    get_tile_position,
    interpolate,
    tile_positions,
    get_grid_rect,
    pairwise,
)
from tower.loader import import_image, import_sound, import_level
from tower.pathfinding import make_enemy_path, update_path_finding, get_directions
from tower.sprites import (
    AnimationState,
    Background,
    HUDText,
    Layer,
    SpriteManager,
    SpriteState,
    Text,
    Sprite,
)

# Required to hide the default TKinter window that appears, and to
# initialize Tkinter so we can use the open and save dialogs
root = tkinter.Tk()
root.withdraw()

log = get_logger()


@dataclass
class GameMode:
    """
    Base class for a Game Mode used by the game engine to:

    - Spawn new enemies
    - Manage win and loss conditions
    - Reset the game state
    - Check if the game is lost or won

    Derived classes must override the methods that raise `NotImplementedError`.

    The `next()` method is invoked every game tick a positive number
    indicates how many enemies must be spawned by the game engine.

    The `killed` and `escaped` values are updated by the game engine
    whenever an enemy is killed or escapes.
    """

    killed: int
    escaped: int

    def reset(self) -> None:
        """
        Resets the game state back to the default.
        """
        raise NotImplementedError("A Game Mode must be resettable")

    def has_lost(self) -> bool:
        """
        Defines the loss condition for the game mode. Must return
        True if the game is lost.
        """
        raise NotImplementedError("No loss condition defined")

    def has_won(self) -> bool:
        """
        Defines the win condition for the game mode. Must return
        True if the game is won.
        """
        raise NotImplementedError("No win condition defined")

    def check_win_or_loss(self) -> bool:
        """
        Returns True if the game is either lost or won.
        """
        return self.has_lost() or self.has_won()

    def next(self) -> int:
        """
        Advances the game mode in some way. If the method returns
        a positive, non-zero number, then that is how many enemies the
        game engine must spawn.
        """
        return 0

    def can_place_turret(self, existing: int) -> int:
        """
        Returns True if the player can place a turret. The
        `existing` value indicates how many already exist in the game
        world
        """
        return 0


@dataclass
class GameModeElimination(GameMode):
    """
    Elimination-style Game Mode where successively larger and
    larger waves of enemies are spawned. Once a `max_escaped` limit is
    reached, the game is lost. The number of turret emplacements the
    player can use is governed by `max_defenses`, which scales with
    the `intensity`. The `intensity_frequency` scales with the number
    of `killed` enemies.

    The `wave` generator is the wave pattern to use to spawn enemies.

    As with everything else, the `create` classmethod instantiates the
    classw ith sensible defaults
    """

    intensity: int
    max_escaped: int
    max_defenses: int
    wave: Generator[int, None, None]
    intensity_frequency: int

    @classmethod
    def create(cls):
        o = cls(
            killed=0,
            escaped=0,
            intensity=1,
            max_defenses=1,
            max_escaped=MAX_ESCAPED,
            intensity_frequency=INTENSITY_FREQUENCY,
            wave=cls.create_wave(intensity=1),
        )
        return o

    def has_lost(self):
        # We've lost the game when the number of escaped enemies exceeds
        # the maximum allowed escapes multiplied by the intensity.
        return self.escaped > self.max_escaped * self.intensity

    def has_won(self):
        # Elimination-style games have no outright win criteria.
        return False

    def reset(self):
        self.killed = 0
        self.escaped = 0
        self.intensity = 1
        self.max_defenses = 1
        self.wave = self.create_wave(self.intensity)

    @staticmethod
    def create_wave(intensity):
        # Creates "waves" of enemies of `intensity` strength.
        while True:
            # Fixed delay between spawn rates
            yield from repeat(0, 30)
            for _ in range(intensity):
                # Spawn one enemy up to intensity, with a random delay
                # to make it seem chaotic and unpredictable
                yield 1
                yield from repeat(0, random.randint(10, 50))

    def can_place_turret(self, existing: int):
        return self.intensity > existing

    def next(self):
        v = next(self.wave)
        # Scale the intensity with the number of kills.
        # The more enemies you kill, the greater the intensity.
        if self.killed == self.intensity * self.intensity_frequency:
            self.intensity += 1
            self.max_defenses += 1
            self.wave = self.create_wave(self.intensity)
        return v


def save_level(tile_map, shrubs, file_obj):
    """
    Saves `tile_map` and `shrubs` to file_obj. No other sprite types (turrets, etc.) are saved.
    """
    output_map = create_tile_map()
    # This is the default format for the file. If you change it, you
    # must ensure the loader is suitably updated also.
    data = {"background": None, "shrub": None, "waves": None}
    for (y, x, _, _) in tile_positions():
        bg_tile = tile_map[y][x]
        assert isinstance(
            bg_tile, Background
        ), f"Must be a Background tile object and not a {bg_tile}"
        output_map[y][x] = {"index": bg_tile.index, "orientation": bg_tile.orientation}
    data["background"] = output_map
    output_shrubs = []
    for shrub in shrubs:
        output_shrubs.append(
            {
                "index": shrub.index,
                "position": shrub.rect.center,
                "orientation": shrub.orientation,
            }
        )
    data["shrubs"] = output_shrubs
    file_obj.write(json.dumps(data))


def create_tile_map(default_value=None) -> list:
    """
    Factory that creates a grid tile map with `default_value`.
    """
    return [[default_value for _ in range(TILES_X)] for _ in range(TILES_Y)]


def create_background_tile_map(raw_tile_map):
    """
    Creates a background tile map given a raw tile map sourced from a level save file.
    """
    background_tiles = create_tile_map()
    for (y, x, dx, dy) in tile_positions():
        raw_tile = raw_tile_map[y][x]
        background_tile = Background.create_from_sprite(
            groups=[],
            index=raw_tile["index"],
            orientation=raw_tile["orientation"],
        )
        background_tile.rect.topleft = (dx, dy)
        background_tiles[y][x] = background_tile
    return background_tiles


def collide_mask(group_a, group_b):
    """
    Uses the sprite mask attribute to check if two groups of sprites are colliding.
    """
    for sprite_a, sprite_b in pg.sprite.groupcollide(
        group_a,
        group_b,
        False,
        False,
        collided=pg.sprite.collide_mask,
    ).items():
        yield sprite_a, sprite_b


class GameState(enum.Enum):
    """
    Enum for the Game's State Machine. Every state represents a
    known game state for the game engine.
    """

    # Unknown state, indicating possible error or misconfiguration.
    unknown = "unknown"
    # The state the game engine would rightly be set to before
    # anything is initialized or configured.
    starting = "starting"
    # The game engine is initialized: pygame is configured, the sprite
    # images are loaded, etc.
    initialized = "initialized"
    # The game engine is in map editing mode
    map_editing = "map_editing"
    # The game engine is in game playing mode
    game_playing = "game_playing"
    # The game engine is in the main menu
    main_menu = "main_menu"
    # The game engine is rendering the game ended screen.
    game_ended = "game_ended"
    # The game engine is exiting and is unwinding
    quitting = "quitting"


class StateError(Exception):
    """
    Raised if the game is in an unexpected game state at a point
    where we expect it to be in a different state. For instance, to
    start the game loop we must be initialized.
    """


@dataclass
class TowerGame:
    """
    Represents the Game Engine and the main entry point for the entire game.

    This is where we track global state that transcends individual game
    states and game play loops, and where we hold references to each
    unique game loop also.

    The `screen` represents the SDL screen surface we draw on. The
    `screen_rect` is the size of the screen.

    The `channels` variable holds a dictionary of known sound channels for the sound mixer.

    The `fullscreen` variable determines if we run the game full screen.

    The `state` variable is the current game state.

    Each of `game_edit`, `game_play`, `game_menu`, and `game_ended`
    represent each unique game loop (and requisite `state`) the game
    engine must loop.
    """

    screen: pg.Surface
    screen_rect: pg.Rect
    channels: dict
    fullscreen: bool
    state: GameState
    game_edit: "GameLoop" = field(init=False, default=None)
    game_play: "GameLoop" = field(init=False, default=None)
    game_menu: "GameLoop" = field(init=False, default=None)
    game_ended: "GameLoop" = field(init=False, default=None)

    @classmethod
    def create(cls, fullscreen=False):
        """
        Creates a TowerGame instance with sensible defaults.
        """

        channels = {
            "footsteps": None,
            "turrets": None,
            "score": None,
        }
        game = cls(
            state=GameState.starting,
            screen=None,
            channels=channels,
            fullscreen=fullscreen,
            # We define our screen rectable to be proportional to the
            # number of tiles and the defined height and width of the
            # tiles we are using.
            screen_rect=SCREENRECT,
        )
        game.init()
        return game

    def set_state(self, next_state: GameState):
        """
        Transitions the game state from one state to another.
        """
        log.debug(
            "Changing Game State", current_state=self.state, next_state=next_state
        )
        self.state = next_state

    def assert_state_is(self, *expected_states: GameState):
        """
        Asserts that the game engine is one of `expected_states`. If that assertions fails, raise `StateError`.
        """
        if not self.state in expected_states:
            raise StateError(
                f"Expected the game state to be one of {expected_states} not {self.state}"
            )

    def loop(self):
        """
        The main game loop that calls out to sub-loops depending on the game state.
        """
        # This is really the most important part of the state
        # machine. Depending on the value of `self.state`, the engine
        # switches to different parts of the game.
        while self.state != GameState.quitting:
            if self.state == GameState.main_menu:
                self.game_menu.loop()
            elif self.state == GameState.map_editing:
                self.game_edit.create_blank_level()
                self.game_edit.loop()
            elif self.state == GameState.game_playing:
                # Attempt to open a level -- by asking the player to
                # select a map with the open dialog -- and if that
                # succeeds, we enter the game play loop. If the player
                # exits, cancels or somehow chooses a level that is
                # not valid, we keep looping.
                if self.game_play.try_open_level():
                    self.game_play.loop()
            elif self.state == GameState.game_ended:
                self.game_ended.loop()
            else:
                assert False, f"Unknown game loop state {self.state}"
        self.quit()

    def quit(self):
        """
        Quits pygame and exits.
        """
        pg.quit()

    def start_game(self):
        """
        Starts the game engine. This is only meant to be called
        once, by whatever entrypoint is used to start the game, and only after the game is initialized.
        """
        self.assert_state_is(GameState.initialized)
        self.set_state(GameState.main_menu)
        self.loop()

    def init(self):
        """
        Initializes the game and configures pygame's SDL engine,
        the sound mixer, loads the images and creates the game state
        loops.
        """
        self.assert_state_is(GameState.starting)
        # Initialize and configure the display and mode for the game
        pg.init()
        # Configures fullscreen or windowed, the color depth (32 bits) and create the screen surface
        window_style = pg.FULLSCREEN if self.fullscreen else 0
        bit_depth = pg.display.mode_ok(self.screen_rect.size, window_style, 32)
        self.screen = pg.display.set_mode(
            self.screen_rect.size, window_style, bit_depth
        )
        # Load the image tiles into the module-level dictionary `IMAGE_SPRITES`
        for sprite_index, sprite_name in SPRITES.items():
            img = import_image(sprite_name)
            # Generate flipped versions of the sprites we load. We
            # want them flipped along the x and/or y-axis.
            for flipped_x in (True, False):
                for flipped_y in (True, False):
                    new_img = pg.transform.flip(img, flip_x=flipped_x, flip_y=flipped_y)
                    IMAGE_SPRITES[(flipped_x, flipped_y, sprite_index)] = new_img

        # Configure the sound mixer.
        pg.mixer.pre_init(
            frequency=44100,
            size=32,
            # N.B.: 2 here means stereo, not the number of channels to use in the mixer
            channels=2,
            buffer=512,
        )
        if pg.mixer.get_init() is None:
            pg.mixer = None
        else:
            # Load the sounds
            for sound_key, sound_name in SOUNDS.items():
                sound = import_sound(sound_name)
                SOUNDS[sound_key] = sound

            # Map the channels and channel names to a dedicated
            # `Channel` object sourced from pygame's sound mixer.
            for channel_id, channel_name in enumerate(self.channels):
                self.channels[channel_name] = pg.mixer.Channel(channel_id)
                # Configure the volume here.
                self.channels[channel_name].set_volume(1.0)
        # Load the font engine.
        pg.font.init()
        # Create the game loop state classes
        self.game_menu = GameMenu.create_with_level(self, level_name="demo.json")
        self.game_edit = GameEdit.create(self)
        self.game_play = GameEdit.create(self)
        self.game_ended = GameEnded.create(self)
        self.set_state(GameState.initialized)


@dataclass
class GameLoop:
    """
    Base Game Loop class used by the main TowerGame engine to
    dispatch game states to specialized game loops that inherit from
    this class.

    Takes the source game as its only input.
    """

    game: TowerGame

    @classmethod
    def create(cls, game):
        """
        Create an instance of this game loop with common defaults.
        """
        return cls(game=game)

    @property
    def mouse_position(self):
        return pg.mouse.get_pos()

    def loop(self):
        while self.state != GameState.quitting:
            self.handle_events()

    def handle_events(self):
        """
        Sample event handler that ensures quit events and normal
        event loop processing takes place. Without this, the game will
        hang, and repaints by the operating system will not happen,
        causing the game window to hang.
        """
        for event in pg.event.get():
            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                if self.state == GameState.main_menu:
                    self.set_state(GameState.quitting)
                else:
                    self.set_state(GameState.main_menu)
            if event.type == pg.QUIT:
                self.set_state(GameState.quitting)
            # Delegate the event to a sub-event handler `handle_event`
            self.handle_event(event)

    def handle_event(self, event):
        """
        Handles a singular event, `event`.
        """

    # Convenient shortcuts.
    def set_state(self, new_state):
        self.game.set_state(new_state)

    @property
    def screen(self):
        return self.game.screen

    @property
    def state(self):
        return self.game.state


@dataclass
class MenuGroup:

    """
    Menu Group UI class that keeps track of a selection of `Text` sprites.

    The menu group remembers the order in they were added in using a list called `items`.

    The position on the screen is determined by `which_position`, and
    the currently selected and not selected items are tracked with
    `selected_color` and `not_selected_color`.

    The selected item's index in the list is stored in `selected`.
    """

    render_position: Vector = field(default_factory=lambda: Vector(0, 0))
    selected_color: str = "sienna2"
    not_selected_color: str = "seashell2"
    selected: Optional[int] = 0
    items: List[Text] = field(default_factory=list)

    def set_selected(self, index):
        """
        Sets the selected item to `index`. All menu group items
        are re-rendered and their selected colors changed to match the
        new index.
        """
        for idx, menu_item in enumerate(self.items):
            if idx == index:
                menu_item.color = self.selected_color
                self.selected = idx
            else:
                menu_item.color = self.not_selected_color
            menu_item.render_text()

    def move(self, direction):
        """
        Moves the selection in `direction`, which is either a
        positive or negative number, indicating down or up,
        respectively.
        """
        if self.selected is None:
            self.selected = 0
        self.selected += direction
        self.selected %= len(self.items)
        self.set_selected(self.selected)

    def forward(self):
        """
        Moves the selected menu item forward one position
        """
        self.move(1)

    def backward(self):
        """
        Moves the selected menu item backward one position
        """
        self.move(-1)

    def add_menu_item(self, *menu_items):
        """
        Adds `menu_items` to the end of the menu items list.
        """
        self.items.extend(menu_items)

    def get_menu_item_position(self):
        """
        Calculates a menu item's *center* position on the screen,
        taking into account all the other menu items' font sizes and
        line height spacing.
        """
        offset = Vector(
            0,
            sum(
                menu_item.font.get_height() + menu_item.font.get_linesize()
                for menu_item in self.items
            ),
        )
        return self.render_position + offset

    def clear(self):
        self.items.clear()

    def add(self, text, size, action):
        sprite = Text(
            groups=[],
            color=self.not_selected_color,
            text=text,
            size=size,
            action=action,
        )
        self.add_menu_item(sprite)
        v = self.get_menu_item_position()
        sprite.move(v)
        # Set the selected item to the top-most item.
        self.move(0)

    def execute(self):
        """
        Executes the action associated with the selected menu
        item. Requires that a callable is associated with the menu
        item's `action`.
        """
        assert self.selected is not None, "No menu item is selected"
        menu = self.items[self.selected]
        assert callable(
            menu.action
        ), f"Menu item {menu} does not have a callable action"
        menu.action()


@dataclass
class GameMenu(GameLoop):

    """
    Main Menu loop for the game.

    The `menu_group` attribute holds the menu group configuration the
    loop renders to the screen.
    """

    background: pg.Surface
    menu_group: MenuGroup

    @classmethod
    def create_with_level(cls, game, level_name):
        """
        Sneaky hack that renders a level just once and then uses
        its surface as the backdrop for the menu screen.
        """
        g = GameEdit.create(game)
        g.open_level(import_level(level_name), show_hud=False)
        g.draw_background()
        g.draw()
        return cls.create(game=game, background=g.screen.copy())

    @classmethod
    def create(cls, game, background):
        return cls(game=game, background=background, menu_group=MenuGroup())

    def handle_event(self, event):
        # Pass up/down/return events to the menu group
        if event.type == pg.KEYDOWN:
            if event.key == pg.K_UP:
                self.menu_group.backward()
            if event.key == pg.K_DOWN:
                self.menu_group.forward()
            if event.key == pg.K_RETURN:
                self.menu_group.execute()

    def make_swirling_text(self, text, color, size, start, stop):
        """
        Generates a `Text` sprite with scrolling, swirling text
        """
        path = zip(
            [
                lerp(start, stop, r)
                for r in [cube(t) for t in interpolate((0, 1), 360 + 1)]
            ],
            chain(range(360 + 1)),
        )
        text = self.make_text(text, color, size, path)
        return text

    def make_text(self, text, color, size, path=None, position=(0, 0), **kwargs):
        """
        Shortcut that creates a `Text` sprite.
        """
        text = Text(
            text=text,
            path=path,
            groups=[],
            size=size,
            color=color,
            **kwargs,
        )
        text.move(position)
        return text

    def action_play(self):
        """
        Menu action for the Play menu item.
        """
        self.set_state(GameState.game_playing)

    def action_edit(self):
        """
        Menu action for the Edit menu item.
        """
        self.set_state(GameState.map_editing)

    def action_quit(self):
        """
        Menu action for the Quit menu item.
        """
        self.set_state(GameState.quitting)

    def loop(self):
        clock = pg.time.Clock()
        # Fill the screen with black color.
        self.screen.fill((0, 0, 0), self.game.screen_rect)
        # This determines where the menu is placed.
        menu_base_position = Vector(self.game.screen_rect.center)
        self.menu_group.render_position = menu_base_position
        self.menu_group.clear()
        self.menu_group.add(
            text="Play",
            size=50,
            action=self.action_play,
        )
        self.menu_group.add(
            text="Edit",
            size=30,
            action=self.action_edit,
        )
        self.menu_group.add(
            text="Quit",
            size=30,
            action=self.action_quit,
        )
        start = Vector(-100, 0)
        stop = menu_base_position + Vector(0, -300)
        menu = pg.sprite.Group(
            Sprite.create_from_sprite("game_logo", groups=[], position=stop),
            self.make_swirling_text(
                text="Make your own",
                color="steelblue",
                size=50,
                start=start,
                stop=stop + Vector(0, -150),
            ),
            self.make_swirling_text(
                text="PRESS ENTER TO PLAY",
                color="red1",
                size=50,
                start=start,
                stop=stop + Vector(0, 150),
            ),
            *self.menu_group.items,
        )
        # Create a semi-transparent backdrop for the menu
        r = self.screen.get_rect()
        r.width = r.width // 3
        r.move(150, 0)
        bg = create_surface(size=r.size)
        bg.fill((0, 0, 0, 128))

        # Loop as long as our game state remains main menu. When an
        # action is triggered by the player, the state is changed,
        # breaking the loop
        while self.state == GameState.main_menu:
            self.screen.blit(self.background, (0, 0))
            # Draw a blended black rectangle to make the menu and text
            # easier to read
            self.screen.blit(bg, r.topright)
            menu.draw(self.screen)
            self.handle_events()
            menu.update()
            pg.display.flip()
            pg.display.set_caption(f"FPS {round(clock.get_fps())}")
            clock.tick(DESIRED_FPS)
        log.info("Exited menu")
        menu.empty()


@dataclass
class GameEnded(GameLoop):
    """
    Game ended loop called when a win or loss condition is met.
    """

    def handle_event(self, event):
        if event.type == pg.KEYDOWN:
            if event.key in (pg.K_RETURN, pg.K_ESCAPE):
                self.set_state(GameState.main_menu)

    def make_falling_text(self, text, color, size, groups, stop):
        """
        Creates a simple text effect that drops down
        """

        start = Vector(stop[0], -100)
        path = zip(
            interpolate(
                (
                    start,
                    stop,
                ),
                150,
            ),
            repeat(0),
        )
        text = Text(
            text=text,
            path=path,
            groups=groups,
            size=size,
            color=color,
        )
        return text

    def loop(self):
        clock = pg.time.Clock()
        self.screen.fill((0, 0, 0), self.game.screen_rect)
        message = pg.sprite.Group()
        self.make_falling_text(
            text="Game Over!",
            color="red1",
            size=150,
            groups=[message],
            stop=self.game.screen_rect.center,
        )
        bg = create_surface()
        bg.fill((0, 0, 0), self.game.screen_rect)
        while self.state == GameState.game_ended:
            self.screen.blit(bg, (0, 0))
            self.handle_events()
            message.update()
            message.draw(self.screen)
            pg.display.flip()
            pg.display.set_caption(f"FPS {round(clock.get_fps())}")
            clock.tick(DESIRED_FPS)


@dataclass
class GameEdit(GameLoop):
    """
    Loop for the Game Editing _and_ Game Playing modes

    The `background` is where the tiled background map is blitted
    to. The `level` holds the grid of tiles, although it may be None
    to start with.

    The `debug` dict holds debug flags for hiding or showing debug
    overlays on the screen.

    The `layers` attribute is a special type of pygame sprite group
    called `pg.sprite.LayeredUpdates`. It allows for ordered
    rendering, as in the Painter's Algorithm, and to query and
    interact with all or parts of the sprites.

    The `sprite_manager` is the instance responsible for picking and
    placing game elements like turrets, enemies, background tiles and
    shrubs. The majority of logic around sprite creation is handled by
    it.

    The `mode` is the type of game mode to use when the game state is
    `GameState.game_playing`.

    The `_last_selected_sprite` tracks the last selected item internally.
    """

    background: pg.Surface
    level: Optional[list]
    debug: dict
    layers: pg.sprite.LayeredUpdates
    sprite_manager: SpriteManager
    mode: GameMode
    # Internal states
    _last_selected_sprite: Optional[int] = field(init=False, default=None)

    @classmethod
    def create(cls, game):
        layers = pg.sprite.LayeredUpdates()
        return cls(
            game=game,
            background=create_surface(),
            level=None,
            debug={
                "show_path_finding": False,
                "show_collision_mask": False,
                "show_grid_rect": False,
            },
            mode=GameModeElimination.create(),
            layers=layers,
            sprite_manager=SpriteManager(
                sprites=pg.sprite.LayeredUpdates(),
                indices=None,
                layers=layers,
                channels=game.channels,
            ),
        )

    def create_blank_level(self):
        """
        Creates a blank level with a uniform tile selection.
        """
        # This "recycles" the game loading/saving mechanism to create
        # a tile map with the structure the
        # `create_background_tile_map` would ordinarily expect.
        self.load_level(create_tile_map({"index": "blank", "orientation": 0}), [])

    def load_level(self, background, shrubs, show_hud: bool = True):
        """
        Given a valid tile map of `background` tiles, and a list
        of `shrubs`, load them into the game and reset the game.
        """
        self.layers.empty()
        self.level = create_background_tile_map(background)
        self.draw_background()
        self.mode.reset()
        if show_hud:
            self.make_hud()
        for shrub in shrubs:
            # Use the create/select features of the sprite manager to place the shrubs.
            self.sprite_manager.select_sprites(
                self.sprite_manager.create_shrub(
                    position=shrub["position"],
                    orientation=shrub["orientation"],
                    index=shrub["index"],
                )
            )
            self.sprite_manager.place(shrub["position"])
            self.sprite_manager.empty()

    def draw_background(self):
        """
        Loop over each tile position and draw the background tile to the background surface.

        This is done exactly once: the backgrounds are static and does
        not otherwise update once the game is started.
        """
        # Recall that the IMAGE_SPRITES dictionary uses a tuple of
        # (flipped_x, flipped_y, name) to determine the sprite to
        # pick.
        self.background.blit(IMAGE_SPRITES[(False, False, "backdrop")], (0, 0))
        for (y, x, dx, dy) in tile_positions():
            background_tile = self.level[y][x]
            self.background.blit(background_tile.image, (dx, dy))

    def make_hud(self):
        """
        Creates the HUD text
        """
        # We can't draw a hud if we're not playing a game. This is
        # rather obvious, but as we transition to (say) the game over
        # or level editor screen, we no longer want to render the hud.
        if self.state != GameState.game_playing:
            return
        hud = HUDText(
            text="",
            mode=self.mode,
            groups=[self.layers],
            position=self.game.screen_rect.midtop + Vector(0, 40),
            size=40,
            color="orangered",
        )
        hud.update()
        return hud

    def draw(self):
        # Repaint background
        self.screen.blit(self.background, (0, 0))
        # Instruct all sprites to update
        self.layers.update()
        self.layers.draw(self.screen)

    def loop(self):
        """
        Combined game loop for both map editing and game playing.
        """
        clock = pg.time.Clock()
        self.draw_background()
        while self.state in (GameState.map_editing, GameState.game_playing):
            mouse_pos = pg.mouse.get_pos()
            m_x, m_y = get_tile_position(mouse_pos)
            self.handle_events()
            self.draw()
            # Handle collision
            self.handle_collision()
            if self.state == GameState.game_playing:
                # Check for victory (or loss) if we are in GameState.game_playing mode
                if self.mode.check_win_or_loss():
                    self.set_state(GameState.game_ended)
                # Maybe spawn new enemies.
                enemies_to_spawn = self.mode.next()
                for _ in range(enemies_to_spawn):
                    self.spawn_enemy()
            # Debug flag to show the grid
            if self.debug["show_grid_rect"]:
                pg.draw.rect(
                    self.screen, "darkgoldenrod4", get_grid_rect(m_x, m_y), width=2
                )
            # Debug flag to show the path finding for the enemies.
            if self.debug["show_path_finding"]:
                paths = update_path_finding(self.level)
                for (idx, (start_tile, stop_tile)) in enumerate(paths):
                    path = get_directions(start_tile, [stop_tile.position])
                    for v1, v2 in path:
                        pg.draw.line(
                            self.screen,
                            PATH_COLORS[idx % len(PATH_COLORS)],
                            v1,
                            v2,
                            width=2,
                        )
            # Debug FPS and Mouse coordinates
            pg.display.set_caption(
                f"FPS {round(clock.get_fps())} Mouse: {mouse_pos} Grid: {(m_x,m_y)}"
            )
            pg.display.flip()
            clock.tick(DESIRED_FPS)
        self.layers.empty()

    def handle_collision(self):
        """
        Handles collision detection between enemies, projectiles, and turret sights
        """
        enemies = self.layers.get_sprites_from_layer(Layer.enemy)
        turret_sights = self.layers.get_sprites_from_layer(Layer.turret_sights)
        projectiles = self.layers.get_sprites_from_layer(Layer.projectile)
        # A set of things that have collided. By default it's empty.
        collided = set()
        # check collision between turret sights and enemies
        for enemy, turret_sights in collide_mask(enemies, turret_sights):
            # `collide_mask` checks, using per-pixel masking, if two
            # groups of sprites have any intersections or overlaps
            # that indicate collision.  If there are, then we get back
            # an `enemy` and one-or-more `turret_sights` the enemy is
            # in the sights of.
            for turret_sight in turret_sights:
                turret = turret_sight.turret
                collided.add(enemy)
                # If we can shoot the turret _and_ if it's not
                # currently selected (but not yet placed), then we can
                # play the turret sound effect and create a projectile.
                if turret.shoot() and turret not in self.sprite_manager.sprites:
                    turret.play()
                    self.sprite_manager.create_projectile(
                        turret,
                        enemy,
                    )
        # Debug flag to show collision masking between sprites.
        if self.debug["show_collision_mask"]:
            # Slow; should be done once
            debug_mask = create_surface()
            debug_mask.fill((0, 0, 0, 0))
            for sprite in chain(turret_sights, enemies):
                set_color = (255, 0, 0)
                if sprite not in collided:
                    set_color = (0, 255, 0)
                if sprite.layer != Layer.enemy:
                    continue
                sprite.mask.to_surface(
                    surface=debug_mask,
                    setcolor=set_color,
                    unsetcolor=None,
                    dest=sprite.rect,
                )
            self.screen.blit(debug_mask, (0, 0))
        # Check for collision between enemies and projectiles
        for enemy, projectiles in collide_mask(enemies, projectiles):
            # The enemy is already in a dying animation state; no need
            # to do anything, as it's already dead or dying.
            if enemy.animation_state == AnimationState.dying:
                continue
            # If there's a collision, kill the enemy. You could add a
            # hitpoint counter to the Enemy class here and subtract
            # a fixed amount if you want the enemies to be more
            # durable.
            enemy.animation_state = AnimationState.dying
            # Update our kill counter
            self.mode.killed += 1
            # ... and don't forget to destroy the projectiles, unless
            # of course you want them to pierce enemies and keep
            # flying!
            for projectile in projectiles:
                projectile.animation_state = AnimationState.exploding
        # Loop over enemies that've stopped moving. Stopped enemies
        # have reached the end of their path, which in our case is the
        # escape tile.
        for enemy in enemies:
            if enemy.state == SpriteState.stopped:
                self.mode.escaped += 1
                # Kill the enemy to remove them from the game.
                enemy.kill()
                channel = self.game.channels["score"]
                if channel is not None:
                    channel.play(SOUNDS["beep"])

    def select_sprite(self, index: Optional[int]):
        """
        Given an integer index (intended to correspond to the
        digit keys on the keyboard) create (and select) a sprite.

        Only some are available in `GameState.game_playing`; the rest
        is intended for the map editor.
        """
        # Skip any index that's not in the 0-9 digit range.
        if index not in range(0, 9):
            return
        self.sprite_manager.kill()
        if self._last_selected_sprite != index:
            self.sprite_manager.reset()
        self._last_selected_sprite = index
        self.debug["show_grid_rect"] = False
        if index == KEY_TURRET:
            self.sprite_manager.select_sprites(
                self.sprite_manager.create_turret(
                    position=self.mouse_position,
                )
            )
        if index == KEY_BACKGROUND:
            self.debug["show_grid_rect"] = True
            self.sprite_manager.select_sprites(
                self.sprite_manager.create_background(position=self.mouse_position),
                self.mouse_position,
            )
        if index == KEY_SHRUB:
            self.sprite_manager.select_sprites(
                self.sprite_manager.create_shrub(position=self.mouse_position),
                self.mouse_position,
            )
        if index == KEY_ENEMY:
            self.spawn_enemy()

    def spawn_enemy(self):
        """
        Updates the path finding and spawns a enemy.
        """
        # NOTE: This could easily be done just once before the game is
        # started, as the path finding is not going to change in game
        # play mode.
        paths = update_path_finding(self.level)
        if paths:
            # Pick a random path combination.
            start_tile, stop_tile = random.choice(paths)
            # Generate a path for the enemy to travel.
            path = make_enemy_path(start_tile, [stop_tile.position])
            # Give it a dummy position of (0,0) as enemies'll snap to
            # the first path position on update.
            self.sprite_manager.create_enemy(position=(0, 0), path=path)
        else:
            # Place an enemy at the mouse cursor if we're in map editing mode.
            if self.state == GameState.map_editing:
                self.sprite_manager.create_enemy(
                    position=self.mouse_position, path=None
                )

    def handle_event(self, event):
        # Mouse Events
        if event.type == pg.MOUSEWHEEL:
            if self.sprite_manager.selected:
                self.sprite_manager.cycle_index()
        if event.type == pg.MOUSEMOTION:
            self.sprite_manager.move(self.mouse_position)
        if event.type == pg.MOUSEBUTTONDOWN and event.button in (
            MOUSE_LEFT,
            MOUSE_RIGHT,
        ):
            if self.sprite_manager.selected:
                if event.button == MOUSE_LEFT:
                    # If we press the LMB with at least one selected
                    # sprite, our intent is to place them on the
                    # map. However, if the layer of the sprite in the
                    # selected sprites list is Background, then we
                    # must instead insert them into the level tile map
                    # (as the background is not really treated as a
                    # sprite in the normal sense)
                    for sprite in self.sprite_manager.sprites:
                        if sprite.layer == Layer.background:
                            # Important: we use the center coordinates
                            # for sprites almost everywhere, but the
                            # tile grid uses the top-left coordinates
                            # instead.
                            gx, gy = get_tile_position(sprite.rect.topleft)
                            self.level[gy][gx] = sprite
                        else:
                            # If it's not a background sprite, just
                            # place the sprite with the sprite manager
                            # at the mouse position
                            self.sprite_manager.place(self.mouse_position)
                    self.sprite_manager.empty()
                    # If we're editing the map, we re-select the last
                    # sprite to cut down on tedium when building a
                    # map.
                    if self.state == GameState.map_editing:
                        self.select_sprite(self._last_selected_sprite)
                elif event.button == MOUSE_RIGHT:
                    # Delete selected sprites if we right-click ("clear selected item")
                    self.sprite_manager.kill()
            else:
                if event.button == MOUSE_RIGHT and self.state == GameState.map_editing:
                    # In game editing mode only, we can also remove
                    # sprites from the map with a right click _if_ we
                    # don't have a selected sprite _and_ the layer is
                    # not the background layer.
                    found_sprites = self.layers.get_sprites_at(self.mouse_position)
                    for found_sprite in found_sprites:
                        if found_sprite.layer != Layer.background:
                            found_sprite.kill()
        # Keyboard Events
        if event.type == pg.KEYDOWN:
            if event.key in (pg.K_q, pg.K_e):
                # Determine the _relative_ orientation we want to
                # rotate based on the key
                if event.key == pg.K_q:
                    orientation = 90
                else:
                    orientation = -90
                if self.sprite_manager.selected:
                    self.sprite_manager.increment_orientation(orientation)
            # Debug Keys
            elif event.key == pg.K_F1:
                self.debug["show_path_finding"] = not self.debug["show_path_finding"]
            elif event.key == pg.K_F2:
                self.debug["show_collision_mask"] = not self.debug[
                    "show_collision_mask"
                ]
            elif self.state == GameState.map_editing:
                if event.key == pg.K_F9:
                    self.try_open_level()
                elif event.key == pg.K_F5:
                    self.try_save_level()
                # Map the number range (pg.K_1..pg.K_9) to 0-indexed
                # by subtracting our current key from pg.K_1. Use that
                # value to try and select something
                index = event.key - pg.K_1
                self.select_sprite(index)
            elif self.state == GameState.game_playing:
                if event.key == pg.K_1:
                    if self.mode.can_place_turret(
                        len(self.layers.get_sprites_from_layer(Layer.turret))
                    ):
                        self.select_sprite(KEY_TURRET)

    def open_level(self, file_obj, show_hud: bool = True):
        data = json.loads(file_obj.read())
        self.load_level(
            background=data["background"], shrubs=data["shrubs"], show_hud=show_hud
        )

    def try_open_level(self):
        """
        Tries to open a level with the open dialog. If the user cancels out, do nothing.
        """
        with open_dialog() as open_file:
            if open_file is not None:
                self.open_level(open_file)
                return True
            else:
                self.set_state(GameState.main_menu)
                return False

    def try_save_level(self):
        """
        Tries to save a level with the save dialog used to source the filepath.
        """
        with save_dialog() as save_file:
            if save_file is not None:
                save_level(
                    self.level,
                    self.layers.get_sprites_from_layer(Layer.shrub.value),
                    save_file,
                )


def start_game():
    """
    Default entrypoint for the game
    """
    game = TowerGame.create()
    game.start_game()


@contextmanager
def open_dialog(title="Open file...", filetypes=(("Tower Defense Levels", "*.json"),)):
    """
    Context manager that yields the opened file, which could be
    None if the user exits it without selecting. If there is a file it
    is closed when the context manager exits.
    """
    try:
        f = tkinter.filedialog.askopenfile(title=title, filetypes=filetypes)
        yield f
    finally:
        if f is not None:
            f.close()


@contextmanager
def save_dialog(title="Save file...", filetypes=(("Tower Defense Levels", "*.json"),)):
    f = tkinter.filedialog.asksaveasfile(title=title, filetypes=filetypes)
    try:
        yield f
    finally:
        if f is not None:
            f.close()
