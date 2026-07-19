"""Minimal dependency-injection container.

Design rationale: the project needs exactly three things from DI: swap implementations at
the seams (tests inject fakes for clock, model client, browser session), share singletons
(settings, logger config), and fail loudly on wiring mistakes. A hand-rolled ~100-line
container delivers that; a framework dependency would not pay for itself. Resolution is
type-keyed and explicit: no autowiring, no decorators, no import-time magic.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from website_agent.core.errors import DependencyError

T = TypeVar("T")

Provider = Callable[["Container"], Any]


@dataclass
class _Registration:
    provider: Provider
    singleton: bool
    instance: Any = None
    materialized: bool = False


class Container:
    """Type-keyed registry of providers with singleton caching and override support."""

    def __init__(self) -> None:
        self._registrations: dict[type[Any], _Registration] = {}
        self._overrides: dict[type[Any], Any] = {}
        self._resolving: list[type[Any]] = []

    def register(
        self,
        interface: type[T],
        provider: Callable[[Container], T],
        *,
        singleton: bool = True,
    ) -> None:
        """Register ``provider`` as the source for ``interface``.

        Args:
            interface: the type used as the lookup key (a Protocol, ABC, or class).
            provider: factory receiving the container, so it can resolve its own deps.
            singleton: cache the first instance (default) or build fresh per resolve.

        Re-registration replaces the previous provider and drops any cached instance;
        this keeps application wiring declarative (last registration wins) while tests
        prefer :meth:`overriding` for scoped substitution.
        """
        self._registrations[interface] = _Registration(provider=provider, singleton=singleton)

    def register_instance(self, interface: type[T], instance: T) -> None:
        """Register an already-built object as the singleton for ``interface``."""
        self._registrations[interface] = _Registration(
            provider=lambda _: instance, singleton=True, instance=instance, materialized=True
        )

    def resolve(self, interface: type[T]) -> T:
        """Return the instance bound to ``interface``.

        Raises:
            DependencyError: if nothing is registered, or providers form a cycle.
        """
        if interface in self._overrides:
            return cast(T, self._overrides[interface])

        registration = self._registrations.get(interface)
        if registration is None:
            raise DependencyError(
                "no provider registered",
                context={"interface": interface.__qualname__},
            )

        if registration.singleton and registration.materialized:
            return cast(T, registration.instance)

        if interface in self._resolving:
            cycle = " -> ".join(t.__qualname__ for t in [*self._resolving, interface])
            raise DependencyError("dependency cycle detected", context={"cycle": cycle})

        self._resolving.append(interface)
        try:
            instance = registration.provider(self)
        finally:
            self._resolving.pop()

        if registration.singleton:
            registration.instance = instance
            registration.materialized = True
        return cast(T, instance)

    def is_registered(self, interface: type[Any]) -> bool:
        """Whether ``interface`` has a provider or an active override."""
        return interface in self._registrations or interface in self._overrides

    @contextmanager
    def overriding(self, interface: type[T], instance: T) -> Iterator[None]:
        """Temporarily force ``interface`` to resolve to ``instance``.

        Scoped and re-entrant safe for distinct interfaces; the primary seam for tests.
        """
        if interface in self._overrides:
            raise DependencyError(
                "interface already overridden",
                context={"interface": interface.__qualname__},
            )
        self._overrides[interface] = instance
        try:
            yield
        finally:
            del self._overrides[interface]
