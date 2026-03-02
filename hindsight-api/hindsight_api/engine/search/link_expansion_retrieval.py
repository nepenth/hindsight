"""
Link Expansion graph retrieval.

Expands from semantic/temporal seeds through three parallel, first-class signals
stored in memory_links:

1. Entity links  — precomputed co-occurrence graph (created at retain time, bounded to
                   MAX_LINKS_PER_ENTITY per entity). Score = number of distinct shared
                   entities between the seed set and each candidate.
2. Semantic links — precomputed kNN graph (each new fact linked to its top-5 most
                    similar existing facts at insert time, similarity >= 0.7). Checked
                    in both directions since the graph is not symmetric. Score = weight.
3. Causal links  — explicit causal chains (causes/caused_by/enables/prevents).
                   Score = weight + 1.0 (boosted as highest-quality signal).

All three signals are bounded at retain time, so no LATERAL fan-out caps are needed
at query time. Each expansion is a simple aggregation over a small result set.
"""

import logging
import math
import time

from ..db_utils import acquire_with_retry
from ..memory_engine import fq_table
from .graph_retrieval import GraphRetriever
from .tags import TagsMatch, filter_results_by_tags
from .types import MPFPTimings, RetrievalResult

logger = logging.getLogger(__name__)


async def _find_semantic_seeds(
    conn,
    query_embedding_str: str,
    bank_id: str,
    fact_type: str,
    limit: int = 20,
    threshold: float = 0.3,
    tags: list[str] | None = None,
    tags_match: TagsMatch = "any",
) -> list[RetrievalResult]:
    """Find semantic seeds via embedding search."""
    from .tags import build_tags_where_clause_simple

    tags_clause = build_tags_where_clause_simple(tags, 6, match=tags_match)
    params = [query_embedding_str, bank_id, fact_type, threshold, limit]
    if tags:
        params.append(tags)

    rows = await conn.fetch(
        f"""
        SELECT id, text, context, event_date, occurred_start, occurred_end,
               mentioned_at, fact_type, document_id, chunk_id, tags,
               1 - (embedding <=> $1::vector) AS similarity
        FROM {fq_table("memory_units")}
        WHERE bank_id = $2
          AND embedding IS NOT NULL
          AND fact_type = $3
          AND (1 - (embedding <=> $1::vector)) >= $4
          {tags_clause}
        ORDER BY embedding <=> $1::vector
        LIMIT $5
        """,
        *params,
    )
    return [RetrievalResult.from_db_row(dict(r)) for r in rows]


class LinkExpansionRetriever(GraphRetriever):
    """
    Graph retrieval via direct link expansion from seeds.

    Runs three parallel expansions through precomputed memory_links: entity
    co-occurrence, semantic kNN, and causal chains.  All bounded at retain time.
    """

    def __init__(
        self,
        causal_weight_threshold: float = 0.3,
    ):
        """
        Args:
            causal_weight_threshold: Minimum weight for causal links to follow.
        """
        self.causal_weight_threshold = causal_weight_threshold

    @property
    def name(self) -> str:
        return "link_expansion"

    async def retrieve(
        self,
        pool,
        query_embedding_str: str,
        bank_id: str,
        fact_type: str,
        budget: int,
        query_text: str | None = None,
        semantic_seeds: list[RetrievalResult] | None = None,
        temporal_seeds: list[RetrievalResult] | None = None,
        adjacency=None,
        tags: list[str] | None = None,
        tags_match: TagsMatch = "any",
    ) -> tuple[list[RetrievalResult], MPFPTimings | None]:
        """
        Retrieve facts by expanding links from seeds.

        Args:
            pool: Database connection pool
            query_embedding_str: Query embedding as string
            bank_id: Memory bank ID
            fact_type: Fact type to filter
            budget: Maximum results to return
            query_text: Original query text (unused)
            semantic_seeds: Pre-computed semantic entry points
            temporal_seeds: Pre-computed temporal entry points
            adjacency: Unused, kept for interface compatibility
            tags: Optional list of tags for visibility filtering

        Returns:
            Tuple of (results, timings)
        """
        start_time = time.time()
        timings = MPFPTimings(fact_type=fact_type)

        async with acquire_with_retry(pool) as conn:
            # Find seeds if not provided
            if semantic_seeds:
                all_seeds = list(semantic_seeds)
            else:
                seeds_start = time.time()
                all_seeds = await _find_semantic_seeds(
                    conn,
                    query_embedding_str,
                    bank_id,
                    fact_type,
                    limit=20,
                    threshold=0.3,
                    tags=tags,
                    tags_match=tags_match,
                )
                timings.seeds_time = time.time() - seeds_start
                logger.debug(
                    f"[LinkExpansion] Found {len(all_seeds)} semantic seeds for fact_type={fact_type} "
                    f"(tags={tags}, tags_match={tags_match})"
                )

            if temporal_seeds:
                all_seeds.extend(temporal_seeds)

            if not all_seeds:
                return [], timings

            seed_ids = list({s.id for s in all_seeds})
            timings.pattern_count = len(seed_ids)

            query_start = time.time()

            # ── 1. Entity expansion ──────────────────────────────────────────────
            # For observations: traverse source_memory_ids → world facts → entities
            # → other world facts → their observations. Observations don't have
            # direct entity links in memory_links (created by consolidation, not retain).
            #
            # For all other fact types: use the precomputed entity co-occurrence links
            # in memory_links. Score = number of distinct entities linking this
            # candidate to the seed set. Links are bidirectional, so only outgoing
            # direction is needed.
            if fact_type == "observation":
                debug_sources = await conn.fetch(
                    f"""
                    SELECT id, source_memory_ids
                    FROM {fq_table("memory_units")}
                    WHERE id = ANY($1::uuid[])
                    """,
                    seed_ids,
                )
                source_ids_found = []
                for row in debug_sources:
                    if row["source_memory_ids"]:
                        source_ids_found.extend(row["source_memory_ids"])
                logger.debug(
                    f"[LinkExpansion] observation graph: {len(seed_ids)} seeds, "
                    f"{len(source_ids_found)} source_memory_ids found"
                )

                entity_rows = await conn.fetch(
                    f"""
                    WITH seed_sources AS (
                        SELECT DISTINCT unnest(source_memory_ids) AS source_id
                        FROM {fq_table("memory_units")}
                        WHERE id = ANY($1::uuid[])
                          AND source_memory_ids IS NOT NULL
                    ),
                    source_entities AS (
                        SELECT DISTINCT ue.entity_id
                        FROM seed_sources ss
                        JOIN {fq_table("unit_entities")} ue ON ss.source_id = ue.unit_id
                    ),
                    all_connected_sources AS (
                        SELECT DISTINCT other_ue.unit_id AS source_id
                        FROM source_entities se
                        JOIN {fq_table("unit_entities")} other_ue ON se.entity_id = other_ue.entity_id
                    )
                    SELECT
                        mu.id, mu.text, mu.context, mu.event_date, mu.occurred_start,
                        mu.occurred_end, mu.mentioned_at,
                        mu.fact_type, mu.document_id, mu.chunk_id, mu.tags,
                        COUNT(DISTINCT cs.source_id)::float AS score
                    FROM all_connected_sources cs
                    JOIN {fq_table("memory_units")} mu
                        ON mu.source_memory_ids @> ARRAY[cs.source_id]
                    WHERE mu.fact_type = 'observation'
                      AND mu.id != ALL($1::uuid[])
                    GROUP BY mu.id
                    ORDER BY score DESC
                    LIMIT $2
                    """,
                    seed_ids,
                    budget,
                )
                logger.debug(f"[LinkExpansion] observation graph: found {len(entity_rows)} connected observations")
            else:
                # Precomputed entity links are bidirectional and already capped at
                # MAX_LINKS_PER_ENTITY=50 per entity at retain time. Score = number of
                # distinct entities tying each candidate to the seed set — equivalent
                # to the old unit_entities co-occurrence count but O(links) not O(fan-out).
                entity_rows = await conn.fetch(
                    f"""
                    SELECT
                        mu.id, mu.text, mu.context, mu.event_date, mu.occurred_start,
                        mu.occurred_end, mu.mentioned_at,
                        mu.fact_type, mu.document_id, mu.chunk_id, mu.tags,
                        COUNT(DISTINCT ml.entity_id)::float AS score
                    FROM {fq_table("memory_links")} ml
                    JOIN {fq_table("memory_units")} mu ON mu.id = ml.to_unit_id
                    WHERE ml.from_unit_id = ANY($1::uuid[])
                      AND ml.link_type = 'entity'
                      AND mu.fact_type = $2
                      AND mu.id != ALL($1::uuid[])
                    GROUP BY mu.id
                    ORDER BY score DESC
                    LIMIT $3
                    """,
                    seed_ids,
                    fact_type,
                    budget,
                )

            # ── 2. Semantic expansion ────────────────────────────────────────────
            # Semantic links are a bank-wide kNN graph: each fact is linked to its
            # top-5 most similar facts at insert time (similarity >= 0.7). The graph
            # is NOT symmetric — A→B exists when B was already in the bank when A was
            # inserted, but B→A only exists if A was there when B was inserted.
            # Checking both directions surfaces facts that point TO seeds (inserted
            # after seeds and found them as nearest neighbors) as well as facts the
            # seeds point to (their nearest neighbors at the time seeds were inserted).
            semantic_rows = await conn.fetch(
                f"""
                WITH outgoing AS (
                    -- Facts the seeds are similar to (seeds → their kNN at insert time)
                    SELECT
                        mu.id, mu.text, mu.context, mu.event_date, mu.occurred_start,
                        mu.occurred_end, mu.mentioned_at,
                        mu.fact_type, mu.document_id, mu.chunk_id, mu.tags,
                        ml.weight
                    FROM {fq_table("memory_links")} ml
                    JOIN {fq_table("memory_units")} mu ON mu.id = ml.to_unit_id
                    WHERE ml.from_unit_id = ANY($1::uuid[])
                      AND ml.link_type = 'semantic'
                      AND mu.fact_type = $2
                      AND mu.id != ALL($1::uuid[])
                ),
                incoming AS (
                    -- Facts that consider seeds as their nearest neighbor (inserted after seeds)
                    SELECT
                        mu.id, mu.text, mu.context, mu.event_date, mu.occurred_start,
                        mu.occurred_end, mu.mentioned_at,
                        mu.fact_type, mu.document_id, mu.chunk_id, mu.tags,
                        ml.weight
                    FROM {fq_table("memory_links")} ml
                    JOIN {fq_table("memory_units")} mu ON mu.id = ml.from_unit_id
                    WHERE ml.to_unit_id = ANY($1::uuid[])
                      AND ml.link_type = 'semantic'
                      AND mu.fact_type = $2
                      AND mu.id != ALL($1::uuid[])
                )
                SELECT
                    id, text, context, event_date, occurred_start,
                    occurred_end, mentioned_at,
                    fact_type, document_id, chunk_id, tags,
                    MAX(weight) AS score
                FROM (SELECT * FROM outgoing UNION ALL SELECT * FROM incoming) combined
                GROUP BY id, text, context, event_date, occurred_start,
                         occurred_end, mentioned_at,
                         fact_type, document_id, chunk_id, tags
                ORDER BY score DESC
                LIMIT $3
                """,
                seed_ids,
                fact_type,
                budget,
            )

            # ── 3. Causal expansion ──────────────────────────────────────────────
            # Explicit causal chains from seeds. Rare in practice, high signal when
            # present. Score = weight ∈ [0, 1], combined additively with other signals.
            causal_rows = await conn.fetch(
                f"""
                SELECT DISTINCT ON (mu.id)
                    mu.id, mu.text, mu.context, mu.event_date, mu.occurred_start,
                    mu.occurred_end, mu.mentioned_at,
                    mu.fact_type, mu.document_id, mu.chunk_id, mu.tags,
                    ml.weight AS score
                FROM {fq_table("memory_links")} ml
                JOIN {fq_table("memory_units")} mu ON ml.to_unit_id = mu.id
                WHERE ml.from_unit_id = ANY($1::uuid[])
                  AND ml.link_type IN ('causes', 'caused_by', 'enables', 'prevents')
                  AND ml.weight >= $2
                  AND mu.fact_type = $3
                ORDER BY mu.id, ml.weight DESC
                LIMIT $4
                """,
                seed_ids,
                self.causal_weight_threshold,
                fact_type,
                budget,
            )

            timings.edge_load_time = time.time() - query_start
            timings.db_queries = 3
            timings.edge_count = len(entity_rows) + len(semantic_rows) + len(causal_rows)

        # Merge results with additive intra-score: entity + semantic + causal ∈ [0, 3].
        #
        # Entity score: tanh(count × 0.5) maps shared-entity count to [0, 1]:
        #   1 entity → 0.46,  2 → 0.76,  3 → 0.91,  4 → 0.96  (saturates naturally)
        # Semantic score: similarity weight, already ∈ [0.7, 1.0].
        # Causal score:   link weight, already ∈ [0, 1].
        #
        # Facts appearing in multiple signals accumulate higher scores, rewarding
        # convergent evidence. The outer RRF uses rank position from this sorted list.
        entity_scores: dict[str, float] = {}
        semantic_scores: dict[str, float] = {}
        causal_scores: dict[str, float] = {}
        row_map: dict[str, dict] = {}

        for row in entity_rows:
            fact_id = str(row["id"])
            entity_scores[fact_id] = math.tanh(row["score"] * 0.5)
            row_map[fact_id] = dict(row)

        for row in semantic_rows:
            fact_id = str(row["id"])
            semantic_scores[fact_id] = max(semantic_scores.get(fact_id, 0.0), row["score"])
            row_map.setdefault(fact_id, dict(row))

        for row in causal_rows:
            fact_id = str(row["id"])
            causal_scores[fact_id] = max(causal_scores.get(fact_id, 0.0), row["score"])
            row_map.setdefault(fact_id, dict(row))

        all_ids = set(entity_scores) | set(semantic_scores) | set(causal_scores)
        score_map = {
            fid: entity_scores.get(fid, 0.0) + semantic_scores.get(fid, 0.0) + causal_scores.get(fid, 0.0)
            for fid in all_ids
        }

        sorted_ids = sorted(score_map.keys(), key=lambda x: score_map[x], reverse=True)[:budget]
        rows = [row_map[fact_id] for fact_id in sorted_ids]

        results = []
        for row in rows:
            result = RetrievalResult.from_db_row(dict(row))
            result.activation = row["score"]
            results.append(result)

        if tags:
            results = filter_results_by_tags(results, tags, match=tags_match)

        timings.result_count = len(results)
        timings.traverse = time.time() - start_time

        logger.debug(
            f"LinkExpansion: {len(results)} results from {len(seed_ids)} seeds "
            f"in {timings.traverse * 1000:.1f}ms (query: {timings.edge_load_time * 1000:.1f}ms)"
        )

        return results, timings
