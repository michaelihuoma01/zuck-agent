"""Project model - Represents a registered code project."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from src.models.session import Session


class Project(Base, TimestampMixin):
    """A registered project directory that can have Claude sessions."""

    __tablename__ = "projects"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )

    # Display name for the project
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Absolute path to project directory
    path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)

    # Optional description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tools enabled by default (e.g., ["Read", "Write", "Bash"])
    default_allowed_tools: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
    )

    # Permission mode: "default", "acceptEdits", "manual"
    permission_mode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="default",
    )

    # Bash command patterns to auto-approve (e.g., ["git status", "npm test"])
    auto_approve_patterns: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
    )

    # Live preview: dev server command (e.g., "npm run dev -- --host 0.0.0.0")
    dev_command: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Live preview: dev server port (e.g., 5173)
    dev_port: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    sessions: Mapped[list["Session"]] = relationship(
        "Session",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id!r}, name={self.name!r}, path={self.path!r})>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "description": self.description,
            "default_allowed_tools": self.default_allowed_tools or [],
            "permission_mode": self.permission_mode,
            "auto_approve_patterns": self.auto_approve_patterns or [],
            "dev_command": self.dev_command,
            "dev_port": self.dev_port,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
