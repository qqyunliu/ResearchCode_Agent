from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.message import Message


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    project = relationship(
        "Project",
        back_populates="conversations",
    )
    messages = relationship(
        Message,
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by=(Message.created_at, Message.id),
    )
