"""DI container: registration, singleton semantics, cycles, overrides."""

from __future__ import annotations

import pytest

from website_agent.core.di import Container
from website_agent.core.errors import DependencyError


class Service:
    def __init__(self, label: str = "svc") -> None:
        self.label = label


class Consumer:
    def __init__(self, service: Service) -> None:
        self.service = service


def test_resolve_unregistered_raises_with_interface_name() -> None:
    container = Container()
    with pytest.raises(DependencyError) as excinfo:
        container.resolve(Service)
    assert "Service" in str(excinfo.value)


def test_singleton_returns_same_instance() -> None:
    container = Container()
    container.register(Service, lambda c: Service())
    assert container.resolve(Service) is container.resolve(Service)


def test_factory_registration_builds_fresh_instances() -> None:
    container = Container()
    container.register(Service, lambda c: Service(), singleton=False)
    assert container.resolve(Service) is not container.resolve(Service)


def test_providers_resolve_their_own_dependencies() -> None:
    container = Container()
    container.register(Service, lambda c: Service("wired"))
    container.register(Consumer, lambda c: Consumer(c.resolve(Service)))
    assert container.resolve(Consumer).service.label == "wired"


def test_register_instance_and_is_registered() -> None:
    container = Container()
    instance = Service("pre-built")
    container.register_instance(Service, instance)
    assert container.is_registered(Service)
    assert not container.is_registered(Consumer)
    assert container.resolve(Service) is instance


def test_re_registration_replaces_and_drops_cache() -> None:
    container = Container()
    container.register(Service, lambda c: Service("first"))
    first = container.resolve(Service)
    container.register(Service, lambda c: Service("second"))
    second = container.resolve(Service)
    assert first.label == "first"
    assert second.label == "second"


def test_cycle_detection_reports_the_chain() -> None:
    container = Container()
    container.register(Service, lambda c: Service(c.resolve(Consumer).service.label))
    container.register(Consumer, lambda c: Consumer(c.resolve(Service)))
    with pytest.raises(DependencyError) as excinfo:
        container.resolve(Service)
    assert "cycle" in excinfo.value.message
    assert "Service" in str(excinfo.value.context["cycle"])


def test_failed_provider_leaves_container_usable() -> None:
    container = Container()
    calls = {"n": 0}

    def provider(c: Container) -> Service:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first construction fails")
        return Service("recovered")

    container.register(Service, provider)
    with pytest.raises(RuntimeError):
        container.resolve(Service)
    assert container.resolve(Service).label == "recovered"


def test_override_is_scoped_and_exclusive() -> None:
    container = Container()
    container.register(Service, lambda c: Service("real"))
    fake = Service("fake")
    with container.overriding(Service, fake):
        assert container.resolve(Service) is fake
        with pytest.raises(DependencyError):
            container.overriding(Service, Service("again")).__enter__()
    assert container.resolve(Service).label == "real"
