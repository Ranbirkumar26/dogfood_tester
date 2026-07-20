"""FastAPI REST server over the AgentService (Phase 14)."""

from website_agent.api.app import create_app
from website_agent.api.service import AgentService

__all__ = ["AgentService", "create_app"]
