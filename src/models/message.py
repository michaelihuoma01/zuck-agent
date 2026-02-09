"""Message model - Represents a message in a Claude session."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, generate_uuid, utc_now

if TYPE_CHECKING:
    from src.models.session import Session


class Message(Base):
    """A message in a Claude session (user, assistant, tool_use, tool_result, system)."""

    __tablename__ = "messages"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )

    # Foreign key to Session
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Message role: user, assistant, system, tool_use, tool_result
    role: Mapped[str] = mapped_column(String(50), nullable=False)

    # Message content (text or JSON string for tool use/result)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # SDK message type for reconstruction (e.g., "assistant", "tool_use")
    message_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Additional metadata (token counts, timing, tool details, etc.)
    # Note: "metadata" is reserved in SQLAlchemy, so we use "extra" as the column name
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # When the message was received
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="messages")

    def __repr__(self) -> str:
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Message(id={self.id!r}, role={self.role!r}, content={content_preview!r})>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "message_type": self.message_type,
            "metadata": self.extra,  # Expose as "metadata" in API
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
