from __future__ import annotations

from lib.project_sync import note as note_mod


def test_state_new_when_note_missing(tmp_path):
    p = tmp_path / "missing.md"
    state = note_mod.classify_note_state(p, repo_path=tmp_path / "fake")
    assert state == "new"


def test_state_linked_when_no_project_path(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("---\ntitle: hi\n---\nbody\n", encoding="utf-8")
    state = note_mod.classify_note_state(p, repo_path=tmp_path / "fake")
    assert state == "adopt"


def test_state_registered_when_project_path_matches(tmp_path):
    repo = tmp_path / "Projects" / "foo"
    repo.mkdir(parents=True)
    p = tmp_path / "n.md"
    p.write_text(
        f"---\nproject_path: {repo}\n---\nx\n", encoding="utf-8"
    )
    state = note_mod.classify_note_state(p, repo_path=repo)
    assert state == "registered"


def test_state_registered_when_project_path_uses_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "Projects" / "foo"
    repo.mkdir(parents=True)
    p = tmp_path / "n.md"
    p.write_text("---\nproject_path: ~/Projects/foo\n---\nx\n", encoding="utf-8")
    state = note_mod.classify_note_state(p, repo_path=repo)
    assert state == "registered"


def test_state_mismatch_when_project_path_points_elsewhere(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    p = tmp_path / "n.md"
    p.write_text(
        f"---\nproject_path: {other}\n---\nx\n", encoding="utf-8"
    )
    state = note_mod.classify_note_state(p, repo_path=tmp_path / "actual")
    assert state == "mismatch"


def test_should_skip_when_commit_matches(tmp_path):
    p = tmp_path / "n.md"
    p.write_text(
        "---\n"
        "project_path: /tmp/x\n"
        "last_synced_commit: abc1234\n"
        "---\nbody\n",
        encoding="utf-8",
    )
    parsed = note_mod.parse_note_text(p.read_text())
    assert note_mod.should_skip(parsed, head_short="abc1234") is True
    assert note_mod.should_skip(parsed, head_short="differen") is False


def test_should_skip_false_when_no_last_synced(tmp_path):
    parsed = note_mod.parse_note_text("---\ntitle: x\n---\nbody\n")
    assert note_mod.should_skip(parsed, head_short="abc1234") is False
