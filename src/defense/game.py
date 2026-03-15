"""Main game class."""

import pygame
import pygame_gui

from .constants import MENU_BAR_HEIGHT
from .grid import WINDOW_WIDTH, WINDOW_HEIGHT, draw_grid
from .helpers import interpolate
from .menu import DefenseMenu
from .sprites import Pilgrim

TITLE = "Defense"
STEPS_PER_CELL = 30  # frames to travel one cell (2 cells/second at 60 FPS)


class DefenseGame:
    def __init__(self):
        pygame.init()
        self._screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(TITLE)
        self._clock = pygame.time.Clock()
        self._manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT))
        self._menu = DefenseMenu(self._manager, WINDOW_WIDTH)
        self.travelers = pygame.sprite.Group()
        self.travelers.add(Pilgrim(interpolate(Pilgrim.waypoints(), STEPS_PER_CELL)))

    def run(self):
        running = True
        while running:
            time_delta = self._clock.tick(60) / 1000.0  # seconds since last frame
            running = self.handle_events()
            self._manager.update(time_delta)
            self.travelers.update()
            draw_grid(self._screen)
            self.travelers.draw(self._screen)
            self._manager.draw_ui(self._screen)
            pygame.display.flip()

        pygame.quit()

    def handle_events(self):
        running = True
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif self._menu.handles_exit(event):
                running = False
            self._manager.process_events(event)
        return running
