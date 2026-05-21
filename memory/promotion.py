"""Memory promotion engine.

Evaluates daily memories for promotion to permanent memory based on:
- Frequency score (0.4): how often the daily memory chunks were recalled
- Quiz score (0.4): accuracy on related quiz concepts
- Recency score (0.2): time decay with 30-day half-life

Promotion threshold: score >= 0.6 and recall_count >= 2.
"""

import math
import os
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from .store import MemoryIndexStore
from .daily import DailyMemoryManager

logger = logging.getLogger(__name__)

PROMOTE_THRESHOLD = 0.6
MIN_RECALL_COUNT = 2

# Scoring weights
W_FREQUENCY = 0.4
W_QUIZ = 0.4
W_RECENCY = 0.2

HALF_LIFE_DAYS = 30
DECAY_RATE = math.log(2) / HALF_LIFE_DAYS  # ~0.0231


@dataclass
class PromotionScore:
    daily_path: str
    date: str
    frequency_score: float = 0.0
    quiz_score: float = 0.0
    recency_score: float = 0.0
    total_score: float = 0.0
    recall_count: int = 0
    eligible: bool = False


class PromotionEngine:
    """Evaluates and executes daily-to-permanent memory promotion."""

    def __init__(self, workspace: str, base_dir: str = ".bobodan"):
        self.workspace = workspace
        self.base_dir = base_dir
        self.store = MemoryIndexStore(workspace, base_dir)
        self.daily = DailyMemoryManager(workspace, base_dir)

    def score(self, daily_path: str, date_str: str) -> PromotionScore:
        """Calculate promotion score for a daily memory file."""
        ps = PromotionScore(daily_path=daily_path, date=date_str)

        # Frequency: recall count / 5 (capped at 1.0)
        recall_count = self.store.get_recall_count(daily_path)
        ps.recall_count = recall_count
        ps.frequency_score = min(1.0, recall_count / 5)

        # Quiz: average accuracy on related concepts
        ps.quiz_score = self._get_quiz_score(date_str)

        # Recency: exponential decay
        try:
            mem_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - mem_date).days
            ps.recency_score = math.exp(-DECAY_RATE * max(0, age_days))
        except ValueError:
            ps.recency_score = 0.0

        # Total
        ps.total_score = (
            W_FREQUENCY * ps.frequency_score
            + W_QUIZ * ps.quiz_score
            + W_RECENCY * ps.recency_score
        )

        ps.eligible = ps.total_score >= PROMOTE_THRESHOLD and recall_count >= MIN_RECALL_COUNT
        return ps

    def _get_quiz_score(self, date_str: str) -> float:
        """Get quiz accuracy for concepts studied on a given date.

        Reads daily memory to find mentioned concepts, then checks quiz accuracy.
        Returns 0.0 if no quiz data available.
        """
        try:
            # Read daily memory content
            content = self.daily.read(date_str)
            if not content:
                return 0.0

            # Extract concepts mentioned in daily memory (simple keyword approach)
            concepts = self._extract_concepts_from_text(content)
            if not concepts:
                return 0.0

            # Check quiz accuracy for these concepts
            from quiz.store import QuizStore
            quiz_store = QuizStore(self.workspace)
            weakness = quiz_store.get_weakness_analysis()

            if not weakness:
                return 0.0

            # Calculate average accuracy for matched concepts
            matched = []
            weakness_map = {w["concept"]: w for w in weakness}
            for concept in concepts:
                if concept in weakness_map:
                    w = weakness_map[concept]
                    accuracy = 1.0 - w["error_rate"]
                    matched.append(accuracy)

            return sum(matched) / len(matched) if matched else 0.0
        except Exception as e:
            logger.debug("Quiz score lookup failed: %s", e)
            return 0.0

    def _extract_concepts_from_text(self, text: str) -> list[str]:
        """Extract concept keywords from daily memory text.

        Simple approach: look for bold text, bullet points with known patterns,
        and explicit concept mentions.
        """
        concepts = []
        for line in text.split("\n"):
            line = line.strip()
            # Lines starting with "- " that mention concepts
            if line.startswith("- ") and len(line) > 4:
                # Clean up markdown
                clean = line[2:].strip("*` ")
                if len(clean) > 2 and len(clean) < 50:
                    concepts.append(clean)
        return concepts[:10]  # Cap at 10

    def promote(self, daily_path: str) -> dict:
        """Promote a daily memory file to permanent memory.

        Reads the daily file, writes it to permanent memory directory,
        and records the promotion in the log.

        Returns {promoted: bool, score: PromotionScore, details: str}.
        """
        # Extract date from filename
        filename = os.path.basename(daily_path)
        date_str = filename.replace(".md", "")

        # Score first
        ps = self.score(daily_path, date_str)
        if not ps.eligible:
            return {
                "promoted": False,
                "score": ps,
                "details": f"Score {ps.total_score:.2f} < {PROMOTE_THRESHOLD} or recall_count {ps.recall_count} < {MIN_RECALL_COUNT}",
            }

        # Read daily content
        content = self.daily.read(date_str)
        if not content.strip():
            return {
                "promoted": False,
                "score": ps,
                "details": "Daily file is empty",
            }

        # Strip frontmatter
        body = content
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                body = content[end + 3:].strip()

        # Write to permanent memory
        mem_name = f"daily-{date_str}"
        description = f"Promoted from daily memory {date_str}"
        from core.memory import MemoryManager
        manager = MemoryManager(self.workspace, self.base_dir)
        manager.save(
            name=mem_name,
            description=description,
            content=body,
            entry_type="project",
        )

        # Record promotion
        details = {
            "frequency": ps.frequency_score,
            "quiz": ps.quiz_score,
            "recency": ps.recency_score,
            "recall_count": ps.recall_count,
        }
        self.store.record_promotion(daily_path, ps.total_score, details)

        logger.info("Promoted daily memory %s (score=%.2f)", date_str, ps.total_score)
        return {
            "promoted": True,
            "score": ps,
            "details": f"Promoted as '{mem_name}' with score {ps.total_score:.2f}",
        }

    def check_stale(self) -> list[dict]:
        """Check permanent memories that might need review (stale).

        Returns list of memories with low quiz accuracy that haven't been
        reviewed recently. Not implemented in MVP — placeholder for future.
        """
        # MVP: just return empty list
        return []

    def run_promotion_check(self, min_age_days: int = 3) -> list[dict]:
        """Check all eligible daily memories and return promotion results.

        Does NOT auto-promote — returns candidates for user review.
        """
        candidates = self.store.get_promotion_candidates(min_age_days=min_age_days)
        results = []
        for c in candidates:
            ps = self.score(c["path"], c["date"])
            results.append({
                "path": c["path"],
                "date": c["date"],
                "score": ps.total_score,
                "eligible": ps.eligible,
                "recall_count": ps.recall_count,
                "frequency": ps.frequency_score,
                "quiz": ps.quiz_score,
                "recency": ps.recency_score,
            })
        return results
