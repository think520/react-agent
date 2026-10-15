"""Capabilities intentionally exposed by the learning-focused Web runtime."""

WEB_SKILL_NAMES = frozenset({
    "course-learning",
    "exam-prep",
    "study-loop",
    # W1 E10: persona 载体 —— 不进白名单，Web 设置里就完全看不到它。
    "socratic-persona",
})
