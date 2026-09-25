"""Embedding query configuration service.

F050: Manages tenant-level embedding query settings:
- embedding_query_strategy: new_only | old_only | dual_rrf
- show_embedding_details: boolean
"""

import json
from typing import Any

from loguru import logger

from bisheng.common.errcode.knowledge_migration import EmbeddingMigrationStrategyError
from bisheng.common.models.config import ConfigDao, ConfigKeyEnum
from bisheng.llm.domain.services.embedding_router import EmbeddingQueryStrategy


class EmbeddingConfigService:
    """Service for managing embedding query configuration."""

    DEFAULT_STRATEGY = EmbeddingQueryStrategy.DUAL_RRF
    DEFAULT_SHOW_DETAILS = False

    @classmethod
    async def get_embedding_query_strategy(cls, tenant_id: int | None = None) -> EmbeddingQueryStrategy:
        """
        Get the embedding query strategy for a tenant.

        Returns:
            EmbeddingQueryStrategy enum value
        """
        # The strategy is tenant-agnostic in current implementation
        # In a multi-tenant scenario, this would read from tenant-specific config
        try:
            config = await ConfigDao.aget_config_by_key(ConfigKeyEnum.EMBEDDING_QUERY_STRATEGY.value)
            if config and config.value:
                value = json.loads(config.value).get("strategy", cls.DEFAULT_STRATEGY.value)
                return EmbeddingQueryStrategy(value)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Invalid embedding strategy config: {}", e)
        return cls.DEFAULT_STRATEGY

    @classmethod
    async def set_embedding_query_strategy(
        cls,
        strategy: str,
        tenant_id: int | None = None,
    ) -> EmbeddingQueryStrategy:
        """
        Set the embedding query strategy for a tenant.

        Args:
            strategy: One of "new_only", "old_only", "dual_rrf"

        Returns:
            The validated strategy

        Raises:
            EmbeddingMigrationStrategyError: If strategy is invalid
        """
        # Validate strategy
        try:
            validated = EmbeddingQueryStrategy(strategy)
        except ValueError:
            raise EmbeddingMigrationStrategyError(strategy=strategy)

        value_json = json.dumps({"strategy": validated.value})
        await ConfigDao.insert_or_update_config(
            key=ConfigKeyEnum.EMBEDDING_QUERY_STRATEGY.value,
            value=value_json,
        )

        logger.info("Set embedding query strategy to {}", validated.value)
        return validated

    @classmethod
    async def get_show_embedding_details(cls, tenant_id: int | None = None) -> bool:
        """
        Get whether to show embedding details in chat.

        Returns:
            True if details should be shown
        """
        try:
            config = await ConfigDao.aget_config_by_key(ConfigKeyEnum.SHOW_EMBEDDING_DETAILS.value)
            if config and config.value:
                return json.loads(config.value).get("show", cls.DEFAULT_SHOW_DETAILS)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Invalid show_embedding_details config: {}", e)
        return cls.DEFAULT_SHOW_DETAILS

    @classmethod
    async def set_show_embedding_details(
        cls,
        show: bool,
        tenant_id: int | None = None,
    ) -> bool:
        """
        Set whether to show embedding details in chat.

        Args:
            show: True to show details, False to hide

        Returns:
            The value that was set
        """
        value_json = json.dumps({"show": show})
        await ConfigDao.insert_or_update_config(
            key=ConfigKeyEnum.SHOW_EMBEDDING_DETAILS.value,
            value=value_json,
        )

        logger.info("Set show_embedding_details to {}", show)
        return show

    @classmethod
    async def get_embedding_config(cls, tenant_id: int | None = None) -> dict[str, Any]:
        """
        Get all embedding-related configuration.

        Returns:
            Dict with strategy and show_details values
        """
        return {
            "strategy": (await cls.get_embedding_query_strategy(tenant_id)).value,
            "show_details": await cls.get_show_embedding_details(tenant_id),
        }
