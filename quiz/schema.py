from dataclasses import dataclass, field

QUESTION_TYPES = {"single_choice", "true_false", "short_answer"}
DIFFICULTY_LEVELS = {"easy", "medium", "hard"}


@dataclass
class Question:
    id: int | None = None
    type: str = "single_choice"
    question: str = ""
    options: list[str] = field(default_factory=list)
    answer: str = ""
    explanation: str = ""
    concepts: list[str] = field(default_factory=list)
    difficulty: str = "medium"
    source: str = ""
    created_at: str = ""


@dataclass
class QuizSession:
    id: int | None = None
    question_ids: list[int] = field(default_factory=list)
    started_at: str = ""
    completed_at: str | None = None


@dataclass
class QuizAttempt:
    id: int | None = None
    session_id: int = 0
    question_id: int = 0
    user_answer: str = ""
    is_correct: bool = False
    feedback: str = ""
    answered_at: str = ""
