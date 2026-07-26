from dataclasses import dataclass, field

MASTERY_UNSEEN = "unseen"
MASTERY_LEARNING = "learning"
MASTERY_MASTERED = "mastered"
MASTERY_NEEDS_REVIEW = "needs_review"


@dataclass
class Mastery:
    """Tracks mastery state for a single knowledge concept."""
    concept: str
    status: str = MASTERY_UNSEEN
    score: float = 0.0      # 0.0 ~ 1.0
    review_count: int = 0
    consecutive_correct: int = 0
    ease_factor: float = 2.5
    interval_days: int = 0
    last_reviewed: str | None = None
    next_review: str | None = None
    source: str = "auto"    # auto (from quiz) or manual (user override)
    updated_at: str = ""


@dataclass
class LearningPlan:
    """A generated learning plan with ordered steps."""
    id: int | None = None
    title: str = ""
    goal: str = ""
    steps: list[dict] = field(default_factory=list)
    course: str | None = None
    created_at: str = ""
    deadline: str | None = None
    status: str = "active"          # active | completed
    current_day: int | None = None
