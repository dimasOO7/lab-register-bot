from src.handlers.common import router as common_router
from src.handlers.profile import router as profile_router
from src.handlers.lessons import router as lessons_router
from src.handlers.queue import router as queue_router

__all__ = ["common_router", "profile_router", "lessons_router", "queue_router"]
