"""Embedding model migration API endpoints.

F050: Knowledge base embedding model migration management endpoints.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from bisheng.common.dependencies.user_deps import UserPayload
from bisheng.common.errcode.knowledge_migration import (
    EmbeddingMigrationLockError,
    EmbeddingMigrationNotFoundError,
    EmbeddingMigrationUnlockError,
)
from bisheng.common.schemas.api import resp_200
from bisheng.knowledge.domain.services.migration_service import KnowledgeMigrationService
from bisheng.worker.knowledge.embedding_migration_tasks import task_migrate_knowledge_base

# Build router
router = APIRouter(prefix="/knowledge", tags=["Knowledge Migration"])


class MigrationStartRequest(BaseModel):
    """Request to start a migration."""

    target_model: str
    strategy: str = "immediate"  # "immediate" or "delayed"


class MigrationStatusResponse(BaseModel):
    """Migration status response."""

    kb_id: int
    kb_name: str
    current_model: str | None
    target_model: str | None
    migration_status: str
    migration_progress: float
    locked_at: str | None
    locked_by: str | None
    locked_model: str | None


class MigrationSummaryResponse(BaseModel):
    """Migration summary for all knowledge bases in tenant."""

    items: list[MigrationStatusResponse]
    total: int


@router.get("/migration/summary")
async def get_migration_summary(
    user: UserPayload = Depends(UserPayload.get_login_user),
) -> resp_200:
    """
    Get migration status summary for all knowledge bases in the tenant.

    Returns:
        List of all knowledge bases with their migration status.
    """
    status_list = await KnowledgeMigrationService.list_all_kb_migration_status(
        tenant_id=user.tenant_id,
    )
    return resp_200(data=status_list)


@router.get("/{kb_id}/migration")
async def get_kb_migration_status(
    kb_id: int,
    user: UserPayload = Depends(UserPayload.get_login_user),
) -> resp_200:
    """
    Get migration status for a specific knowledge base.

    Args:
        kb_id: Knowledge base ID

    Returns:
        Migration status details
    """
    try:
        status = await KnowledgeMigrationService.get_migration_status(kb_id)
        return resp_200(data=status)
    except EmbeddingMigrationNotFoundError:
        return EmbeddingMigrationNotFoundError.return_resp()


@router.post("/{kb_id}/migration/start")
async def start_migration(
    kb_id: int,
    req: MigrationStartRequest,
    user: UserPayload = Depends(UserPayload.get_login_user),
) -> resp_200:
    """
    Start embedding model migration for a knowledge base.

    Args:
        kb_id: Knowledge base ID
        req: Migration start request with target_model and strategy

    Returns:
        Updated migration status
    """
    try:
        status = await KnowledgeMigrationService.start_migration(
            kb_id=kb_id,
            target_model=req.target_model,
            strategy=req.strategy,
            user_name=user.user_name,
        )

        # If immediate strategy, dispatch Celery task
        if req.strategy == "immediate":
            task_migrate_knowledge_base.delay(kb_id, req.target_model)

        return resp_200(data=status)
    except EmbeddingMigrationNotFoundError:
        return EmbeddingMigrationNotFoundError.return_resp()
    except Exception as e:
        return resp_200(code=500, msg=str(e))


@router.post("/{kb_id}/migration/pause")
async def pause_migration(
    kb_id: int,
    user: UserPayload = Depends(UserPayload.get_login_user),
) -> resp_200:
    """
    Pause an in-progress migration.

    Args:
        kb_id: Knowledge base ID

    Returns:
        Updated migration status
    """
    try:
        status = await KnowledgeMigrationService.pause_migration(kb_id)
        return resp_200(data=status)
    except EmbeddingMigrationNotFoundError:
        return EmbeddingMigrationNotFoundError.return_resp()
    except Exception as e:
        return resp_200(code=500, msg=str(e))


@router.post("/{kb_id}/migration/complete")
async def force_complete_migration(
    kb_id: int,
    user: UserPayload = Depends(UserPayload.get_login_user),
) -> resp_200:
    """
    Force complete a migration.

    Args:
        kb_id: Knowledge base ID

    Returns:
        Updated migration status
    """
    try:
        status = await KnowledgeMigrationService.force_complete_migration(kb_id)
        return resp_200(data=status)
    except EmbeddingMigrationNotFoundError:
        return EmbeddingMigrationNotFoundError.return_resp()
    except Exception as e:
        return resp_200(code=500, msg=str(e))


@router.post("/{kb_id}/migration/lock")
async def lock_knowledge_base(
    kb_id: int,
    user: UserPayload = Depends(UserPayload.get_login_user),
) -> resp_200:
    """
    Lock a knowledge base at its current embedding model.

    Args:
        kb_id: Knowledge base ID

    Returns:
        Updated migration status
    """
    try:
        status = await KnowledgeMigrationService.lock_knowledge_base(
            kb_id=kb_id,
            user_name=user.user_name,
        )
        return resp_200(data=status)
    except EmbeddingMigrationNotFoundError:
        return EmbeddingMigrationNotFoundError.return_resp()
    except EmbeddingMigrationLockError:
        return EmbeddingMigrationLockError.return_resp()
    except Exception as e:
        return resp_200(code=500, msg=str(e))


@router.post("/{kb_id}/migration/unlock")
async def unlock_knowledge_base(
    kb_id: int,
    user: UserPayload = Depends(UserPayload.get_login_user),
) -> resp_200:
    """
    Unlock a knowledge base.

    Args:
        kb_id: Knowledge base ID

    Returns:
        Updated migration status
    """
    try:
        status = await KnowledgeMigrationService.unlock_knowledge_base(kb_id)
        return resp_200(data=status)
    except EmbeddingMigrationNotFoundError:
        return EmbeddingMigrationNotFoundError.return_resp()
    except EmbeddingMigrationUnlockError:
        return EmbeddingMigrationUnlockError.return_resp()
    except Exception as e:
        return resp_200(code=500, msg=str(e))
