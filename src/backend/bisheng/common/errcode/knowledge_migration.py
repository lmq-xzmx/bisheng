"""Embedding model migration error codes.

Module code: 140
Error code range: 14001-14019
"""

from .base import BaseErrorCode


class EmbeddingMigrationNotFoundError(BaseErrorCode):
    """Knowledge base migration record not found."""

    Code: int = 14001
    Msg: str = "Knowledge base migration record not found"


class EmbeddingMigrationAlreadyLockedError(BaseErrorCode):
    """Knowledge base is already locked at current embedding model."""

    Code: int = 14002
    Msg: str = "Knowledge base is already locked at current embedding model"


class EmbeddingMigrationTargetUnavailableError(BaseErrorCode):
    """Target embedding model is not available."""

    Code: int = 14003
    Msg: str = "Target embedding model is not available"


class EmbeddingMigrationLockedKBError(BaseErrorCode):
    """Cannot migrate a locked knowledge base."""

    Code: int = 14004
    Msg: str = "Cannot migrate a locked knowledge base, please unlock it first"


class EmbeddingMigrationInProgressError(BaseErrorCode):
    """Migration is already in progress."""

    Code: int = 14005
    Msg: str = "Migration is already in progress for this knowledge base"


class EmbeddingMigrationInvalidStatusError(BaseErrorCode):
    """Invalid migration status for the requested operation."""

    Code: int = 14006
    Msg: str = "Invalid migration status: {status}"


class EmbeddingMigrationProgressError(BaseErrorCode):
    """Failed to update migration progress."""

    Code: int = 14007
    Msg: str = "Failed to update migration progress"


class EmbeddingMigrationTaskError(BaseErrorCode):
    """Migration task execution failed."""

    Code: int = 14008
    Msg: str = "Migration task failed: {reason}"


class EmbeddingMigrationCancelError(BaseErrorCode):
    """Failed to cancel migration."""

    Code: int = 14009
    Msg: str = "Failed to cancel migration task"


class EmbeddingMigrationUnlockError(BaseErrorCode):
    """Failed to unlock knowledge base."""

    Code: int = 14010
    Msg: str = "Failed to unlock knowledge base"


class EmbeddingMigrationLockError(BaseErrorCode):
    """Failed to lock knowledge base."""

    Code: int = 14011
    Msg: str = "Failed to lock knowledge base at current embedding model"


class EmbeddingMigrationStrategyError(BaseErrorCode):
    """Invalid embedding query strategy."""

    Code: int = 14012
    Msg: str = "Invalid embedding query strategy: {strategy}. Valid values: new_only, old_only, dual_rrf"


class EmbeddingMigrationLargeKBError(BaseErrorCode):
    """Knowledge base is too large for immediate migration."""

    Code: int = 14013
    Msg: str = (
        "Knowledge base has {doc_count} documents, estimated migration time: {estimated_time}. "
        "Please confirm to proceed with migration."
    )


class EmbeddingMigrationServiceUnavailableError(BaseErrorCode):
    """Embedding service is unavailable."""

    Code: int = 14014
    Msg: str = "Embedding service is currently unavailable, please try again later"


class EmbeddingMigrationOldModelUnavailableError(BaseErrorCode):
    """Old embedding model is unavailable (for locked KB scenario)."""

    Code: int = 14015
    Msg: str = "The locked embedding model is no longer available. Please unlock and select a new model"


class EmbeddingMigrationNoTargetModelError(BaseErrorCode):
    """No target model specified for migration."""

    Code: int = 14016
    Msg: str = "No target embedding model specified for migration"


class EmbeddingMigrationAlreadyCompletedError(BaseErrorCode):
    """Migration has already been completed."""

    Code: int = 14017
    Msg: str = "Migration has already been completed for this knowledge base"


class EmbeddingMigrationForceCompleteError(BaseErrorCode):
    """Failed to force complete migration."""

    Code: int = 14018
    Msg: str = "Failed to force complete migration: {reason}"


class EmbeddingMigrationPauseError(BaseErrorCode):
    """Failed to pause migration."""

    Code: int = 14019
    Msg: str = "Failed to pause migration task"
