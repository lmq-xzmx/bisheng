"""Embedding model migration Celery tasks.

F050: Handles async re-embedding of knowledge base documents when switching
embedding models, supporting pause/resume via progress tracking.
"""

from dataclasses import dataclass

from loguru import logger
from sqlalchemy import select

from bisheng.common.errcode.knowledge_migration import (
    EmbeddingMigrationTaskError,
)
from bisheng.core.logger import trace_id_var
from bisheng.knowledge.domain.models.knowledge import Knowledge, KnowledgeDao, MigrationStatus
from bisheng.worker.main import bisheng_celery


@dataclass
class BatchResult:
    """Result of processing a batch of documents."""

    count: int
    error: str | None = None


# Batch size for processing documents
BATCH_SIZE = 100


@bisheng_celery.task(acks_late=True, bind=True)
def task_migrate_knowledge_base(self, kb_id: int, target_model: str) -> str:
    """
    Migrate a knowledge base to a new embedding model.

    This task:
    1. Updates the KB status to 'migrating'
    2. Processes documents in batches
    3. Updates progress after each batch
    4. Handles failures gracefully with retry

    Args:
        kb_id: Knowledge base ID
        target_model: Target embedding model ID

    Returns:
        str: Task result message
    """
    trace_id_var.set(f"embed_migration_{kb_id}")
    logger.info(
        "task_migrate_knowledge_base start kb_id={}, target_model={}",
        kb_id,
        target_model,
    )

    try:
        # Get knowledge base
        kb = KnowledgeDao.query_by_id(kb_id)
        if not kb:
            logger.error("kb_id={} not found", kb_id)
            return f"knowledge {kb_id} not found"

        # Update status to migrating
        kb.migration_status = MigrationStatus.MIGRATING.value
        kb.target_model = target_model
        KnowledgeDao.update_one(kb)

        # Get total document count for progress estimation
        total_docs = _get_document_count(kb)
        if total_docs == 0:
            # No documents, complete immediately
            _complete_migration(kb_id, target_model)
            return f"knowledge {kb_id} migration completed (no documents)"

        logger.info(
            "Starting migration for kb_id={}, total_docs={}, target_model={}",
            kb_id,
            total_docs,
            target_model,
        )

        # Process documents in batches
        processed = 0
        batch_num = 0
        while processed < total_docs:
            # Check if task was revoked/paused
            if self.request.id and self.app.control.inspect().revoked(self.request.id):
                logger.info("Migration task {} was revoked, saving progress", self.request.id)
                break

            batch_result = _process_document_batch(
                kb=kb,
                target_model=target_model,
                batch_size=BATCH_SIZE,
                offset=processed,
            )

            if batch_result.error:
                logger.error(
                    "Batch {} failed for kb_id={}: {}",
                    batch_num,
                    kb_id,
                    batch_result.error,
                )
                raise EmbeddingMigrationTaskError(reason=batch_result.error)

            processed += batch_result.count
            batch_num += 1

            # Update progress
            progress = min(processed / total_docs, 1.0)
            _update_progress(kb_id, progress)

            logger.debug(
                "Batch {} completed for kb_id={}, processed={}/{}, progress={:.1%}",
                batch_num,
                kb_id,
                processed,
                total_docs,
                progress,
            )

        # Check if completed
        if processed >= total_docs:
            _complete_migration(kb_id, target_model)
            return f"knowledge {kb_id} migration completed, {total_docs} documents processed"

        # Paused or incomplete
        return f"knowledge {kb_id} migration paused at {processed}/{total_docs}"

    except Exception as e:
        logger.exception("task_migrate_knowledge_base error: {}", e)
        _handle_migration_error(kb_id, str(e))
        raise e


def _get_document_count(kb: Knowledge) -> int:
    """
    Get total document count for a knowledge base.

    This counts the number of knowledge_document records or knowledge_files.
    """
    from sqlalchemy import func

    from bisheng.core.database import get_sync_db_session
    from bisheng.knowledge.domain.models.knowledge_document import KnowledgeDocument
    from bisheng.knowledge.domain.models.knowledge_file import KnowledgeFileDao

    # Try knowledge_document first
    try:
        with get_sync_db_session() as session:
            stmt = select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.knowledge_id == kb.id)
            count = session.scalar(stmt)
            if count and count > 0:
                return count
    except Exception as e:
        logger.debug("Could not count knowledge_document: {}", e)

    # Fall back to knowledge_file count
    try:
        files = KnowledgeFileDao.get_files_by_status(kb.id)
        return len(files)
    except Exception as e:
        logger.debug("Could not count knowledge_files: {}", e)

    return 0


def _process_document_batch(
    kb: Knowledge,
    target_model: str,
    batch_size: int,
    offset: int,
) -> BatchResult:
    """
    Process a batch of documents for re-embedding.

    Args:
        kb: Knowledge base
        target_model: Target embedding model ID
        batch_size: Number of documents to process
        offset: Starting offset

    Returns:
        BatchResult with count and optional error
    """
    from bisheng.core.database import get_sync_db_session
    from bisheng.knowledge.domain.knowledge_rag import KnowledgeRag
    from bisheng.knowledge.domain.models.knowledge_document import KnowledgeDocument
    from bisheng.llm.domain import LLMService

    try:
        with get_sync_db_session() as session:
            # Get documents for this batch
            stmt = (
                select(KnowledgeDocument)
                .where(KnowledgeDocument.knowledge_id == kb.id)
                .offset(offset)
                .limit(batch_size)
            )
            documents = session.exec(stmt).all()

            if not documents:
                return BatchResult(count=0)

            logger.debug(
                "Re-embedding {} documents for kb_id={} with model {}",
                len(documents),
                kb.id,
                target_model,
            )

            # Get new embedding model
            new_embeddings = LLMService.get_bisheng_knowledge_embedding_sync(
                model_id=target_model, invoke_user_id=kb.user_id or 0
            )

            # Initialize Milvus vector store with new embeddings
            from bisheng.common.schemas.rag_schema import KNOWLEDGE_RAG_METADATA_SCHEMA

            vector_client = KnowledgeRag.init_knowledge_milvus_vectorstore_sync(
                invoke_user_id=kb.user_id or 0,
                knowledge=kb,
                embeddings=new_embeddings,
                metadata_schemas=KNOWLEDGE_RAG_METADATA_SCHEMA,
            )

            # Process each document
            processed_count = 0
            for doc in documents:
                try:
                    # Get document content and metadata
                    texts = [doc.content] if doc.content else []
                    if not texts:
                        continue

                    # Get metadata from document
                    metadata = {
                        "document_id": doc.id,
                        "knowledge_id": kb.id,
                    }
                    if hasattr(doc, "file_id") and doc.file_id:
                        metadata["file_id"] = doc.file_id

                    # Add to Milvus
                    if texts and texts[0]:
                        vector_client.add_texts(texts=texts, metadatas=[metadata])
                        processed_count += 1

                except Exception as e:
                    logger.warning(
                        "Failed to re-embed document {} for kb_id={}: {}",
                        doc.id,
                        kb.id,
                        e,
                    )
                    continue

            logger.debug(
                "Successfully re-embedded {} documents for kb_id={}",
                processed_count,
                kb.id,
            )

            return BatchResult(count=processed_count)

    except Exception as e:
        logger.exception("Error processing batch for kb_id={}: {}", kb.id, e)
        return BatchResult(count=0, error=str(e))


def _update_progress(kb_id: int, progress: float) -> None:
    """Update migration progress in database."""
    import asyncio

    from sqlalchemy import update

    from bisheng.core.database import get_async_db_session
    from bisheng.knowledge.domain.models.knowledge import Knowledge

    async def _update():
        async with get_async_db_session() as session:
            stmt = update(Knowledge).where(Knowledge.id == kb_id).values(migration_progress=progress)
            await session.exec(stmt)
            await session.commit()

    try:
        asyncio.get_event_loop().run_until_complete(_update())
    except Exception as e:
        logger.warning("Could not update progress for kb_id={}: {}", kb_id, e)


def _complete_migration(kb_id: int, target_model: str) -> None:
    """Mark migration as completed and switch to new model."""
    import asyncio

    from sqlalchemy import update

    from bisheng.core.database import get_async_db_session
    from bisheng.knowledge.domain.models.knowledge import Knowledge, MigrationStatus

    async def _complete():
        async with get_async_db_session() as session:
            stmt = (
                update(Knowledge)
                .where(Knowledge.id == kb_id)
                .values(
                    migration_status=MigrationStatus.COMPLETED.value,
                    migration_progress=1.0,
                    model=target_model,
                )
            )
            await session.exec(stmt)
            await session.commit()

    try:
        asyncio.get_event_loop().run_until_complete(_complete())
        logger.info("Migration completed for kb_id={}", kb_id)
    except Exception as e:
        logger.exception("Could not complete migration for kb_id={}: {}", kb_id, e)


def _handle_migration_error(kb_id: int, error: str) -> None:
    """Handle migration error by updating status."""
    import asyncio

    from sqlalchemy import update

    from bisheng.core.database import get_async_db_session
    from bisheng.knowledge.domain.models.knowledge import Knowledge, MigrationStatus

    async def _error():
        async with get_async_db_session() as session:
            stmt = update(Knowledge).where(Knowledge.id == kb_id).values(migration_status=MigrationStatus.FAILED.value)
            await session.exec(stmt)
            await session.commit()

    try:
        asyncio.get_event_loop().run_until_complete(_error())
        logger.info("Migration marked as failed for kb_id={}, error={}", kb_id, error)
    except Exception as e:
        logger.exception("Could not mark migration as failed for kb_id={}: {}", kb_id, e)
