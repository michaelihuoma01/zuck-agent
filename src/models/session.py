"""Session model - Represents a Claude agent session."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from src.models.message import Message
    from src.models.project import Project


class SessionStatus(str, Enum):
    """Status of a Claude session."""

    IDLE = "idle"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    ERROR = "error"


class Session(Base, TimestampMixin):
    """A Claude agent session tied to a project."""

    __tablename__ = "sessions"

    # Primary key (our ID)
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )

    # Claude SDK's session ID (captured from init message)
    claude_session_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Foreign key to Project
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Display name for the session
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Session status
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=SessionStatus.IDLE.value,
        index=True,  # Frequently filtered by status
    )

    # Most recent user prompt
    last_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tool use awaiting approval (null if none)
    # Structure follows Section 6.4: tool_name, tool_input, tool_use_id, file_path, diff, requested_at
    pending_approval: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Number of messages in session
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Cumulative API cost in USD
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Error details if status is ERROR
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.timestamp",
    )

    def __repr__(self) -> str:
        return f"<Session(id={self.id!r}, status={self.status!r}, project_id={self.project_id!r})>"

    @property
    def status_enum(self) -> SessionStatus:
        """Get status as enum."""
        return SessionStatus(self.status)

    def set_status(self, status: SessionStatus) -> None:
        """Set status from enum."""
        self.status = status.value

    def to_dict(self, include_messages: bool = False) -> dict:
        """Convert to dictionary for API responses."""
        data = {
            "id": self.id,
            "claude_session_id": self.claude_session_id,
            "project_id": self.project_id,
            "name": self.name,
            "status": self.status,
            "last_prompt": self.last_prompt,
            "pending_approval": self.pending_approval,
            "message_count": self.message_count,
            "total_cost_usd": self.total_cost_usd,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_messages:
            data["messages"] = [m.to_dict() for m in self.messages]
        return data
