"""P1-14: patching preferences must not silently lose a concurrent update."""

import threading

from service.preference_service import PreferenceService


def test_concurrent_patches_do_not_lose_an_update(tmp_path, monkeypatch):
    """`patch` read the revision, checked it, then wrote - with no lock.

    Two concurrent callers both read the same revision, both passed the check
    and both were told the write succeeded, while one of the two changes
    vanished. Correct behaviour is: exactly one wins, the other is told
    `preferences_revision_conflict` and retries.
    """
    service = PreferenceService(home=str(tmp_path))
    base = service.get()["revision"]

    barrier = threading.Barrier(2)
    original_get = PreferenceService.get

    def slow_get(self):
        current = original_get(self)
        try:
            # Give a concurrent reader the chance to read the same revision.
            barrier.wait(timeout=0.4)
        except threading.BrokenBarrierError:
            pass
        return current

    monkeypatch.setattr(PreferenceService, "get", slow_get)

    outcomes: list[str] = []
    lock = threading.Lock()

    def run(patch):
        try:
            service.patch(base, patch, set(), set())
            outcome = "ok"
        except RuntimeError as exc:
            outcome = str(exc)
        with lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=run, args=({"appearance": {"paper_texture": False}},)),
        threading.Thread(target=run, args=({"memory": {"enabled": False}},)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert outcomes.count("ok") == 1, outcomes
    assert any("conflict" in outcome for outcome in outcomes), outcomes
    assert service.get()["revision"] == base + 1

def test_appearance_theme_and_contrast_are_validated(tmp_path):
    """W-F6：主题/对比度偏好必须有默认值，且非法值被拒绝。"""
    from service.preference_service import PreferenceService

    service = PreferenceService(default_provider="deepseek", home=str(tmp_path))
    defaults = service.get()
    assert defaults["appearance"]["theme"] == "system"
    assert defaults["appearance"]["contrast"] == "normal"

    updated = service.patch(
        defaults["revision"],
        {"appearance": {"theme": "dark", "contrast": "high"}},
        {"deepseek"},
        set(),
    )
    assert updated["appearance"]["theme"] == "dark"
    assert updated["appearance"]["contrast"] == "high"

    import pytest

    with pytest.raises(ValueError):
        service.patch(updated["revision"], {"appearance": {"theme": "neon"}}, {"deepseek"}, set())
    with pytest.raises(ValueError):
        service.patch(updated["revision"], {"appearance": {"contrast": "extreme"}}, {"deepseek"}, set())
