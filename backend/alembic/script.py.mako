"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
${imports if imports else ""}
# revision identifiers, used by Alembic.
# fmt: off
revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}
# fmt: on

# Explicitly public: Alembic reads these identifiers by name via module
# introspection, so code scanning would otherwise report them as unused
# globals. Keep this a literal list of names — a computed ``__all__``
# (comprehension, ``+=``) makes the module-wide unused-global analysis
# unusable instead of scoping it to these four identifiers.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Upgrade schema."""
% if upgrades:
${upgrades}
% endif


def downgrade() -> None:
    """Downgrade schema."""
% if downgrades:
${downgrades}
% endif
