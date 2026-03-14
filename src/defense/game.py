"""Main game class."""

import sys
import pygame
import pygame_gui

from .menu import DefenseMenu


TITLE = "Defense"
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
BACKGROUND_COLOR = (211, 211, 211)  # light gray


class DefenseGame:
    def __init__(self):
        pygame.init()
        self._screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(TITLE)
        self._clock = pygame.time.Clock()
        self._manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT))
        self._menu = DefenseMenu(self._manager, WINDOW_WIDTH)

    def run(self):
        running = True
        while running:
            time_delta = self._clock.tick(60) / 1000.0  # seconds since last frame
            running = self.handle_events()
            self._manager.update(time_delta)
            self._screen.fill(BACKGROUND_COLOR)
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
