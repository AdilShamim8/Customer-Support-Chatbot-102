"""Initial database schema for conversation storage.

Revision ID: 001
Create Date: 2026-01-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Conversations table
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            onupdate=sa.text("NOW()"),
        ),
        sa.Column(
            "messages",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "user_context",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
    )

    # Feedback table
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("message_index", sa.Integer, nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("was_helpful", sa.Boolean, nullable=False),
        sa.Column("feedback_text", sa.Text, nullable=True),
        sa.Column("issue_category", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
    )

    # Document registry table
    op.create_table(
        "documents",
        sa.Column("doc_id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_path", sa.Text, nullable=False),
        sa.Column("doc_type", sa.String(50), nullable=False),
        sa.Column("chunk_count", sa.Integer, nullable=False, default=0),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
    )

    # Indexes
    op.create_index(
        "ix_conversations_updated_at",
        "conversations",
        ["updated_at"],
    )
    op.create_index(
        "ix_feedback_conversation_id",
        "feedback",
        ["conversation_id"],
    )
    op.create_index(
        "ix_documents_doc_type",
        "documents",
        ["doc_type"],
    )


def downgrade() -> None:
    op.drop_table("documents")
    op.drop_table("feedback")
    op.drop_table("conversations")
