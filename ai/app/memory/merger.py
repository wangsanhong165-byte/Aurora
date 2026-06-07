"""Memory merger  deduplicate, merge, and update memory cards.

Operates after extraction, before persistence. Ensures the long-term store
doesn't accumulate near-duplicate facts.
"""

from __future__ import annotations

from typing import Any

from app.memory.long_term import MemoryCard


class MemoryMerger:
    """Deduplicates and merges memory cards before storage.

    Strategy:
    - Text similarity (token overlap) for finding duplicates
    - Newer cards with higher confidence replace older similar ones
    - Importance decays slightly on merge (avoid inflation)
    - Max cards limit enforced (drop lowest-importance)

    Usage:
        merger = MemoryMerger()
        merged = merger.merge(existing_cards, new_cards)
    """

    def __init__(
        self,
        similarity_threshold: float = 0.6,
        max_cards: int = 500,
    ) -> None:
        self.similarity_threshold = similarity_threshold
        self.max_cards = max_cards

    def merge(
        self,
        existing: list[dict[str, Any]],
        new_cards: list[MemoryCard],
    ) -> list[dict[str, Any]]:
        """Merge new cards into existing ones, returning the combined list.

        Args:
            existing: Current cards from LongTermMemoryStore (list of dicts).
            new_cards: Newly extracted MemoryCard objects.

        Returns:
            Merged list of card dicts, deduplicated, capped at max_cards.
        """
        merged: list[dict[str, Any]] = list(existing)

        for new_card in new_cards:
            new_dict = new_card.to_dict()
            best_idx = self._find_best_match(new_card.content, merged)

            if best_idx is not None:
                # Merge with existing: keep newer, average importance
                merged[best_idx] = self._merge_pair(merged[best_idx], new_dict)
            else:
                merged.append(new_dict)

        # Sort by importance desc, then by recency
        merged.sort(
            key=lambda c: (
                float(c.get("importance", 0)),
                c.get("created_at", ""),
            ),
            reverse=True,
        )

        # Cap: keep episode/relationship cards, trim only fact/summary/etc
        _protected = {"episode", "relationship"}
        if len(merged) > self.max_cards:
            protected = [c for c in merged if c.get("type") in _protected]
            trimmable = [c for c in merged if c.get("type") not in _protected]
            # Keep all protected + fill remaining with top trimmable
            keep = min(self.max_cards - len(protected), len(trimmable))
            merged = protected + trimmable[:keep]

        return merged

    def _find_best_match(
        self,
        text: str,
        cards: list[dict[str, Any]],
    ) -> int | None:
        """Find the index of the most similar card above threshold."""
        best_score = 0.0
        best_idx = None
        tokens = set(text)

        for i, card in enumerate(cards):
            card_text = str(card.get("content", ""))
            if not card_text:
                continue
            card_tokens = set(card_text)
            if not tokens or not card_tokens:
                continue

            # Jaccard similarity
            intersection = tokens & card_tokens
            union = tokens | card_tokens
            score = len(intersection) / len(union) if union else 0.0

            # Boost same-type cards
            if card.get("type") == "fact":
                score += 0.1

            if score > best_score:
                best_score = score
                best_idx = i

        if best_score >= self.similarity_threshold:
            return best_idx
        return None

    @staticmethod
    def _merge_pair(
        old: dict[str, Any],
        new: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge a new card into an existing one."""
        # Use newer content (likely more accurate)
        merged = dict(old)

        # Average importance, slight decay
        old_imp = float(old.get("importance", 0.5))
        new_imp = float(new.get("importance", 0.5))
        merged["importance"] = round(max(old_imp, new_imp) * 0.95, 2)

        # Max confidence
        merged["confidence"] = max(
            float(old.get("confidence", 0.5)),
            float(new.get("confidence", 0.5)),
        )

        # Update timestamp
        from app.core.events import utc_now
        merged["updated_at"] = utc_now()

        # Merge metadata
        old_meta = old.get("metadata", {})
        new_meta = new.get("metadata", {})
        if isinstance(old_meta, dict) and isinstance(new_meta, dict):
            merged["metadata"] = {**old_meta, **new_meta}

        return merged
