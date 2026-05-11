"""Central page router for decoupled page switching."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from PySide6.QtWidgets import QStackedWidget, QWidget


@dataclass(frozen=True)
class Route:
    """Describe a route entry for one page."""

    key: str
    title: str


class AppRouter:
    """Register and switch pages in a stacked widget."""

    def __init__(self, container: QStackedWidget) -> None:
        """Initialize router with target page container."""
        self._container = container
        self._index_map: Dict[str, int] = {}
        self._route_map: Dict[str, Route] = {}

    def register_page(self, route: Route, page: QWidget) -> None:
        """Register a page and cache route key to stacked index."""
        index = self._container.addWidget(page)
        self._index_map[route.key] = index
        self._route_map[route.key] = route

    def add_alias(self, route_key: str, target_route_key: str) -> None:
        """Map a new route key to an existing route index."""
        target_index = self._index_map.get(target_route_key)
        target_route = self._route_map.get(target_route_key)
        if target_index is None or target_route is None:
            return
        self._index_map[route_key] = target_index
        self._route_map[route_key] = Route(route_key, target_route.title)

    def switch_to(self, route_key: str) -> None:
        """Switch to a registered page by route key."""
        index = self._index_map.get(route_key)
        if index is None:
            return
        self._container.setCurrentIndex(index)

    def has_route(self, route_key: str) -> bool:
        """Return whether route key has been registered."""
        return route_key in self._index_map
