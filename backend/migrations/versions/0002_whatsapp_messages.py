"""add whatsapp_messages table

Revision ID: 0002_whatsapp_messages
Revises: 0001_initial
Create Date: 2026-08-24

"""
from alembic import op
import sqlalchemy as sa

revision = "0002_whatsapp_messages"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("message_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="simulated"),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("repair_id", sa.Integer, sa.ForeignKey("repair_orders.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("whatsapp_messages")
