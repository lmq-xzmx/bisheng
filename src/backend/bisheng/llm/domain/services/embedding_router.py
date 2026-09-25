"""Embedding Query Router for managing dual-model queries during embedding model migration.

This router determines which embedding model(s) to use for a query based on:
1. The knowledge base's migration status (idle, migrating, completed, locked)
2. The tenant's query strategy configuration (new_only, old_only, dual_rrf)
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class EmbeddingQueryStrategy(StrEnum):
    """Query routing strategy for embedding models."""

    NEW_ONLY = "new_only"  # Only use the new/target model
    OLD_ONLY = "old_only"  # Only use the old/current model
    DUAL_RRF = "dual_rrf"  # Use both models with RRF fusion


@dataclass
class EmbeddingQueryResult:
    """Result from an embedding query with metadata."""

    documents: list[Any]
    model_source: str  # "new", "old", or "dual_rrf"
    strategy_used: EmbeddingQueryStrategy


class EmbeddingQueryRouter:
    """
    Routes embedding queries based on migration status and tenant configuration.

    Decision logic:
    - If tenant strategy is new_only: use target model only
    - If tenant strategy is old_only: use current model only
    - If tenant strategy is dual_rrf or migrating:
      - idle/locked: use single model based on status
      - migrating: use both models with RRF fusion
      - completed: use new model only
    """

    def __init__(
        self,
        kb_migration_status: str,
        kb_model: str | None,
        kb_target_model: str | None,
        kb_migration_progress: float,
        tenant_strategy: EmbeddingQueryStrategy = EmbeddingQueryStrategy.DUAL_RRF,
    ):
        self.kb_migration_status = kb_migration_status
        self.kb_model = kb_model
        self.kb_target_model = kb_target_model
        self.kb_migration_progress = kb_migration_progress
        self.tenant_strategy = tenant_strategy

    def should_use_dual_query(self) -> bool:
        """Determine if we should query both old and new models."""
        # If tenant strategy is explicitly single-model, never use dual
        if self.tenant_strategy in (EmbeddingQueryStrategy.NEW_ONLY, EmbeddingQueryStrategy.OLD_ONLY):
            return False

        # Migrating status always uses dual query for smooth transition
        if self.kb_migration_status == "migrating":
            return True

        # For other statuses, use single model
        return False

    def get_active_model(self) -> str | None:
        """Get the currently active embedding model for single-model queries."""
        status = self.kb_migration_status

        if status in ("idle", "pending_delayed", "pending_immediate"):
            return self.kb_model
        elif status == "migrating":
            # During migration, prefer new model for completed portions
            if self.kb_migration_progress >= 1.0:
                return self.kb_target_model
            return self.kb_model
        elif status == "completed":
            return self.kb_target_model or self.kb_model
        elif status == "locked":
            return self.kb_locked_model
        else:
            return self.kb_model

    def get_model_source(self) -> str:
        """Determine which model(s) were used for the current query."""
        if self.should_use_dual_query():
            return "dual_rrf"
        return "new" if self.tenant_strategy == EmbeddingQueryStrategy.NEW_ONLY else "old"

    def decide_routing(self) -> tuple[list[str], EmbeddingQueryStrategy]:
        """
        Decide which models to query and which strategy to use.

        Returns:
            Tuple of (model_ids to query, strategy used)
        """
        # Explicit single-model strategies override migration status
        if self.tenant_strategy == EmbeddingQueryStrategy.NEW_ONLY:
            return [self.kb_target_model or self.kb_model], EmbeddingQueryStrategy.NEW_ONLY

        if self.tenant_strategy == EmbeddingQueryStrategy.OLD_ONLY:
            return [self.kb_model], EmbeddingQueryStrategy.OLD_ONLY

        # dual_rrf strategy - decide based on migration status
        status = self.kb_migration_status

        if status == "locked":
            return [self.kb_locked_model], EmbeddingQueryStrategy.OLD_ONLY

        if status == "completed":
            return [self.kb_target_model or self.kb_model], EmbeddingQueryStrategy.NEW_ONLY

        if status == "migrating":
            models = []
            if self.kb_model:
                models.append(self.kb_model)
            if self.kb_target_model:
                models.append(self.kb_target_model)
            return models, EmbeddingQueryStrategy.DUAL_RRF

        # idle, pending_* - use current model
        return [self.kb_model], EmbeddingQueryStrategy.OLD_ONLY

    @property
    def kb_locked_model(self) -> str | None:
        """Get the model that was locked - stored in the knowledge base record."""
        # This is stored in knowledge_base.locked_model field
        # Accessed via the kb object that this router wraps
        return getattr(self, "_locked_model", None)

    @property
    def is_migration_complete(self) -> bool:
        """Check if migration has completed."""
        return self.kb_migration_status == "completed"

    @property
    def is_locked(self) -> bool:
        """Check if knowledge base is locked."""
        return self.kb_migration_status == "locked"
