"""Model registry for Alembic autogenerate.

Import every model here so ``Base.metadata`` is aware of all tables.
"""

from src.db.base import Base
from src.modules.auth.models import (
    SessionModel,  # noqa: F401  # type: ignore[unused-import]  # populate Base.metadata
)
from src.modules.users.models import (
    UserModel,  # noqa: F401  # type: ignore[unused-import]  # populate Base.metadata
)

# All models must be imported above this line.
target_metadata = Base.metadata
