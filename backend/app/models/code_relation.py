from sqlalchemy import Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CodeRelation(Base):
    __tablename__ = "code_relations"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "source_id",
            "target_id",
            "relation_type",
            name="uq_code_relations_edge",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("code_entities.id", ondelete="CASCADE"),
    )
    target_id: Mapped[int] = mapped_column(
        ForeignKey("code_entities.id", ondelete="CASCADE"),
    )
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False,
    )
    metadata_json: Mapped[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )
