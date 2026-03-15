"""Grid constants, coordinate conversion, and rendering for the Defense game."""

import pygame

from .colors import CELL_COLOR, GRID_BORDER_COLOR
from .constants import MENU_BAR_HEIGHT

CELL_SIZE = 20    # interior pixel size of each grid cell
BORDER_WIDTH = 2  # dark border visible between adjacent cells
CELL_STRIDE = CELL_SIZE + BORDER_WIDTH  # distance between cell origins
GRID_COLS = 40
GRID_ROWS = 32

WINDOW_WIDTH = CELL_STRIDE * GRID_COLS
WINDOW_HEIGHT = MENU_BAR_HEIGHT + CELL_STRIDE * GRID_ROWS

_CELL_OFFSET = BORDER_WIDTH // 2


def cell_to_pixel(col, row):
    """Return the top-left pixel position of the interior of grid cell (col, row)."""
    return (col * CELL_STRIDE + _CELL_OFFSET, MENU_BAR_HEIGHT + row * CELL_STRIDE + _CELL_OFFSET)


def draw_grid(screen):
    """Draw the grid onto screen."""
    screen.fill(
        GRID_BORDER_COLOR,
        pygame.Rect(0, MENU_BAR_HEIGHT, WINDOW_WIDTH, CELL_STRIDE * GRID_ROWS),
    )
    for row in range(GRID_ROWS):
        y = MENU_BAR_HEIGHT + row * CELL_STRIDE + _CELL_OFFSET
        for col in range(GRID_COLS):
            x = col * CELL_STRIDE + _CELL_OFFSET
            pygame.draw.rect(screen, CELL_COLOR, pygame.Rect(x, y, CELL_SIZE, CELL_SIZE))
