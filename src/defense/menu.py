"""Defense game menu."""

import pygame
import pygame_gui

from .constants import MENU_BAR_HEIGHT

MENU_BUTTON_WIDTH = 60


class DefenseMenu:
    def __init__(self, manager, window_width):
        self._menu_bar = pygame_gui.elements.UIPanel(
            relative_rect=pygame.Rect(0, 0, window_width, MENU_BAR_HEIGHT),
            manager=manager,
        )
        self._exit_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(0, 0, MENU_BUTTON_WIDTH, MENU_BAR_HEIGHT),
            text="Exit",
            manager=manager,
            container=self._menu_bar,
        )

    def handles_exit(self, event):
        """Return True if the event is an exit request from the menu."""
        return (
            event.type == pygame_gui.UI_BUTTON_PRESSED
            and event.ui_element is self._exit_button
        )
