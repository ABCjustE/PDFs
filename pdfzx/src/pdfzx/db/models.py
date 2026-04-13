from __future__ import annotations

from datetime import UTC
from datetime import datetime
from typing import Any

from sqlalchemy import JSON
from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from pdfzx.db.base import Base


class Document(Base):
    """Canonical document record keyed by content hash."""

    __tablename__ = "documents"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    md5: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalised_name: Mapped[str | None] = mapped_column(String(512))
    llm_enriched_name: Mapped[str | None] = mapped_column(String(512))
    metadata_title: Mapped[str | None] = mapped_column(String(512))
    metadata_author: Mapped[str | None] = mapped_column(String(512))
    metadata_creator: Mapped[str | None] = mapped_column(String(512))
    metadata_created: Mapped[str | None] = mapped_column(String(128))
    metadata_modified: Mapped[str | None] = mapped_column(String(128))
    metadata_extra_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    languages_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_digital: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    toc_valid: Mapped[bool | None] = mapped_column(Boolean)
    toc_invalid_reason: Mapped[str | None] = mapped_column(Text)
    extraction_status: Mapped[str | None] = mapped_column(String(32))
    force_extracted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    first_seen_job: Mapped[str | None] = mapped_column(ForeignKey("jobs.job_id"))
    last_seen_job: Mapped[str | None] = mapped_column(ForeignKey("jobs.job_id"))

    paths: Mapped[list[DocumentPath]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    toc_entries: Mapped[list[DocumentTocEntry]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    file_stats: Mapped[list[FileStat]] = relationship(back_populates="document")
    llm_document_suggestions: Mapped[list[LlmDocumentSuggestion]] = relationship(
        back_populates="document"
    )
    llm_taxonomy_suggestions: Mapped[list[LlmTaxonomySuggestion]] = relationship(
        back_populates="document"
    )
    llm_toc_review_suggestions: Mapped[list[LlmTocReviewSuggestion]] = relationship(
        back_populates="document"
    )
    taxonomy_memberships: Mapped[list[TaxonomyNodeDocument]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    taxonomy_assignments: Mapped[list[TaxonomyAssignment]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentPath(Base):
    """Known relative path for a document."""

    __tablename__ = "document_paths"
    __table_args__ = (UniqueConstraint("sha256", "rel_path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(ForeignKey("documents.sha256"), nullable=False)
    rel_path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)

    document: Mapped[Document] = relationship(back_populates="paths")


class DocumentTocEntry(Base):
    """Ordered table-of-contents entry for a document."""

    __tablename__ = "document_toc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(ForeignKey("documents.sha256"), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    document: Mapped[Document] = relationship(back_populates="toc_entries")


class FileStat(Base):
    """Per-path incremental scan state."""

    __tablename__ = "file_stats"

    rel_path: Mapped[str] = mapped_column(String(1024), primary_key=True)
    sha256: Mapped[str] = mapped_column(ForeignKey("documents.sha256"), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mtime: Mapped[float] = mapped_column(Float, nullable=False)
    last_scanned_job: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), nullable=False)

    document: Mapped[Document] = relationship(back_populates="file_stats")
    job: Mapped[Job] = relationship(back_populates="file_stats")


class Job(Base):
    """Inventory run audit record."""

    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    root_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    removed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    file_stats: Mapped[list[FileStat]] = relationship(back_populates="job")


class Prompt(Base):
    """Stored prompt definition and version identity."""

    __tablename__ = "prompts"
    __table_args__ = (
        UniqueConstraint("workflow_name", "model_provider", "model", "prompt_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    model_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    document_suggestions: Mapped[list[LlmDocumentSuggestion]] = relationship(
        back_populates="prompt"
    )
    taxonomy_suggestions: Mapped[list[LlmTaxonomySuggestion]] = relationship(
        back_populates="prompt"
    )
    toc_review_suggestions: Mapped[list[LlmTocReviewSuggestion]] = relationship(
        back_populates="prompt"
    )


class PromptSuggestionMixin:
    """Shared lifecycle fields for prompt-backed suggestion tables."""

    reasoning_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)


class TaxonomyNode(Base):
    """One node in the taxonomy tree."""

    __tablename__ = "taxonomy_nodes"
    __table_args__ = (UniqueConstraint("parent_id", "name"), UniqueConstraint("path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("taxonomy_nodes.id"))
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)

    parent: Mapped[TaxonomyNode | None] = relationship(
        remote_side=lambda: [TaxonomyNode.id], back_populates="children"
    )
    children: Mapped[list[TaxonomyNode]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    documents: Mapped[list[TaxonomyNodeDocument]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )
    topic_terms: Mapped[list[TaxonomyNodeTopicTerm]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )
    outgoing_assignments: Mapped[list[TaxonomyAssignment]] = relationship(
        foreign_keys="TaxonomyAssignment.node_id",
        back_populates="node",
        cascade="all, delete-orphan",
    )
    incoming_assignments: Mapped[list[TaxonomyAssignment]] = relationship(
        foreign_keys="TaxonomyAssignment.assigned_child_id",
        back_populates="assigned_child",
    )


class TaxonomyNodeDocument(Base):
    """Current document membership for one taxonomy node."""

    __tablename__ = "taxonomy_node_documents"

    node_id: Mapped[int] = mapped_column(ForeignKey("taxonomy_nodes.id"), primary_key=True)
    sha256: Mapped[str] = mapped_column(ForeignKey("documents.sha256"), primary_key=True)

    node: Mapped[TaxonomyNode] = relationship(back_populates="documents")
    document: Mapped[Document] = relationship(back_populates="taxonomy_memberships")


class TaxonomyNodeTopicTerm(Base):
    """Reviewable narrower topic term attached to one taxonomy node."""

    __tablename__ = "taxonomy_node_topic_terms"

    node_id: Mapped[int] = mapped_column(ForeignKey("taxonomy_nodes.id"), primary_key=True)
    term: Mapped[str] = mapped_column(String(256), primary_key=True)

    node: Mapped[TaxonomyNode] = relationship(back_populates="topic_terms")


class TaxonomyAssignment(Base):
    """Assignment decision for one document under one parent node."""

    __tablename__ = "taxonomy_assignments"

    node_id: Mapped[int] = mapped_column(ForeignKey("taxonomy_nodes.id"), primary_key=True)
    sha256: Mapped[str] = mapped_column(ForeignKey("documents.sha256"), primary_key=True)
    assigned_child_id: Mapped[int | None] = mapped_column(ForeignKey("taxonomy_nodes.id"))
    confidence: Mapped[str | None] = mapped_column(String(16))
    reasoning_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(tz=UTC).replace(tzinfo=None),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(tz=UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(tz=UTC).replace(tzinfo=None),
        nullable=False,
    )

    node: Mapped[TaxonomyNode] = relationship(
        foreign_keys=[node_id], back_populates="outgoing_assignments"
    )
    document: Mapped[Document] = relationship(back_populates="taxonomy_assignments")
    assigned_child: Mapped[TaxonomyNode | None] = relationship(
        foreign_keys=[assigned_child_id], back_populates="incoming_assignments"
    )


class LlmDocumentSuggestion(PromptSuggestionMixin, Base):
    """Structured LLM suggestion for one document and prompt."""

    __tablename__ = "llm_document_suggestions"
    __table_args__ = (UniqueConstraint("sha256", "prompt_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(ForeignKey("documents.sha256"), nullable=False, index=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id"), nullable=False, index=True)
    suggested_file_name: Mapped[str | None] = mapped_column(String(512))
    suggested_author: Mapped[str | None] = mapped_column(String(512))
    suggested_publisher: Mapped[str | None] = mapped_column(String(512))
    suggested_edition: Mapped[str | None] = mapped_column(String(256))
    suggested_labels_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    document: Mapped[Document] = relationship(back_populates="llm_document_suggestions")
    prompt: Mapped[Prompt] = relationship(back_populates="document_suggestions")


class LlmTaxonomySuggestion(PromptSuggestionMixin, Base):
    """Structured taxonomy suggestion for one document and prompt."""

    # TODO: Drop this table in a future schema migration after existing production
    # data is no longer needed. The runtime taxonomy-suggestion workflow has been removed.
    __tablename__ = "llm_taxonomy_suggestions"
    __table_args__ = (UniqueConstraint("sha256", "prompt_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(ForeignKey("documents.sha256"), nullable=False, index=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id"), nullable=False, index=True)
    suggested_taxonomy_path: Mapped[str | None] = mapped_column(String(1024))
    suggested_document_type: Mapped[str | None] = mapped_column(String(64))
    suggested_new_subcategory: Mapped[str | None] = mapped_column(String(256))
    confidence: Mapped[float | None] = mapped_column(Float)

    document: Mapped[Document] = relationship(back_populates="llm_taxonomy_suggestions")
    prompt: Mapped[Prompt] = relationship(back_populates="taxonomy_suggestions")


class LlmTocReviewSuggestion(PromptSuggestionMixin, Base):
    """Structured ToC review suggestion for one document and prompt."""

    __tablename__ = "llm_toc_review_suggestions"
    __table_args__ = (UniqueConstraint("sha256", "prompt_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(ForeignKey("documents.sha256"), nullable=False, index=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id"), nullable=False, index=True)
    toc_is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    toc_matches_document: Mapped[bool] = mapped_column(Boolean, nullable=False)
    toc_invalid_reason: Mapped[str | None] = mapped_column(Text)
    preface_page: Mapped[int | None] = mapped_column(Integer)
    preface_label: Mapped[str | None] = mapped_column(String(256))
    confidence: Mapped[float | None] = mapped_column(Float)

    document: Mapped[Document] = relationship(back_populates="llm_toc_review_suggestions")
    prompt: Mapped[Prompt] = relationship(back_populates="toc_review_suggestions")
