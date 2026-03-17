"""LangGraph BaseStore adapter backed by Hindsight.

Maps LangGraph's key-value store interface to Hindsight's memory operations.
Namespace tuples are joined to form bank IDs, and values are stored/retrieved
via retain/recall.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from hindsight_client import Hindsight
from langgraph.store.base import BaseStore, GetOp, Item, ListNamespacesOp, PutOp, Result, SearchItem, SearchOp

from .config import get_config
from .errors import HindsightError
from .tools import _resolve_client

logger = logging.getLogger(__name__)


def _namespace_to_bank_id(namespace: tuple[str, ...]) -> str:
    """Convert a namespace tuple to a Hindsight bank ID.

    Uses "." as separator since "/" is not valid in Hindsight bank IDs
    (interpreted as URL path segments).
    """
    return ".".join(namespace) if namespace else "default"


def _make_item(namespace: tuple[str, ...], key: str, value: dict, created_at: datetime | None = None) -> Item:
    """Create a LangGraph Item from Hindsight data."""
    now = datetime.now(timezone.utc)
    return Item(
        namespace=namespace,
        key=key,
        value=value,
        created_at=created_at or now,
        updated_at=now,
    )


def _make_search_item(
    namespace: tuple[str, ...], key: str, value: dict, score: float, created_at: datetime | None = None
) -> SearchItem:
    """Create a LangGraph SearchItem from Hindsight recall results."""
    now = datetime.now(timezone.utc)
    return SearchItem(
        namespace=namespace,
        key=key,
        value=value,
        score=score,
        created_at=created_at or now,
        updated_at=now,
    )


class HindsightStore(BaseStore):
    """LangGraph BaseStore implementation backed by Hindsight.

    Maps LangGraph's namespace/key-value model to Hindsight memory banks:
    - Namespace tuples are joined with "/" to form bank IDs
    - ``put()`` stores values via Hindsight retain with the key as document_id
    - ``search()`` uses Hindsight recall for semantic search
    - ``get()`` uses recall with the key as a targeted query

    This enables LangGraph's built-in memory patterns (cross-thread memory,
    semantic search) to be backed by Hindsight's memory engine.

    Example::

        from hindsight_client import Hindsight
        from hindsight_langgraph import HindsightStore

        store = HindsightStore(client=Hindsight(base_url="http://localhost:8888"))
        graph = builder.compile(checkpointer=checkpointer, store=store)
    """

    def __init__(
        self,
        *,
        client: Hindsight | None = None,
        hindsight_api_url: str | None = None,
        api_key: str | None = None,
        tags: list[str] | None = None,
    ):
        self._client = _resolve_client(client, hindsight_api_url, api_key)
        self._tags = tags
        # Track known namespaces for list_namespaces
        self._known_namespaces: set[tuple[str, ...]] = set()
        # Track banks that have been created to avoid repeated create calls
        self._created_banks: set[str] = set()

    def batch(self, ops: Iterable[GetOp | PutOp | SearchOp | ListNamespacesOp]) -> list[Result]:
        raise NotImplementedError("Use abatch() for async operation.")

    async def abatch(self, ops: Iterable[GetOp | PutOp | SearchOp | ListNamespacesOp]) -> list[Result]:
        results: list[Result] = []
        for op in ops:
            if isinstance(op, GetOp):
                results.append(await self._handle_get(op))
            elif isinstance(op, PutOp):
                await self._handle_put(op)
                results.append(None)
            elif isinstance(op, SearchOp):
                results.append(await self._handle_search(op))
            elif isinstance(op, ListNamespacesOp):
                results.append(await self._handle_list_namespaces(op))
            else:
                results.append(None)
        return results

    async def _handle_get(self, op: GetOp) -> Item | None:
        """Handle a get operation by recalling with the key as query."""
        bank_id = _namespace_to_bank_id(op.namespace)
        try:
            await self._ensure_bank(bank_id)
            response = await self._client.arecall(
                bank_id=bank_id,
                query=op.key,
                budget="low",
                max_tokens=1024,
            )
            if not response.results:
                return None

            # Find result matching the key via document_id or content
            for result in response.results:
                doc_id = getattr(result, "document_id", None)
                if doc_id == op.key:
                    value = _parse_value(result.text)
                    ts = getattr(result, "occurred_start", None)
                    return _make_item(op.namespace, op.key, value, created_at=ts)

            # If no exact match, return the top result
            result = response.results[0]
            value = _parse_value(result.text)
            ts = getattr(result, "occurred_start", None)
            return _make_item(op.namespace, op.key, value, created_at=ts)
        except Exception as e:
            logger.error(f"Store get failed for {op.namespace}/{op.key}: {e}")
            return None

    async def _ensure_bank(self, bank_id: str) -> None:
        """Create a bank if it hasn't been created yet in this session."""
        if bank_id in self._created_banks:
            return
        try:
            await self._client.acreate_bank(bank_id, name=bank_id)
        except Exception:
            # Bank may already exist — that's fine
            pass
        self._created_banks.add(bank_id)

    async def _handle_put(self, op: PutOp) -> None:
        """Handle a put operation by retaining the value."""
        bank_id = _namespace_to_bank_id(op.namespace)
        self._known_namespaces.add(op.namespace)

        if op.value is None:
            # LangGraph uses value=None as delete
            logger.debug(f"Delete not supported for {op.namespace}/{op.key}, skipping.")
            return

        try:
            await self._ensure_bank(bank_id)
            content = json.dumps(op.value) if isinstance(op.value, dict) else str(op.value)
            retain_kwargs: dict[str, Any] = {
                "bank_id": bank_id,
                "content": content,
                "document_id": op.key,
            }
            if self._tags:
                retain_kwargs["tags"] = self._tags
            await self._client.aretain(**retain_kwargs)
        except Exception as e:
            logger.error(f"Store put failed for {op.namespace}/{op.key}: {e}")
            raise HindsightError(f"Store put failed: {e}") from e

    async def _handle_search(self, op: SearchOp) -> list[SearchItem]:
        """Handle a search operation via Hindsight recall."""
        bank_id = _namespace_to_bank_id(op.namespace_prefix)
        query = op.query or "*"

        try:
            await self._ensure_bank(bank_id)
            recall_kwargs: dict[str, Any] = {
                "bank_id": bank_id,
                "query": query,
                "budget": "mid",
                "max_tokens": 4096,
            }
            response = await self._client.arecall(**recall_kwargs)
            if not response.results:
                return []

            items = []
            limit = op.limit or 10
            offset = op.offset or 0
            results_slice = response.results[offset : offset + limit]

            for i, result in enumerate(results_slice):
                value = _parse_value(result.text)
                doc_id = getattr(result, "document_id", None) or _content_key(result.text)
                score = 1.0 - (i * 0.01)  # Approximate score from rank position
                ts = getattr(result, "occurred_start", None)
                items.append(_make_search_item(op.namespace_prefix, doc_id, value, score=score, created_at=ts))

            # Apply filters if provided
            if op.filter:
                items = [item for item in items if _matches_filter(item.value, op.filter)]

            return items
        except Exception as e:
            logger.error(f"Store search failed for {op.namespace_prefix}: {e}")
            return []

    async def _handle_list_namespaces(self, op: ListNamespacesOp) -> list[tuple[str, ...]]:
        """List known namespaces. Limited to namespaces seen via put()."""
        namespaces = list(self._known_namespaces)

        if op.match_conditions:
            # Basic prefix matching
            filtered = []
            for ns in namespaces:
                match = True
                for cond in op.match_conditions:
                    prefix = cond.match_type == "prefix" if hasattr(cond, "match_type") else True
                    if prefix and not _namespace_starts_with(ns, cond.path):
                        match = False
                        break
                if match:
                    filtered.append(ns)
            namespaces = filtered

        if op.max_depth is not None:
            namespaces = [ns for ns in namespaces if len(ns) <= op.max_depth]

        limit = op.limit or 100
        offset = op.offset or 0
        return namespaces[offset : offset + limit]

    # Sync convenience methods that delegate to async

    def get(self, namespace: tuple[str, ...], key: str) -> Item | None:
        raise NotImplementedError("Use aget() for async operation.")

    async def aget(self, namespace: tuple[str, ...], key: str) -> Item | None:
        result = await self.abatch([GetOp(namespace=namespace, key=key)])
        return result[0]

    def put(self, namespace: tuple[str, ...], key: str, value: dict, index: bool | list[str] | None = None) -> None:
        raise NotImplementedError("Use aput() for async operation.")

    async def aput(
        self, namespace: tuple[str, ...], key: str, value: dict, index: bool | list[str] | None = None
    ) -> None:
        await self.abatch([PutOp(namespace=namespace, key=key, value=value)])

    def delete(self, namespace: tuple[str, ...], key: str) -> None:
        raise NotImplementedError("Use adelete() for async operation.")

    async def adelete(self, namespace: tuple[str, ...], key: str) -> None:
        await self.abatch([PutOp(namespace=namespace, key=key, value=None)])

    def search(
        self,
        namespace_prefix: tuple[str, ...],
        *,
        query: str | None = None,
        filter: dict | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[SearchItem]:
        raise NotImplementedError("Use asearch() for async operation.")

    async def asearch(
        self,
        namespace_prefix: tuple[str, ...],
        *,
        query: str | None = None,
        filter: dict | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[SearchItem]:
        result = await self.abatch(
            [SearchOp(namespace_prefix=namespace_prefix, query=query, filter=filter, limit=limit, offset=offset)]
        )
        return result[0]

    def list_namespaces(
        self,
        *,
        match_conditions: Sequence | None = None,
        max_depth: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[tuple[str, ...]]:
        raise NotImplementedError("Use alist_namespaces() for async operation.")

    async def alist_namespaces(
        self,
        *,
        match_conditions: Sequence | None = None,
        max_depth: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[tuple[str, ...]]:
        result = await self.abatch(
            [ListNamespacesOp(match_conditions=match_conditions, max_depth=max_depth, limit=limit, offset=offset)]
        )
        return result[0]


def _parse_value(text: str) -> dict:
    """Try to parse stored text as JSON, fallback to wrapping in a dict."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return {"text": text}


def _content_key(text: str) -> str:
    """Generate a stable key from content text."""
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _matches_filter(value: dict, filter_dict: dict) -> bool:
    """Check if a value dict matches all filter conditions."""
    for key, expected in filter_dict.items():
        if value.get(key) != expected:
            return False
    return True


def _namespace_starts_with(namespace: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    """Check if namespace starts with the given prefix."""
    if len(prefix) > len(namespace):
        return False
    return namespace[: len(prefix)] == prefix
