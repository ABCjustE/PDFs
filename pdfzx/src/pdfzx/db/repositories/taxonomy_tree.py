from __future__ import annotations

from datetime import UTC
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.models import TaxonomyAssignment
from pdfzx.db.models import TaxonomyNode
from pdfzx.db.models import TaxonomyNodeDocument


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

    def upsert_assignment(
        self,
        *,
        node_id: int,
        sha256: str,
        assigned_child_id: int | None,
        confidence: str | None = None,
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
                status=status,
                created_at=now,
                updated_at=now,
            )
            self._session.add(assignment)
            self._session.flush()
            return assignment
        assignment.assigned_child_id = assigned_child_id
        assignment.confidence = confidence
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
