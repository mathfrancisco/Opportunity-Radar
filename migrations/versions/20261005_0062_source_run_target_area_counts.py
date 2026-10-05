"""Count each run's items inside and outside the active profile's target areas.

Revision ID: 20261005_0062
Revises: 20261004_0061
Create Date: 2026-10-05 00:00:00

Card F50-04: a source whose items mostly fall outside the profile's target role families
stops persisting new off-target raw items. The decision reads these two counters over the
source's last complete runs. Null means the run predates the measurement (or no active
profile declared target areas), never a guessed zero.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261005_0062"
down_revision = "20261004_0061"
branch_labels = None
depends_on = None

SCHEMA = "acquisition"
TABLE = "source_run"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("items_target_area", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("items_off_target", sa.Integer(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column(TABLE, "items_off_target", schema=SCHEMA)
    op.drop_column(TABLE, "items_target_area", schema=SCHEMA)
