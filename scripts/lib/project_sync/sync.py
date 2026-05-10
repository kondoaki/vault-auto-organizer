from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lib.common import AgentError, Config, log_info

from . import agent as agent_mod
from . import facts as facts_mod
from . import note as note_mod


@dataclass
class SyncResult:
    name: str
    status: str
    sha: str = None
    note_path: Path = None
    message: str = None


def sync_repo(cfg: Config, repo_path: Path, *, force: bool) -> SyncResult:
    name = repo_path.name
    note_path = note_mod.resolve_note_path(cfg.vault_dir, name)
    note_path.parent.mkdir(parents=True, exist_ok=True)

    state = note_mod.classify_note_state(note_path, repo_path=repo_path)

    if state == "mismatch":
        existing = note_mod.parse_note_text(
            note_path.read_text(encoding="utf-8")
        )
        other = existing.frontmatter.get("project_path", "?")
        return SyncResult(
            name=name, status="error", sha=None,
            message=f"already linked to {other}",
        )

    facts = facts_mod.collect_facts(repo_path)

    if state == "registered" and not force:
        existing = note_mod.parse_note_text(
            note_path.read_text(encoding="utf-8")
        )
        if note_mod.should_skip(existing, head_short=facts.head_commit):
            return SyncResult(
                name=name, status="skipped-unchanged",
                sha=facts.head_commit, note_path=note_path,
            )

    note_existed_before = note_path.exists()

    if state in ("registered", "adopt"):
        existing = note_mod.parse_note_text(
            note_path.read_text(encoding="utf-8")
        )
        if not note_mod.has_valid_markers(existing.body):
            if (note_mod.MARKER_START in existing.body
                    or note_mod.MARKER_END in existing.body):
                return SyncResult(
                    name=name, status="error",
                    message="marker block malformed; repair manually",
                )
            existing = note_mod.ParsedNote(
                frontmatter=existing.frontmatter,
                body=existing.body.rstrip() + "\n\n" + note_mod.default_skeleton(),
            )
            note_path.write_text(
                note_mod.render_note(existing), encoding="utf-8"
            )
    else:  # state == "new"
        skeleton_body = note_mod.default_skeleton()
        bootstrap = note_mod.ParsedNote(
            frontmatter={"project_path": facts.project_path},
            body=skeleton_body,
        )
        note_path.write_text(
            note_mod.render_note(bootstrap), encoding="utf-8"
        )

    yaml_block = facts_mod.to_yaml_block(
        facts,
        note_path=str(note_path.relative_to(cfg.vault_dir)),
        note_exists=note_existed_before,
    )
    prompt_text = agent_mod.render_prompt(yaml_block)

    try:
        agent_mod.invoke_for_repo(
            cfg, repo_path=repo_path, prompt_text=prompt_text,
        )
    except AgentError as e:
        return SyncResult(
            name=name, status="error",
            message=f"agent failed: {e}", note_path=note_path,
        )

    after = note_mod.parse_note_text(
        note_path.read_text(encoding="utf-8")
    )
    if not note_mod.has_valid_markers(after.body):
        return SyncResult(
            name=name, status="error",
            message="agent corrupted marker block",
            note_path=note_path,
        )

    fields = {
        "project_path": facts.project_path,
        "last_synced": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_synced_commit": facts.head_commit,
    }
    if facts.project_repo:
        fields["project_repo"] = facts.project_repo

    final = note_mod.update_frontmatter_fields(after, **fields)
    note_path.write_text(note_mod.render_note(final), encoding="utf-8")

    if state == "new":
        status = "created"
    elif state == "adopt":
        status = "linked"
    else:
        status = "synced"

    log_info(f"{status} {name} @ {facts.head_commit}")
    return SyncResult(
        name=name, status=status, sha=facts.head_commit, note_path=note_path,
    )


__all__ = ["SyncResult", "sync_repo"]
