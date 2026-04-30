"""
Re-export auth dependencies for use in routers.

Routers import from here:
    from .dependencies import require_manager, current_user_id
"""

from .auth import (
    get_current_user,
    require_manager,
    require_admin,
    current_user_id,
)

__all__ = [
    "get_current_user",
    "require_manager",
    "require_admin",
    "current_user_id",
]
