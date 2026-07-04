from app.api.agent_api import router as agent_router
from app.api.project_api import router as project_router
from app.api.search_api import router as search_router

__all__ = ["agent_router", "project_router", "search_router"]
