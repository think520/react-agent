from .store import QuizStore


def format_wrong_answer_book(entries: list[dict]) -> str:
    """Format wrong answer entries for display."""
    if not entries:
        return "暂无错题记录。"

    lines = [f"错题本（共 {len(entries)} 道错题）：\n"]
    for i, entry in enumerate(entries, 1):
        lines.append(f"--- 第 {i} 题 ---")
        lines.append(f"题型: {_type_label(entry.get('type', ''))}")
        lines.append(f"难度: {entry.get('difficulty', 'medium')}")
        lines.append(f"题目: {entry.get('question', '')}")

        if entry.get("options") and entry["type"] == "single_choice":
            for opt in entry["options"]:
                lines.append(f"  {opt}")

        lines.append(f"你的答案: {entry.get('user_answer', '')}")
        lines.append(f"正确答案: {entry.get('answer', '')}")
        if entry.get("feedback"):
            lines.append(f"批改反馈: {entry['feedback']}")
        if entry.get("explanation"):
            lines.append(f"解析: {entry['explanation']}")
        if entry.get("concepts"):
            lines.append(f"知识点: {', '.join(entry['concepts'])}")
        lines.append("")

    return "\n".join(lines)


def format_weakness_analysis(analysis: list[dict]) -> str:
    """Format weakness analysis for display."""
    if not analysis:
        return "暂无做题记录，无法分析薄弱点。"

    lines = ["薄弱知识点分析：\n"]
    for item in analysis[:10]:
        concept = item.get("concept", "?")
        total = item.get("total_attempts", 0)
        wrong = item.get("wrong_count", 0)
        rate = item.get("error_rate", 0)
        lines.append(f"  {concept}: 错误率 {rate:.0%}（{wrong}/{total}）")

    return "\n".join(lines)


class QuizReviewer:
    def __init__(self, store: QuizStore):
        self.store = store

    def get_wrong_answer_book(self, limit: int = 20) -> list[dict]:
        """Return wrong answers with full question context."""
        return self.store.get_wrong_answers(limit)

    def get_weakness_analysis(self) -> list[dict]:
        """Group wrong answers by concept and calculate error rates."""
        return self.store.get_weakness_analysis()

    def format_wrong_answer_book(self, entries: list[dict]) -> str:
        """Format for display."""
        return format_wrong_answer_book(entries)

    def format_weakness_analysis(self, analysis: list[dict]) -> str:
        """Format for display."""
        return format_weakness_analysis(analysis)


def _type_label(qtype: str) -> str:
    return {
        "single_choice": "单选题",
        "true_false": "判断题",
        "short_answer": "简答题",
    }.get(qtype, qtype)
