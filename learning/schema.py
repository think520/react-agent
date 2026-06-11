from dataclasses import dataclass, field


@dataclass
class Mastery:
    """Tracks mastery state for a single knowledge concept."""
    concept: str
    status: str = "unseen"  # unseen, learning, mastered, needs_review
    score: float = 0.0      # 0.0 ~ 1.0
    review_count: int = 0
    consecutive_correct: int = 0
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
