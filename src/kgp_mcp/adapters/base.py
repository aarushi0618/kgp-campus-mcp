"""Abstract SourceAdapter interface — all data source integrations implement this."""
from abc import ABC, abstractmethod
from typing import Any

from kgp_mcp.models.campus_entity import CampusEntity


class SourceAdapter(ABC):
    """Base class for all campus data source adapters.

    Every adapter must implement fetch() and parse().
    Domain services depend ONLY on this interface, never on concrete implementations.
    """

    @abstractmethod
    async def fetch(self) -> Any:
        """Fetch raw data from the external source.

        Returns:
            Raw data (HTML string, PDF bytes, JSON dict, etc.)

        Raises:
            httpx.HTTPError: On network failure after retries.
        """
        ...

    @abstractmethod
    async def parse(self, raw: Any) -> list[CampusEntity]:
        """Parse raw data into normalized CampusEntity objects.

        Args:
            raw: The output of fetch().

        Returns:
            List of normalized CampusEntity objects.
        """
        ...

    @abstractmethod
    def to_campus_entity(self, parsed: Any) -> CampusEntity:
        """Convert a single parsed item into a CampusEntity.

        Args:
            parsed: A single item from the parse() output.

        Returns:
            A normalized CampusEntity.
        """
        ...

    async def get_entities(self) -> list[CampusEntity]:
        """Convenience method: fetch, parse, and return entities."""
        raw = await self.fetch()
        return await self.parse(raw)