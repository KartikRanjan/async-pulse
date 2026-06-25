"""Model registry for Alembic autogenerate.

Import every model here so ``Base.metadata`` is aware of all tables.
"""

from src.db.base import Base
from src.modules.auth.models import SessionModel
from src.modules.users.models import UserModel

# All models must be imported above this line.
target_metadata = Base.metadata

__all__ = ["SessionModel", "UserModel", "target_metadata"]
