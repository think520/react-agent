"""Learning path generator.

Priority of data sources:
1. Quiz records (weakness analysis) — reflects actual mastery
2. User goal — what the user wants to achieve
3. Graph relations — prerequisite ordering
4. Course structure — chapter/section order from notes
"""

import json
import logging
from datetime import datetime, timezone

from .schema import LearningPlan
from .store import LearningStore
from .progress import ProgressTracker

logger = logging.getLogger(__name__)

PATH_GENERATION_PROMPT = """你是一个学习规划助手。根据以下信息，生成一份个性化学习计划。

用户目标：{goal}
截止日期：{deadline}
课程资料：{course_info}
薄弱知识点：{weakness_info}
已有掌握度：{mastery_info}

要求：
1. 按天拆分学习任务，每天 2-3 个知识点
2. 薄弱知识点优先安排，已掌握的可以跳过或快速复习
3. 每个学习步骤关联具体资料来源
4. 每天末尾安排 3-5 道练习题巩固
5. 计划要现实可行，考虑截止日期
6. 所有内容用中文

严格按以下 JSON 格式输出，不要添加 markdown 代码块或其他文字：
{{
  "title": "学习计划标题",
  "steps": [
    {{
      "day": 1,
      "date": "2026-05-20",
      "topics": ["知识点1", "知识点2"],
      "materials": ["来源文件1.md", "来源文件2.md"],
      "tasks": ["学习xxx概念", "做3道相关练习题"],
      "review": ["需要复习的旧知识点"]
    }}
  ]
}}"""


class LearningPathGenerator:
    def __init__(self, store: LearningStore, progress: ProgressTracker, llm_provider=None):
        self.store = store
        self.progress = progress
        self.llm = llm_provider

    def generate_path(
        self,
        goal: str,
        course: str | None = None,
        deadline: str | None = None,
        workspace: str = ".",
    ) -> LearningPlan:
        """Generate a learning plan based on user goal, mastery state, and course materials."""
        # Gather data sources
        weakness_info = self._get_weakness_summary(workspace)
        mastery_info = self._get_mastery_summary(course)
        course_info = self._get_course_info(workspace, course)

        if not self.llm:
            # Fallback: generate a simple plan from weakness data
            return self._generate_simple_plan(goal, weakness_info, course, deadline)

        # Use LLM to generate a personalized plan
        prompt = PATH_GENERATION_PROMPT.format(
            goal=goal,
            deadline=deadline or "无截止日期",
            course_info=course_info or "未找到相关课程资料",
            weakness_info=weakness_info or "暂无做题记录",
            mastery_info=mastery_info or "暂无掌握度数据",
        )

        try:
            response = self.llm.complete([{"role": "user", "content": prompt}])
            raw = response.content if hasattr(response, "content") else str(response)
            plan_data = self._parse_plan_json(raw)
        except Exception as e:
            logger.error("LLM plan generation failed: %s", e)
            return self._generate_simple_plan(goal, weakness_info, course, deadline)

        plan = LearningPlan(
            title=plan_data.get("title", f"学习计划: {goal}"),
            goal=goal,
            steps=plan_data.get("steps", []),
            course=course,
            deadline=deadline,
        )

        # Save to store
        plan.id = self.store.save_plan(plan)
        return plan

    def _get_weakness_summary(self, workspace: str = ".") -> str:
        """Get weakness summary from quiz review."""
        try:
            from quiz.review import QuizReviewer
            from quiz.store import QuizStore
            quiz_store = QuizStore(workspace)
            reviewer = QuizReviewer(quiz_store)
            analysis = reviewer.get_weakness_analysis()
            if not analysis:
                return ""
            lines = []
            for item in analysis[:10]:
                accuracy = 1.0 - item["error_rate"]
                lines.append(f"- {item['concept']}: 正确率 {accuracy:.0%}, 错题 {item['wrong_count']} 道")
            return "\n".join(lines)
        except Exception as exc:
            logger.warning("Weakness summary unavailable for learning plan: %s", exc)
            return ""

    def _get_mastery_summary(self, course: str | None = None) -> str:
        """Get mastery overview."""
        overview = self.progress.get_overview()
        if overview["total_concepts"] == 0:
            return ""
        lines = [f"已跟踪 {overview['total_concepts']} 个知识点，平均掌握度 {overview['average_score']:.0%}"]
        if overview["weakest"]:
            lines.append("最薄弱:")
            for w in overview["weakest"]:
                lines.append(f"  - {w['concept']}: {w['score']:.0%}")
        return "\n".join(lines)

    def _get_course_info(self, workspace: str, course: str | None = None) -> str:
        """Get course structure from RAG index."""
        try:
            import os
            from knowledge.paths import knowledge_path
            index_path = knowledge_path(workspace, "rag_index.json")
            if not os.path.exists(index_path):
                return ""
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            chunks = data.get("chunks", [])
            sources = set()
            for c in chunks:
                src = c.get("source", "")
                if course and course not in src:
                    continue
                sources.add(src)
            if not sources:
                return ""
            return f"可用资料 ({len(sources)} 个文件):\n" + "\n".join(f"- {s}" for s in sorted(sources))
        except Exception:
            return ""

    def _generate_simple_plan(
        self, goal: str, weakness_info: str, course: str | None, deadline: str | None
    ) -> LearningPlan:
        """Fallback: generate a basic plan without LLM."""
        steps = []
        # Simple plan based on weakness data
        if weakness_info:
            concepts = []
            for line in weakness_info.split("\n"):
                if line.startswith("- "):
                    concept = line.split(":")[0].replace("- ", "").strip()
                    concepts.append(concept)
            for i, concept in enumerate(concepts[:7], 1):
                steps.append({
                    "day": i,
                    "date": "",
                    "topics": [concept],
                    "materials": [],
                    "tasks": [f"复习 {concept} 的相关笔记", f"做 3 道 {concept} 相关练习题"],
                    "review": [],
                })
        else:
            steps.append({
                "day": 1,
                "date": "",
                "topics": [goal],
                "materials": [],
                "tasks": [f"阅读 {goal} 相关资料", "完成 5 道练习题"],
                "review": [],
            })

        plan = LearningPlan(
            title=f"学习计划: {goal}",
            goal=goal,
            steps=steps,
            course=course,
            deadline=deadline,
        )
        plan.id = self.store.save_plan(plan)
        return plan

    @staticmethod
    def _parse_plan_json(text: str) -> dict:
        """Parse JSON plan from LLM response (shared implementation)."""
        from core.llm_json import parse_llm_object
        return parse_llm_object(text) or {}
