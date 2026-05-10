from __future__ import annotations

from pathlib import Path

import pytest

from lib.project_sync import note as note_mod


def test_parse_note_with_frontmatter_and_body():
    text = (
        "---\n"
        "project_path: ~/Projects/foo\n"
        "last_synced_commit: a1b2c3d\n"
        "---\n"
        "\n"
        "body line\n"
    )
    parsed = note_mod.parse_note_text(text)
    assert parsed.frontmatter == {
        "project_path": "~/Projects/foo",
        "last_synced_commit": "a1b2c3d",
    }
    assert parsed.body == "\nbody line\n"


def test_parse_note_without_frontmatter():
    parsed = note_mod.parse_note_text("just body\n")
    assert parsed.frontmatter == {}
    assert parsed.body == "just body\n"


def test_render_round_trips():
    src = (
        "---\n"
        "a: 1\n"
        "b: two words\n"
        "---\n"
        "\nhello\n"
    )
    parsed = note_mod.parse_note_text(src)
    assert note_mod.render_note(parsed) == src


def test_update_frontmatter_fields_preserves_order_and_unknown_keys():
    parsed = note_mod.parse_note_text(
        "---\n"
        "title: Foo\n"
        "project_path: ~/Projects/foo\n"
        "last_synced_commit: old\n"
        "---\n"
        "body\n"
    )
    updated = note_mod.update_frontmatter_fields(
        parsed,
        last_synced_commit="new",
        last_synced="2026-05-10 14:32",
    )
    assert updated.frontmatter["title"] == "Foo"
    assert updated.frontmatter["last_synced_commit"] == "new"
    assert updated.frontmatter["last_synced"] == "2026-05-10 14:32"
    keys = list(updated.frontmatter.keys())
    assert keys[0] == "title"


def test_has_valid_markers_true_when_balanced():
    body = (
        "preamble\n"
        "<!-- vault-sync:start -->\n"
        "snapshot\n"
        "<!-- vault-sync:end -->\n"
        "tail\n"
    )
    assert note_mod.has_valid_markers(body) is True


def test_has_valid_markers_false_when_only_one():
    assert note_mod.has_valid_markers("<!-- vault-sync:start -->\nx\n") is False
    assert note_mod.has_valid_markers("x\n<!-- vault-sync:end -->\n") is False


def test_has_valid_markers_false_when_out_of_order():
    body = (
        "<!-- vault-sync:end -->\n"
        "<!-- vault-sync:start -->\n"
    )
    assert note_mod.has_valid_markers(body) is False


def test_resolve_note_path_prefers_folder_form_when_dir_exists(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "01_Projects" / "foo").mkdir(parents=True)
    p = note_mod.resolve_note_path(vault, "foo")
    assert p == vault / "01_Projects" / "foo" / "foo.md"


def test_resolve_note_path_falls_back_to_file_form(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "01_Projects").mkdir(parents=True)
    p = note_mod.resolve_note_path(vault, "foo")
    assert p == vault / "01_Projects" / "foo.md"


def test_default_skeleton_contains_marker_block():
    text = note_mod.default_skeleton()
    assert "<!-- vault-sync:start -->" in text
    assert "<!-- vault-sync:end -->" in text
    assert note_mod.has_valid_markers(text)
