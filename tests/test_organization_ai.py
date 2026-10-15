"""⑤（E17）：AI 归类 —— 提议可以来自模型，"动不动手"仍然只由用户确认决定。

设计 §3.5 决定 22：整理可以交给波波蛋，但必须走「提议 → 预览 → 确认 → 执行 →
一键撤销」。⑤a 的确定性规则只会说"库根散落"，这一块加**模型归类**，并且把三条
底线写成测试：

1. **文件清单由服务端说了算**：模型提到库里不存在的文件一律丢掉（不许凭空造资料）；
2. **目标文件夹必须落在资料库里且不是 Bobodan 自己的目录**：`.bobodan/…`、`..`、
   绝对路径一律拒绝；
3. **模型不可用或没说人话时如实降级**回规则建议，并说明原因 —— 不假装那是模型给的。
"""

import json
from types import SimpleNamespace

import pytest

from service.kb_service import KBService
from service.library_service import LibraryService


class FakeProvider:
    """只实现组织代码真正用到的那部分契约：`complete()` 返回带 `content` 的对象。"""

    name = "fake"
    model = "fake-model"

    def __init__(self, reply: str = "", error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.prompts: list = []

    def complete(self, messages, **kwargs):
        self.prompts.append(messages)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content=self.reply)


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    return root


def _drop(library, *names):
    for name in names:
        (library / name).write_text(f"# {name}\n\n内容足够长，能切出一段。", encoding="utf-8")


def _reply(groups):
    return json.dumps({"groups": groups}, ensure_ascii=False)


def test_model_grouping_is_validated_against_real_files(library):
    _drop(library, "散落的一课.md", "另一份.md")
    service = KBService(str(library))
    provider = FakeProvider(reply=_reply([
        {"folder": "课程笔记", "items": ["散落的一课.md", "凭空捏造.md"], "reason": "看起来是同一门课"},
        {"folder": ".bobodan/evil", "items": ["另一份.md"], "reason": "内部目录不该被接受"},
        {"folder": "../外面", "items": ["散落的一课.md"], "reason": "越界路径不该被接受"},
    ]))

    result = service.propose_organization(llm_provider=provider)

    assert result["ok"], result
    assert result["source"] == "model", result
    assert result["degraded"] == ""
    assert [proposal["items"] for proposal in result["proposals"]] == [["散落的一课.md"]]
    proposal = result["proposals"][0]
    assert proposal["suggested_folder"] == "课程笔记"
    assert proposal["requires_confirmation"] is True, "模型不能自己动手"
    # 提示词里必须给出真实存在的文件名 —— 不然模型只能靠猜。
    prompt = json.dumps(provider.prompts, ensure_ascii=False)
    assert "散落的一课.md" in prompt


def test_model_failure_degrades_to_rules_and_says_why(library):
    _drop(library, "散落的一课.md")
    service = KBService(str(library))

    result = service.propose_organization(llm_provider=FakeProvider(error=RuntimeError("provider down")))

    assert result["ok"], result
    assert result["source"] == "rules"
    assert result["degraded"] == "model_unavailable"
    assert result["proposals"][0]["kind"] == "loose_materials"


def test_a_model_that_says_nothing_useful_degrades_too(library):
    _drop(library, "散落的一课.md")
    service = KBService(str(library))

    result = service.propose_organization(llm_provider=FakeProvider(reply="我觉得还行吧"))

    assert result["ok"], result
    assert result["source"] == "rules"
    assert result["degraded"] == "model_returned_nothing"
    assert result["proposals"][0]["kind"] == "loose_materials"


def test_rules_only_path_is_unchanged_when_no_model_is_given(library):
    _drop(library, "散落的一课.md")
    service = KBService(str(library))

    result = service.propose_organization()

    assert result["ok"], result
    assert result["source"] == "rules"
    assert result["degraded"] == ""
    assert result["proposals"][0]["kind"] == "loose_materials"
