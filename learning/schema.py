from dataclasses import dataclass, field

MASTERY_UNSEEN = "unseen"
MASTERY_LEARNING = "learning"
MASTERY_MASTERED = "mastered"
MASTERY_NEEDS_REVIEW = "needs_review"


@dataclass
class Mastery:
    """Tracks mastery state for a single knowledge concept.

    E6.2 分工：
    - «next_review» / «interval_days» / «ease_factor» / «review_count» /
      «consecutive_correct» 是**调度状态**，由 SM-2 写入。
    - «manual_status» / «manual_at» 是**用户自己的判断**，与系统推导分开存。
    - «status» / «score» 是旧口径的历史快照，仅在没有逐次历史时作为回退值；
      业务判断与展示统一走 «learning.contract.mastery_state»。
    """
    concept: str
    status: str = MASTERY_UNSEEN
    score: float = 0.0      # 旧口径存量分数（回退值，不再是能力判断）
    review_count: int = 0
    consecutive_correct: int = 0
    ease_factor: float = 2.5
    interval_days: int = 0
    last_reviewed: str | None = None
    next_review: str | None = None
    source: str = "auto"    # auto (调度写入) or manual (用户标记过)
    updated_at: str = ""
    manual_status: str | None = None
    manual_at: str | None = None


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
