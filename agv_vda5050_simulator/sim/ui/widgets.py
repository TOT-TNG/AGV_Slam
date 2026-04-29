from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import pygame


@dataclass
class Button:
    rect: pygame.Rect
    text: str
    callback: Callable[[], None]
    enabled: bool = True
    selected: bool = False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, *, rect: Optional[pygame.Rect] = None) -> None:
        draw_rect = rect or self.rect
        if not self.enabled:
            color = (92, 96, 104)
            border = (120, 120, 120)
        elif self.selected:
            color = (221, 153, 55)
            border = (255, 210, 90)
        else:
            color = (58, 112, 158)
            border = (96, 142, 180)
        pygame.draw.rect(surface, color, draw_rect, border_radius=6)
        pygame.draw.rect(surface, border, draw_rect, width=1, border_radius=6)
        label = font.render(self.text, True, (248, 250, 252))
        surface.blit(label, label.get_rect(center=draw_rect.center))

    def handle_click(self, pos: tuple[int, int]) -> None:
        if self.enabled and self.rect.collidepoint(pos):
            self.callback()
