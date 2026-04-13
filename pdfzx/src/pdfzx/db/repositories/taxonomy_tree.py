from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from pdfzx.db.models import Document
from pdfzx.db.models import TaxonomyAssignment
from pdfzx.db.models import TaxonomyNode
from pdfzx.db.models import TaxonomyNodeDocument
from pdfzx.db.models import TaxonomyNodeTopicTerm


@dataclass(frozen=True, slots=True)
class TaxonomyAssignmentView:
    """Readable assignment row for operator inspection."""

    node_path: str
    document_path: str | None
    assigned_path: str | None
    confidence: str | None
    status: str
    reasoning_summary: str | None


@dataclass(frozen=True, slots=True)
class TaxonomyNodeStat:
    """Readable direct membership count for one taxonomy node."""

    node_path: str
    depth: int
    document_count: int


@dataclass(frozen=True, slots=True)
class TaxonomyNodeDocumentView:
    """Readable document membership row for one taxonomy node."""

    node_path: str
    sha256: str
    document_path: str | None


@dataclass(frozen=True, slots=True)
class TaxonomyNodeTermView:
    """Readable narrower topic term row for one taxonomy node."""

    node_id: int
    node_path: str
    term: str


class TaxonomyTreeRepository:
    """CRUD helpers for taxonomy nodes, memberships, and assignments."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_root_node(
        self,
        *,
        name: str = "Root",
        path: str = "Root",
    ) -> TaxonomyNode:
        """Return the root node, creating it if missing."""
        root = self.get_node_by_path(path=path)
        if root is not None:
            return root
        return self.create_node(name=name, path=path)

    def create_node(
        self,
        *,
        name: str,
        path: str,
        parent_id: int | None = None,
        depth: int = 0,
    ) -> TaxonomyNode:
        """Create one taxonomy node."""
        node = TaxonomyNode(
            name=name,
            path=path,
            parent_id=parent_id,
            depth=depth,
        )
        self._session.add(node)
        self._session.flush()
        return node

    def ensure_child_node(
        self,
        *,
        parent_id: int,
        parent_path: str,
        name: str,
    ) -> TaxonomyNode:
        """Return one child node under a parent, creating it if missing."""
        path = f"{parent_path}/{name}"
        node = self.get_node_by_path(path=path)
        if node is not None:
            return node
        parent = self.get_node(node_id=parent_id)
        if parent is None:
            msg = f"Taxonomy node not found: {parent_id}"
            raise ValueError(msg)
        return self.create_node(
            name=name,
            path=path,
            parent_id=parent_id,
            depth=parent.depth + 1,
        )

    def get_node(self, *, node_id: int) -> TaxonomyNode | None:
        """Return one taxonomy node by id."""
        return self._session.get(TaxonomyNode, node_id)

    def get_node_by_path(self, *, path: str) -> TaxonomyNode | None:
        """Return one taxonomy node by stable path."""
        stmt = select(TaxonomyNode).where(TaxonomyNode.path == path)
        return self._session.scalar(stmt)

    def get_child_by_name(self, *, parent_id: int, name: str) -> TaxonomyNode | None:
        """Return one direct child node by parent and child name."""
        stmt = select(TaxonomyNode).where(
            TaxonomyNode.parent_id == parent_id,
            TaxonomyNode.name == name,
        )
        return self._session.scalar(stmt)

    def list_nodes(self, *, parent_id: int | None = None) -> list[TaxonomyNode]:
        """Return nodes, optionally filtered to one parent."""
        stmt = select(TaxonomyNode)
        if parent_id is None:
            stmt = stmt.where(TaxonomyNode.parent_id.is_(None))
        else:
            stmt = stmt.where(TaxonomyNode.parent_id == parent_id)
        stmt = stmt.order_by(TaxonomyNode.path.asc(), TaxonomyNode.id.asc())
        return list(self._session.scalars(stmt))

    def update_node(
        self,
        *,
        node_id: int,
        name: str | None = None,
        path: str | None = None,
    ) -> TaxonomyNode:
        """Update selected fields on one taxonomy node."""
        node = self.get_node(node_id=node_id)
        if node is None:
            msg = f"Taxonomy node not found: {node_id}"
            raise ValueError(msg)
        if name is not None:
            node.name = name
        if path is not None:
            node.path = path
        self._session.flush()
        return node

    def delete_node(self, *, node_id: int) -> None:
        """Delete one taxonomy node."""
        node = self.get_node(node_id=node_id)
        if node is None:
            return
        self._session.delete(node)
        self._session.flush()

    def replace_child_subtree(self, *, parent_id: int) -> int:
        """Delete the current child subtree under one parent node."""
        child_ids = self._descendant_node_ids(parent_id=parent_id)
        if not child_ids:
            return 0
        self._session.execute(
            delete(TaxonomyAssignment).where(TaxonomyAssignment.assigned_child_id.in_(child_ids))
        )
        for node_id in child_ids:
            node = self.get_node(node_id=node_id)
            if node is not None:
                self._session.delete(node)
        self._session.flush()
        return len(child_ids)

    def add_documents(self, *, node_id: int, sha256s: list[str]) -> int:
        """Attach documents to one node, ignoring existing memberships."""
        if not sha256s:
            return 0
        existing = set(self.list_document_sha256s(node_id=node_id))
        document_sha256s = set(self._existing_document_sha256s(sha256s))
        missing = document_sha256s - existing
        if not missing:
            return 0
        self._session.add_all(
            TaxonomyNodeDocument(node_id=node_id, sha256=sha256) for sha256 in sorted(missing)
        )
        self._session.flush()
        return len(missing)

    def sync_root_documents(self, *, root_node_id: int) -> int:
        """Replace root membership with all known documents."""
        stmt = select(Document.sha256).order_by(Document.sha256.asc())
        return self.replace_documents(
            node_id=root_node_id,
            sha256s=list(self._session.scalars(stmt)),
        )

    def replace_documents(self, *, node_id: int, sha256s: list[str]) -> int:
        """Replace the current document membership for one node."""
        unique_sha256s = sorted(set(self._existing_document_sha256s(sha256s)))
        self._session.execute(
            delete(TaxonomyNodeDocument).where(TaxonomyNodeDocument.node_id == node_id)
        )
        if unique_sha256s:
            self._session.add_all(
                TaxonomyNodeDocument(node_id=node_id, sha256=sha256)
                for sha256 in unique_sha256s
            )
        self._session.flush()
        return len(unique_sha256s)

    def list_document_sha256s(self, *, node_id: int) -> list[str]:
        """Return sorted document hashes currently attached to one node."""
        stmt = (
            select(TaxonomyNodeDocument.sha256)
            .where(TaxonomyNodeDocument.node_id == node_id)
            .order_by(TaxonomyNodeDocument.sha256.asc())
        )
        return list(self._session.scalars(stmt))

    def replace_topic_terms(self, *, node_id: int, terms: list[str]) -> int:
        """Replace the current narrower topic terms for one taxonomy node."""
        normalized_terms = sorted({term.strip() for term in terms if term.strip()})
        self._session.execute(
            delete(TaxonomyNodeTopicTerm).where(TaxonomyNodeTopicTerm.node_id == node_id)
        )
        if normalized_terms:
            self._session.add_all(
                TaxonomyNodeTopicTerm(node_id=node_id, term=term) for term in normalized_terms
            )
        self._session.flush()
        return len(normalized_terms)

    def list_topic_terms(self, *, node_id: int) -> list[str]:
        """Return sorted narrower topic terms attached to one taxonomy node."""
        stmt = (
            select(TaxonomyNodeTopicTerm.term)
            .where(TaxonomyNodeTopicTerm.node_id == node_id)
            .order_by(TaxonomyNodeTopicTerm.term.asc())
        )
        return list(self._session.scalars(stmt))

    def list_node_term_views(
        self,
        *,
        node_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[TaxonomyNodeTermView]:
        """Return readable narrower topic term rows, optionally for one node."""
        stmt = (
            select(TaxonomyNode.id, TaxonomyNode.path, TaxonomyNodeTopicTerm.term)
            .join(TaxonomyNodeTopicTerm, TaxonomyNode.id == TaxonomyNodeTopicTerm.node_id)
            .order_by(TaxonomyNode.path.asc(), TaxonomyNodeTopicTerm.term.asc())
            .offset(offset)
        )
        if node_id is not None:
            stmt = stmt.where(TaxonomyNode.id == node_id)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [
            TaxonomyNodeTermView(node_id=node_id, node_path=node_path, term=term)
            for node_id, node_path, term in self._session.execute(stmt)
        ]

    def upsert_assignment(  # noqa: PLR0913
        self,
        *,
        node_id: int,
        sha256: str,
        assigned_child_id: int | None,
        confidence: str | None = None,
        reasoning_summary: str | None = None,
        status: str = "pending",
    ) -> TaxonomyAssignment:
        """Create or update one assignment decision under a parent node."""
        assignment = self._session.get(TaxonomyAssignment, {"node_id": node_id, "sha256": sha256})
        now = datetime.now(tz=UTC).replace(tzinfo=None)
        if assignment is None:
            assignment = TaxonomyAssignment(
                node_id=node_id,
                sha256=sha256,
                assigned_child_id=assigned_child_id,
                confidence=confidence,
                reasoning_summary=reasoning_summary,
                status=status,
                created_at=now,
                updated_at=now,
            )
            self._session.add(assignment)
            self._session.flush()
            return assignment
        assignment.assigned_child_id = assigned_child_id
        assignment.confidence = confidence
        assignment.reasoning_summary = reasoning_summary
        assignment.status = status
        assignment.updated_at = now
        self._session.flush()
        return assignment

    def list_assignments(self, *, node_id: int) -> list[TaxonomyAssignment]:
        """Return assignments for one parent node."""
        stmt = (
            select(TaxonomyAssignment)
            .where(TaxonomyAssignment.node_id == node_id)
            .order_by(TaxonomyAssignment.sha256.asc())
        )
        return list(self._session.scalars(stmt))

    def list_assignment_views(
        self,
        *,
        node_id: int,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[TaxonomyAssignmentView]:
        """Return readable assignment rows for one parent node."""
        stmt = (
            select(TaxonomyAssignment)
            .options(
                selectinload(TaxonomyAssignment.node),
                selectinload(TaxonomyAssignment.assigned_child),
                selectinload(TaxonomyAssignment.document).selectinload(Document.paths),
            )
            .where(TaxonomyAssignment.node_id == node_id)
            .order_by(TaxonomyAssignment.sha256.asc())
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(TaxonomyAssignment.status == status)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = []
        for assignment in self._session.scalars(stmt):
            document_paths = sorted(path.rel_path for path in assignment.document.paths)
            rows.append(
                TaxonomyAssignmentView(
                    node_path=assignment.node.path,
                    document_path=document_paths[0] if document_paths else None,
                    assigned_path=(
                        assignment.assigned_child.path if assignment.assigned_child else None
                    ),
                    confidence=assignment.confidence,
                    status=assignment.status,
                    reasoning_summary=assignment.reasoning_summary,
                )
            )
        return rows

    def list_node_stats(
        self,
        *,
        depth: int | None = None,
    ) -> list[TaxonomyNodeStat]:
        """Return direct membership counts grouped by taxonomy node."""
        stmt = (
            select(
                TaxonomyNode.path,
                TaxonomyNode.depth,
                func.count(TaxonomyNodeDocument.sha256),
            )
            .outerjoin(TaxonomyNodeDocument, TaxonomyNode.id == TaxonomyNodeDocument.node_id)
            .group_by(TaxonomyNode.id, TaxonomyNode.path, TaxonomyNode.depth)
            .order_by(func.count(TaxonomyNodeDocument.sha256).desc(), TaxonomyNode.path.asc())
        )
        if depth is not None:
            stmt = stmt.where(TaxonomyNode.depth == depth)
        return [
            TaxonomyNodeStat(
                node_path=node_path,
                depth=node_depth,
                document_count=document_count,
            )
            for node_path, node_depth, document_count in self._session.execute(stmt)
        ]

    def list_node_document_views(
        self,
        *,
        node_id: int,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[TaxonomyNodeDocumentView]:
        """Return readable document membership rows for one taxonomy node."""
        stmt = (
            select(TaxonomyNodeDocument)
            .options(
                selectinload(TaxonomyNodeDocument.node),
                selectinload(TaxonomyNodeDocument.document).selectinload(Document.paths),
            )
            .where(TaxonomyNodeDocument.node_id == node_id)
            .order_by(TaxonomyNodeDocument.sha256.asc())
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = []
        for membership in self._session.scalars(stmt):
            document_paths = sorted(path.rel_path for path in membership.document.paths)
            rows.append(
                TaxonomyNodeDocumentView(
                    node_path=membership.node.path,
                    sha256=membership.sha256,
                    document_path=document_paths[0] if document_paths else None,
                )
            )
        return rows

    def apply_assignments(
        self,
        *,
        node_id: int,
        minimum_confidence: str = "high",
        exclude_path_keywords: list[str] | None = None,
    ) -> dict[str, int]:
        """Apply pending assignments above a confidence threshold to child memberships."""
        confidence_order = {"low": 0, "medium": 1, "high": 2}
        minimum_rank = confidence_order[minimum_confidence]
        applied = 0
        skipped = 0
        excluded = 0
        keywords = [keyword.lower() for keyword in exclude_path_keywords or []]
        stmt = (
            select(TaxonomyAssignment)
            .options(selectinload(TaxonomyAssignment.document).selectinload(Document.paths))
            .where(TaxonomyAssignment.node_id == node_id)
            .order_by(TaxonomyAssignment.sha256.asc())
        )
        for assignment in self._session.scalars(stmt):
            if assignment.status != "pending":
                skipped += 1
                continue
            if assignment.assigned_child_id is None:
                skipped += 1
                continue
            confidence = assignment.confidence or "low"
            if confidence_order.get(confidence, -1) < minimum_rank:
                skipped += 1
                continue
            if keywords and any(
                keyword in path.rel_path.lower()
                for keyword in keywords
                for path in assignment.document.paths
            ):
                excluded += 1
                continue
            self.add_documents(node_id=assignment.assigned_child_id, sha256s=[assignment.sha256])
            self._session.execute(
                delete(TaxonomyNodeDocument).where(
                    TaxonomyNodeDocument.node_id == node_id,
                    TaxonomyNodeDocument.sha256 == assignment.sha256,
                )
            )
            assignment.status = "applied"
            assignment.updated_at = datetime.now(tz=UTC).replace(tzinfo=None)
            applied += 1
        self._session.flush()
        return {"applied": applied, "skipped": skipped, "excluded": excluded}

    def _existing_document_sha256s(self, sha256s: list[str]) -> list[str]:
        stmt = select(Document.sha256).where(Document.sha256.in_(set(sha256s)))
        return list(self._session.scalars(stmt))

    def _descendant_node_ids(self, *, parent_id: int) -> list[int]:
        direct_children = self.list_nodes(parent_id=parent_id)
        descendant_ids: list[int] = []
        for child in direct_children:
            descendant_ids.append(child.id)
            descendant_ids.extend(self._descendant_node_ids(parent_id=child.id))
        return descendant_ids
