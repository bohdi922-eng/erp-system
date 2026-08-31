"""add sessions table (auth)

Revision ID: 0003_sessions
Revises: 0002_whatsapp_messages
Create Date: 2026-08-30

"""
from alembic import op
import sqlalchemy as sa

revision = "0003_sessions"
down_revision = "0002_whatsapp_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sessions")
