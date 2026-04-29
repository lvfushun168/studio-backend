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


def build_default_stage_progress(stage_template: str, project_id: int, scene_id: int) -> list[dict]:
    template = STAGE_TEMPLATES.get(stage_template, STAGE_TEMPLATES["ai_single_frame"])
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
