"""Main game class."""

import pygame
import pygame_gui

from .colors import CELL_COLOR, GRID_BORDER_COLOR
from .menu import DefenseMenu
from .sprites import Pilgrim

from .constants import MENU_BAR_HEIGHT

TITLE = "Defense"
CELL_SIZE = 16    # interior pixel size of each grid cell
BORDER_WIDTH = 2  # dark border visible between adjacent cells
CELL_STRIDE = CELL_SIZE + BORDER_WIDTH  # distance between cell origins (18)
GRID_COLS = 50
GRID_ROWS = 40

WINDOW_WIDTH = CELL_STRIDE * GRID_COLS                    # 900
WINDOW_HEIGHT = MENU_BAR_HEIGHT + CELL_STRIDE * GRID_ROWS # 750

_CELL_OFFSET = BORDER_WIDTH // 2  # 1px leading border on each side


class DefenseGame:
    def __init__(self):
        pygame.init()
        self._screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(TITLE)
        self._clock = pygame.time.Clock()
        self._manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT))
        self._menu = DefenseMenu(self._manager, WINDOW_WIDTH)
        self.travelers = pygame.sprite.Group()
        self.travelers.add(Pilgrim(0, MENU_BAR_HEIGHT))

    def run(self):
        running = True
        while running:
            time_delta = self._clock.tick(60) / 1000.0  # seconds since last frame
            running = self.handle_events()
            self._manager.update(time_delta)
            self._draw_grid()
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

    def _draw_grid(self):
        # Fill the entire grid area with the border color so gaps between
        # cells show through as a 2-pixel-wide dark border.
        self._screen.fill(
            GRID_BORDER_COLOR,
            pygame.Rect(0, MENU_BAR_HEIGHT, WINDOW_WIDTH, CELL_STRIDE * GRID_ROWS),
        )
        for row in range(GRID_ROWS):
            y = MENU_BAR_HEIGHT + row * CELL_STRIDE + _CELL_OFFSET
            for col in range(GRID_COLS):
                x = col * CELL_STRIDE + _CELL_OFFSET
                pygame.draw.rect(
                    self._screen,
                    CELL_COLOR,
                    pygame.Rect(x, y, CELL_SIZE, CELL_SIZE),
                )
