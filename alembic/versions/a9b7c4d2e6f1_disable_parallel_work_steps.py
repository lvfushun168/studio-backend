"""disable parallel work-step execution

Revision ID: a9b7c4d2e6f1
Revises: d6f1a2b3c4e5
Create Date: 2026-06-26 16:30:00.000000

The columns remain for backwards-compatible API and database reads, but the
product now uses a single linear sequence within each stage.
"""

from alembic import op
import sqlalchemy as sa


revision = "a9b7c4d2e6f1"
down_revision = "d6f1a2b3c4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE work_step_template_items SET allow_parallel = FALSE WHERE allow_parallel = TRUE"))
    op.execute(sa.text("UPDATE scene_work_steps SET allow_parallel = FALSE WHERE allow_parallel = TRUE"))


def downgrade() -> None:
    # Previous per-step parallel choices cannot be reconstructed after the
    # product-level migration to a linear execution model.
    pass
