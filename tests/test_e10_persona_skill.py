"""W1 E10：Socratic persona 的**载体**与**优先级裁决**。

核对结论：产品里**没有 persona 系统**（«assistant.display_name» 只是名字），
所以先定载体 —— 这里用现成的 skills 通道（«skills/» 发现 → 目录注入 system prompt →
«preferences.skills.enabled_names» 过滤），并把它加进 Web 白名单，否则在 Web 上完全不可见。

裁决（必须写死并留痕）：**persona 管风格与流程，不碰证据门禁**。
"""

from __future__ import annotations

import os

from core.skills import build_skills_system_prompt, find_skill_by_name, list_skills

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(REPO_ROOT, "skills")


def test_the_persona_skill_loads_like_any_other_skill():
    skill = find_skill_by_name(SKILLS_DIR, "socratic-persona")

    assert skill is not None, [item.name for item in list_skills(SKILLS_DIR)]
    assert skill.description.strip(), skill
    # 描述要让人（和模型）知道它管的是"怎么带"而不是"讲什么"。
    assert "苏格拉底" in skill.description or "提问" in skill.description, skill.description


def test_the_persona_is_visible_and_enableable_on_the_web():
    """Web 侧 skills 是白名单 —— 不进白名单，设置了也看不见。"""
    from web.backend.capabilities import WEB_SKILL_NAMES

    assert "socratic-persona" in WEB_SKILL_NAMES


def test_the_persona_shows_up_in_web_settings():
    """白名单的用处就在这里：设置页要能列出它，用户才可能启用。"""
    from web.backend.routers.settings import _skills

    # 相对目录会挂到「workspace」上（测试里是临时目录），所以这里给绝对路径。
    names = [skill.name for skill in _skills({"skills": {"enabled": True, "dir": SKILLS_DIR}})]

    assert "socratic-persona" in names, names


def test_enabling_the_persona_puts_it_in_the_system_prompt():
    prompt = build_skills_system_prompt(SKILLS_DIR, {"socratic-persona"})

    assert prompt is not None
    assert "socratic-persona" in prompt
    # 只挂启用的那一个：别的技能不该被顺手带上。
    assert "study-loop" not in prompt


def test_the_persona_states_the_adjudication_explicitly():
    """裁决要写在载体里：风格可以变，证据门禁与来源绑定不能变。"""
    skill = find_skill_by_name(SKILLS_DIR, "socratic-persona")
    body = open(skill.file_path, encoding="utf-8").read()

    assert "证据门禁" in body, body[:400]
    assert "不碰" in body or "不改变" in body or "不得绕过" in body, body[:400]
    # 练习必须经服务端绑定的卡片，persona 不能改成"直接发题"。
    assert "练习卡" in body, body[:400]


def test_the_adjudication_is_recorded_in_the_docs():
    doc = os.path.join(REPO_ROOT, "docs", "PERSONA.md")

    assert os.path.isfile(doc), doc
    text = open(doc, encoding="utf-8").read()
    assert "证据门禁" in text, text[:400]
    # 明确写出优先级顺序，避免以后靠猜。
    assert "优先级" in text, text[:400]
