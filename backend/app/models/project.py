from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    root_path: Mapped[str] = mapped_column(
        String(2048),
        unique=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="created",
        nullable=False,
    )
    last_scan_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    files = relationship("CodeFile", cascade="all, delete-orphan")
    entities = relationship("CodeEntity", cascade="all, delete-orphan")
    relations = relationship("CodeRelation", cascade="all, delete-orphan")
    issues = relationship("ScanIssue", cascade="all, delete-orphan")
    conversations = relationship(
        "Conversation",
        back_populates="project",
        cascade="all, delete-orphan",
    )
