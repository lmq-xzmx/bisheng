"""Knowledge base embedding model migration service.

Manages the lifecycle of embedding model migration for knowledge bases:
- Start migration (immediate or delayed)
- Pause / resume / force complete
- Lock / unlock knowledge base at current model
- Query migration status and progress
"""

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import select

from bisheng.common.errcode.knowledge_migration import (
    EmbeddingMigrationAlreadyCompletedError,
    EmbeddingMigrationAlreadyLockedError,
    EmbeddingMigrationInProgressError,
    EmbeddingMigrationInvalidStatusError,
    EmbeddingMigrationLockedKBError,
    EmbeddingMigrationNoTargetModelError,
    EmbeddingMigrationNotFoundError,
    EmbeddingMigrationUnlockError,
)
from bisheng.knowledge.domain.models.knowledge import Knowledge, KnowledgeDao, MigrationStatus
from bisheng.llm.domain.services.embedding_router import EmbeddingQueryRouter


class KnowledgeMigrationService:
    """Service for managing knowledge base embedding model migrations."""

    # Estimated embedding time per document (seconds) - used for progress estimation
    ESTIMATED_EMBEDDING_TIME_PER_DOC = 0.1  # 100ms per document (GPU)

    @classmethod
    async def get_migration_status(cls, kb_id: int) -> dict[str, Any]:
        """
        Get migration status for a knowledge base.

        Returns:
            Dict with migration status, progress, model info, etc.
        """
        kb = await KnowledgeDao.async_query_by_id(kb_id)
        if not kb:
            raise EmbeddingMigrationNotFoundError()

        return {
            "kb_id": kb.id,
            "kb_name": kb.name,
            "current_model": kb.model,
            "target_model": kb.target_model,
            "migration_status": kb.migration_status,
            "migration_progress": kb.migration_progress,
            "locked_at": kb.locked_at,
            "locked_by": kb.locked_by,
            "locked_model": kb.locked_model,
            "estimated_total_docs": cls._estimate_total_docs(kb),
        }

    @classmethod
    async def list_all_kb_migration_status(cls, tenant_id: int) -> list[dict[str, Any]]:
        """
        List migration status for all knowledge bases in a tenant.

        Returns:
            List of migration status dicts for all knowledge bases.
        """
        # Get all knowledge bases for tenant
        statement = select(Knowledge).where(Knowledge.tenant_id == tenant_id)
        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            result = await session.exec(statement)
            knowledge_bases = result.all()

        return [
            {
                "kb_id": kb.id,
                "kb_name": kb.name,
                "current_model": kb.model,
                "target_model": kb.target_model,
                "migration_status": kb.migration_status,
                "migration_progress": kb.migration_progress,
                "locked_at": kb.locked_at,
                "locked_by": kb.locked_by,
                "locked_model": kb.locked_model,
            }
            for kb in knowledge_bases
        ]

    @classmethod
    async def start_migration(
        cls,
        kb_id: int,
        target_model: str,
        strategy: str = "immediate",
        user_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Start embedding model migration for a knowledge base.

        Args:
            kb_id: Knowledge base ID
            target_model: Target embedding model ID
            strategy: "immediate" or "delayed"
            user_name: Username initiating the migration

        Returns:
            Updated migration status
        """
        kb = await KnowledgeDao.async_query_by_id(kb_id)
        if not kb:
            raise EmbeddingMigrationNotFoundError()

        # Validate target model
        if not target_model:
            raise EmbeddingMigrationNoTargetModelError()

        # Check current status
        if kb.migration_status == MigrationStatus.MIGRATING.value:
            raise EmbeddingMigrationInProgressError()

        if kb.migration_status == MigrationStatus.LOCKED.value:
            raise EmbeddingMigrationLockedKBError()

        if kb.migration_status == MigrationStatus.COMPLETED.value:
            raise EmbeddingMigrationAlreadyCompletedError()

        # Set migration status based on strategy
        new_status = (
            MigrationStatus.PENDING_IMMEDIATE.value
            if strategy == "immediate"
            else MigrationStatus.PENDING_DELAYED.value
        )

        # Update knowledge base
        kb.target_model = target_model
        kb.migration_status = new_status
        kb.migration_progress = 0.0

        await KnowledgeDao.aupdate_one(kb)

        logger.info(
            "Starting embedding migration for kb_id={}, target_model={}, strategy={}, user={}",
            kb_id,
            target_model,
            strategy,
            user_name,
        )

        return await cls.get_migration_status(kb_id)

    @classmethod
    async def pause_migration(cls, kb_id: int) -> dict[str, Any]:
        """
        Pause an in-progress migration.

        The migration can be resumed later. Progress is preserved.
        """
        kb = await KnowledgeDao.async_query_by_id(kb_id)
        if not kb:
            raise EmbeddingMigrationNotFoundError()

        if kb.migration_status != MigrationStatus.MIGRATING.value:
            raise EmbeddingMigrationInvalidStatusError(
                status=kb.migration_status,
            )

        # Mark as pending_delayed to pause
        kb.migration_status = MigrationStatus.PENDING_DELAYED.value
        await KnowledgeDao.aupdate_one(kb)

        logger.info("Paused migration for kb_id={}", kb_id)

        return await cls.get_migration_status(kb_id)

    @classmethod
    async def force_complete_migration(cls, kb_id: int) -> dict[str, Any]:
        """
        Force complete a migration.

        Marks migration as completed even if not all documents have been re-embedded.
        The partially migrated data will be used.
        """
        kb = await KnowledgeDao.async_query_by_id(kb_id)
        if not kb:
            raise EmbeddingMigrationNotFoundError()

        if kb.migration_status not in (
            MigrationStatus.MIGRATING.value,
            MigrationStatus.PENDING_IMMEDIATE.value,
            MigrationStatus.PENDING_DELAYED.value,
        ):
            raise EmbeddingMigrationInvalidStatusError(
                status=kb.migration_status,
            )

        # Mark as completed
        kb.migration_status = MigrationStatus.COMPLETED.value
        kb.migration_progress = 1.0
        kb.model = kb.target_model  # Switch to new model

        await KnowledgeDao.aupdate_one(kb)

        logger.info("Force completed migration for kb_id={}", kb_id)

        return await cls.get_migration_status(kb_id)

    @classmethod
    async def lock_knowledge_base(
        cls,
        kb_id: int,
        user_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Lock a knowledge base at its current embedding model.

        A locked KB will not be affected by system default embedding model changes.
        """
        kb = await KnowledgeDao.async_query_by_id(kb_id)
        if not kb:
            raise EmbeddingMigrationNotFoundError()

        if kb.migration_status == MigrationStatus.LOCKED.value:
            raise EmbeddingMigrationAlreadyLockedError()

        kb.migration_status = MigrationStatus.LOCKED.value
        kb.locked_at = datetime.now()
        kb.locked_by = user_name
        kb.locked_model = kb.model
        kb.target_model = None  # Clear any pending migration
        kb.migration_progress = 0.0

        await KnowledgeDao.aupdate_one(kb)

        logger.info("Locked knowledge base kb_id={}, user={}", kb_id, user_name)

        return await cls.get_migration_status(kb_id)

    @classmethod
    async def unlock_knowledge_base(cls, kb_id: int) -> dict[str, Any]:
        """
        Unlock a knowledge base.

        After unlocking, the KB will be subject to system default embedding model changes.
        """
        kb = await KnowledgeDao.async_query_by_id(kb_id)
        if not kb:
            raise EmbeddingMigrationNotFoundError()

        if kb.migration_status != MigrationStatus.LOCKED.value:
            raise EmbeddingMigrationUnlockError()

        kb.migration_status = MigrationStatus.IDLE.value
        kb.locked_at = None
        kb.locked_by = None
        kb.locked_model = None

        await KnowledgeDao.aupdate_one(kb)

        logger.info("Unlocked knowledge base kb_id={}", kb_id)

        return await cls.get_migration_status(kb_id)

    @classmethod
    async def update_migration_progress(
        cls,
        kb_id: int,
        progress: float,
    ) -> None:
        """
        Update migration progress for a knowledge base.

        Called by the Celery worker during migration.
        """
        kb = await KnowledgeDao.async_query_by_id(kb_id)
        if not kb:
            logger.warning("Cannot update progress for unknown kb_id={}", kb_id)
            return

        kb.migration_progress = min(max(progress, 0.0), 1.0)
        if progress >= 1.0:
            kb.migration_status = MigrationStatus.COMPLETED.value
            kb.model = kb.target_model  # Switch to new model
            logger.info(
                "Migration completed for kb_id={}, final_progress={}",
                kb_id,
                progress,
            )

        await KnowledgeDao.aupdate_one(kb)

    @classmethod
    def create_router_for_kb(
        cls,
        kb: Knowledge,
        tenant_strategy: str = "dual_rrf",
    ) -> EmbeddingQueryRouter:
        """
        Create an EmbeddingQueryRouter for a knowledge base.

        Args:
            kb: Knowledge base instance
            tenant_strategy: Tenant-wide query strategy

        Returns:
            Configured EmbeddingQueryRouter
        """
        from bisheng.llm.domain.services.embedding_router import EmbeddingQueryStrategy

        # Convert string strategy to enum
        strategy_map = {
            "new_only": EmbeddingQueryStrategy.NEW_ONLY,
            "old_only": EmbeddingQueryStrategy.OLD_ONLY,
            "dual_rrf": EmbeddingQueryStrategy.DUAL_RRF,
        }
        strategy = strategy_map.get(tenant_strategy, EmbeddingQueryStrategy.DUAL_RRF)

        return EmbeddingQueryRouter(
            kb_migration_status=kb.migration_status,
            kb_model=kb.model,
            kb_target_model=kb.target_model,
            kb_migration_progress=kb.migration_progress,
            tenant_strategy=strategy,
        )

    @classmethod
    def _estimate_total_docs(cls, kb: Knowledge) -> int:
        """
        Estimate total documents in a knowledge base.

        This is used for migration time estimation.
        In a real implementation, this would query the actual document count.
        """
        # TODO: Query actual document count from knowledge_file or knowledge_document
        # For now, return a placeholder
        return 0
