from __future__ import annotations

import re

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session


STAGE_TEMPLATES = {
    "ai_single_frame": [
        {"key": "storyboard", "label": "分镜", "needs_review": True},
        {"key": "ai_draw", "label": "AI抽卡", "needs_review": True},
        {"key": "correction", "label": "修正", "needs_review": True},
        {"key": "final", "label": "成稿", "needs_review": True},
    ],
    "standard": [
        {"key": "storyboard", "label": "分镜", "needs_review": True},
        {"key": "layout_character", "label": "Layout(人)", "needs_review": True, "sub_track": "character"},
        {"key": "layout_background", "label": "Layout(背)", "needs_review": True, "sub_track": "background"},
        {"key": "keyframe", "label": "一原", "needs_review": True},
        {"key": "second_keyframe", "label": "二原", "needs_review": True},
        {"key": "inbetween", "label": "中割", "needs_review": True},
        {"key": "coloring", "label": "上色", "needs_review": True},
        {"key": "compositing", "label": "合成", "needs_review": True},
        {"key": "final", "label": "完成", "needs_review": True},
    ],
    "standard_keyframe_review": [
        {"key": "storyboard", "label": "分镜", "needs_review": True},
        {"key": "layout_character", "label": "Layout(人)", "needs_review": True, "sub_track": "character"},
        {"key": "layout_background", "label": "Layout(背)", "needs_review": True, "sub_track": "background"},
        {"key": "keyframe", "label": "一原", "needs_review": True},
        {"key": "keyframe_review", "label": "一原作监", "needs_review": True},
        {"key": "second_keyframe", "label": "二原", "needs_review": True},
        {"key": "inbetween", "label": "中割", "needs_review": True},
        {"key": "coloring", "label": "上色", "needs_review": True},
        {"key": "compositing", "label": "合成", "needs_review": True},
        {"key": "final", "label": "完成", "needs_review": True},
    ],
    "standard_second_review": [
        {"key": "storyboard", "label": "分镜", "needs_review": True},
        {"key": "layout_character", "label": "Layout(人)", "needs_review": True, "sub_track": "character"},
        {"key": "layout_background", "label": "Layout(背)", "needs_review": True, "sub_track": "background"},
        {"key": "keyframe", "label": "一原", "needs_review": True},
        {"key": "second_keyframe", "label": "二原", "needs_review": True},
        {"key": "second_review", "label": "二原作监", "needs_review": True},
        {"key": "inbetween", "label": "中割", "needs_review": True},
        {"key": "coloring", "label": "上色", "needs_review": True},
        {"key": "compositing", "label": "合成", "needs_review": True},
        {"key": "final", "label": "完成", "needs_review": True},
    ],
    "standard_dual_review": [
        {"key": "storyboard", "label": "分镜", "needs_review": True},
        {"key": "layout_character", "label": "Layout(人)", "needs_review": True, "sub_track": "character"},
        {"key": "layout_background", "label": "Layout(背)", "needs_review": True, "sub_track": "background"},
        {"key": "keyframe", "label": "一原", "needs_review": True},
        {"key": "keyframe_review", "label": "一原作监", "needs_review": True},
        {"key": "second_keyframe", "label": "二原", "needs_review": True},
        {"key": "second_review", "label": "二原作监", "needs_review": True},
        {"key": "inbetween", "label": "中割", "needs_review": True},
        {"key": "coloring", "label": "上色", "needs_review": True},
        {"key": "compositing", "label": "合成", "needs_review": True},
        {"key": "final", "label": "完成", "needs_review": True},
    ],
}

PROJECT_TEMPLATE_PREFIX = "project_template:"
GLOBAL_TEMPLATE_PREFIX = "global_template:"
STAGE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def make_project_template_key(template_id: int) -> str:
    return f"{PROJECT_TEMPLATE_PREFIX}{template_id}"


def make_global_template_key(template_id: int) -> str:
    return f"{GLOBAL_TEMPLATE_PREFIX}{template_id}"


def parse_project_template_key(template_key: str | None) -> int | None:
    if not template_key or not template_key.startswith(PROJECT_TEMPLATE_PREFIX):
        return None
    raw_id = template_key[len(PROJECT_TEMPLATE_PREFIX):]
    if not raw_id.isdigit():
        return None
    return int(raw_id)


def parse_global_template_key(template_key: str | None) -> int | None:
    if not template_key or not template_key.startswith(GLOBAL_TEMPLATE_PREFIX):
        return None
    raw_id = template_key[len(GLOBAL_TEMPLATE_PREFIX):]
    if not raw_id.isdigit():
        return None
    return int(raw_id)


def clone_stage_steps(items: list[dict]) -> list[dict]:
    return [dict(item) for item in items]


def validate_stage_steps(steps: list[dict]) -> list[dict]:
    if not steps:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Workflow template must contain at least one step")
    if len(steps) > 20:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Workflow template cannot contain more than 20 steps")

    normalized: list[dict] = []
    seen_keys: set[str] = set()
    for index, raw_step in enumerate(steps):
        key = str(raw_step.get("key") or "").strip()
        label = str(raw_step.get("label") or "").strip()
        needs_review = bool(raw_step.get("needs_review", True))
        sub_track = raw_step.get("sub_track")
        if not STAGE_KEY_PATTERN.match(key):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid step key at position {index + 1}: {key or '<empty>'}")
        if not label:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Step label is required at position {index + 1}")
        if key in seen_keys:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Duplicate step key: {key}")
        if not needs_review:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Step '{key}' must require review in the current workflow engine")
        seen_keys.add(key)
        normalized.append(
            {
                "key": key,
                "label": label,
                "needs_review": True,
                "sub_track": str(sub_track).strip() if sub_track else None,
            }
        )

    layout_keys = [step["key"] for step in normalized if step["key"] in {"layout_character", "layout_background"}]
    if layout_keys:
        if set(layout_keys) != {"layout_character", "layout_background"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Layout dual-track steps must include both layout_character and layout_background")
        layout_character_index = next(i for i, step in enumerate(normalized) if step["key"] == "layout_character")
        layout_background_index = next(i for i, step in enumerate(normalized) if step["key"] == "layout_background")
        if layout_background_index != layout_character_index + 1:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="layout_character and layout_background must stay adjacent in the workflow")

    return normalized


def resolve_stage_template_steps(
    db: Session | None,
    stage_template: str,
    project_id: int | None = None,
) -> list[dict]:
    if stage_template in STAGE_TEMPLATES:
        return clone_stage_steps(STAGE_TEMPLATES[stage_template])

    template_id = parse_project_template_key(stage_template)
    if template_id is not None and db is not None:
        from app.models.workflow import WorkflowTemplate

        template = db.get(WorkflowTemplate, template_id)
        if template and template.scope == "project" and (project_id is None or template.project_id == project_id):
            return clone_stage_steps(template.steps_json or [])

    template_id = parse_global_template_key(stage_template)
    if template_id is not None and db is not None:
        from app.models.workflow import WorkflowTemplate

        template = db.get(WorkflowTemplate, template_id)
        if template and template.scope == "global":
            return clone_stage_steps(template.steps_json or [])

    return clone_stage_steps(STAGE_TEMPLATES["ai_single_frame"])


def stage_template_exists(
    db: Session | None,
    stage_template: str,
    project_id: int | None = None,
) -> bool:
    if stage_template in STAGE_TEMPLATES:
        return True

    template_id = parse_project_template_key(stage_template)
    if template_id is not None and db is not None:
        from app.models.workflow import WorkflowTemplate

        template = db.get(WorkflowTemplate, template_id)
        return bool(template and template.scope == "project" and (project_id is None or template.project_id == project_id))

    template_id = parse_global_template_key(stage_template)
    if template_id is not None and db is not None:
        from app.models.workflow import WorkflowTemplate

        template = db.get(WorkflowTemplate, template_id)
        return bool(template and template.scope == "global")

    return False


def materialize_template_for_project(
    db: Session,
    stage_template: str,
    project_id: int,
    created_by: int | None = None,
) -> str:
    template_id = parse_global_template_key(stage_template)
    if template_id is None:
        return stage_template

    from app.models.workflow import WorkflowTemplate

    source_template = db.get(WorkflowTemplate, template_id)
    if not source_template or source_template.scope != "global":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage template not found")

    existing = db.scalar(
        select(WorkflowTemplate).where(
            WorkflowTemplate.scope == "project",
            WorkflowTemplate.project_id == project_id,
            WorkflowTemplate.based_on_template_key == stage_template,
        ).limit(1)
    )
    if existing:
        return make_project_template_key(existing.id)

    base_name = source_template.name
    candidate_name = base_name
    suffix = 2
    while db.scalar(
        select(WorkflowTemplate.id).where(
            WorkflowTemplate.scope == "project",
            WorkflowTemplate.project_id == project_id,
            WorkflowTemplate.name == candidate_name,
        ).limit(1)
    ):
        candidate_name = f"{base_name} {suffix}"
        suffix += 1

    cloned = WorkflowTemplate(
        scope="project",
        project_id=project_id,
        name=candidate_name,
        description=source_template.description,
        based_on_template_key=stage_template,
        is_default=False,
        is_active=source_template.is_active,
        steps_json=clone_stage_steps(source_template.steps_json or []),
        created_by=created_by,
    )
    db.add(cloned)
    db.flush()
    return make_project_template_key(cloned.id)


def get_template_keys(db: Session | None, stage_template: str, project_id: int | None = None) -> list[str]:
    return [item["key"] for item in resolve_stage_template_steps(db, stage_template, project_id)]


def build_default_stage_progress(
    db: Session | None,
    stage_template: str,
    project_id: int,
    scene_id: int,
) -> list[dict]:
    template = resolve_stage_template_steps(db, stage_template, project_id)
    result: list[dict] = []
    for index, item in enumerate(template):
        result.append(
            {
                "project_id": project_id,
                "scene_id": scene_id,
                "stage_key": item["key"],
                "status": "pending" if index == 0 else "locked",
            }
        )
    return result
