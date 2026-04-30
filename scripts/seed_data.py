#!/usr/bin/env python3
"""Seed minimal demo data for frontend integration testing."""

from pathlib import Path
import sys

from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.auth import generate_api_key
from app.core.database import SessionLocal
from app.domains.stage_templates import build_default_stage_progress
from app.models.annotation import Annotation
from app.models.asset import Asset
from app.models.bank import BankMaterial, BankReference
from app.models.notification import Notification
from app.models.project import Episode, Project, SceneAssignment, SceneGroup, UserProjectMembership
from app.models.reference import Reference
from app.models.scene import Scene, StageProgress
from app.models.user import User


def clear_tables(db) -> None:
    """Clear all data using TRUNCATE with CASCADE."""
    tables = [
        "references",
        "notifications",
        "annotation_attachments",
        "annotations",
        "asset_attachments",
        "assets",
        "bank_references",
        "bank_materials",
        "review_records",
        "stage_progresses",
        "scene_assignments",
        "scenes",
        "scene_groups",
        "episodes",
        "user_project_memberships",
        "projects",
        "users",
    ]
    for t in tables:
        db.execute(text(f'TRUNCATE TABLE "{t}" CASCADE'))
    # Reset serial sequences
    for t in tables:
        db.execute(text(f"""SELECT setval(pg_get_serial_sequence('"{t}"', 'id'), 1, false)"""))
    db.commit()


def seed() -> None:
    db = SessionLocal()

    try:
        clear_tables(db)

        # 1. Users
        users = [
            User(username="admin", display_name="系统管理员", email="admin@studio.com", role="admin", api_key=generate_api_key(), is_active=True),
            User(username="director1", display_name="导演A", email="director.a@studio.com", role="director", api_key=generate_api_key(), is_active=True),
            User(username="director2", display_name="导演B", email="director.b@studio.com", role="director", api_key=generate_api_key(), is_active=True),
            User(username="producer1", display_name="制片人小王", email="producer@studio.com", role="producer", api_key=generate_api_key(), is_active=True),
            User(username="artist1", display_name="画师小红", email="artist.red@studio.com", role="artist", api_key=generate_api_key(), is_active=True),
            User(username="artist2", display_name="画师小明", email="artist.ming@studio.com", role="artist", api_key=generate_api_key(), is_active=True),
            User(username="artist3", display_name="画师小蓝", email="artist.blue@studio.com", role="artist", api_key=generate_api_key(), is_active=True),
            User(username="visitor1", display_name="访客小张", email="visitor.zhang@studio.com", role="visitor", api_key=generate_api_key(), is_active=True),
        ]
        db.add_all(users)
        db.flush()
        user_map = {u.username: u.id for u in users}

        # 2. Projects
        projects = [
            Project(name="奇幻冒险动画", description="2026年春季主项目，奇幻冒险题材，共2集", project_type="series", status="active", created_by=user_map["admin"]),
            Project(name="都市恋爱动画", description="现代都市背景恋爱题材，单集特别篇", project_type="single", status="active", created_by=user_map["admin"]),
            Project(name="科幻机甲动画", description="未来科幻机甲战斗题材，预研项目", project_type="single", status="active", created_by=user_map["admin"]),
        ]
        db.add_all(projects)
        db.flush()
        p1, p2, p3 = projects

        # 3. Memberships
        memberships = [
            UserProjectMembership(user_id=user_map["director1"], project_id=p1.id),
            UserProjectMembership(user_id=user_map["producer1"], project_id=p1.id),
            UserProjectMembership(user_id=user_map["artist1"], project_id=p1.id),
            UserProjectMembership(user_id=user_map["artist2"], project_id=p1.id),
            UserProjectMembership(user_id=user_map["visitor1"], project_id=p1.id),
            UserProjectMembership(user_id=user_map["director2"], project_id=p2.id),
            UserProjectMembership(user_id=user_map["artist2"], project_id=p2.id),
            UserProjectMembership(user_id=user_map["artist3"], project_id=p2.id),
        ]
        db.add_all(memberships)

        # 4. Episodes
        episodes = [
            Episode(project_id=p1.id, episode_number=1, name="第一集：觉醒"),
            Episode(project_id=p1.id, episode_number=2, name="第二集：相遇"),
        ]
        db.add_all(episodes)
        db.flush()
        ep1 = episodes[0]

        # 5. SceneGroups
        groups = [
            SceneGroup(project_id=p1.id, episode_id=ep1.id, name="镜头组A（城市篇）", sort_order=0),
            SceneGroup(project_id=p1.id, episode_id=ep1.id, name="镜头组B（森林篇）", sort_order=1),
            SceneGroup(project_id=p2.id, name="特别篇镜头组", sort_order=0),
        ]
        db.add_all(groups)
        db.flush()
        g1, g2, g3 = groups

        # 6. Scenes
        scenes_data = [
            {"project_id": p1.id, "scene_group_id": g1.id, "name": "SC001", "description": "主角觉醒场景，森林深处", "level": "A", "stage_template": "ai_single_frame", "pipeline": "ai_single_frame", "frame_count": 1, "sort_order": 1, "created_by": user_map["director1"]},
            {"project_id": p1.id, "scene_group_id": g1.id, "name": "SC002", "description": "主角与同伴相遇", "level": "B", "stage_template": "ai_single_frame", "pipeline": "ai_single_frame", "frame_count": 1, "sort_order": 2, "created_by": user_map["director1"]},
            {"project_id": p1.id, "scene_group_id": g1.id, "name": "SC003", "description": "战斗序章，雪原", "level": "A", "stage_template": "standard", "pipeline": "standard", "frame_count": 24, "duration_seconds": 1.0, "sort_order": 3, "created_by": user_map["director1"]},
            {"project_id": p1.id, "scene_group_id": g2.id, "name": "SC004", "description": "都市初遇，咖啡店", "level": "B", "stage_template": "ai_single_frame", "pipeline": "ai_single_frame", "frame_count": 1, "sort_order": 1, "created_by": user_map["director1"]},
            {"project_id": p1.id, "scene_group_id": g2.id, "name": "SC005", "description": "雨夜告白", "level": "A", "stage_template": "ai_single_frame", "pipeline": "ai_single_frame", "frame_count": 1, "sort_order": 2, "created_by": user_map["director1"]},
            {"project_id": p1.id, "scene_group_id": g2.id, "name": "SC004_A", "description": "咖啡店特写补充（基于 SC004 兼用）", "level": "C", "stage_template": "ai_single_frame", "pipeline": "ai_single_frame", "frame_count": 1, "sort_order": 3, "base_scene_id": None, "created_by": user_map["director1"]},
            {"project_id": p2.id, "scene_group_id": g3.id, "name": "SC001", "description": "开场全景", "level": "A", "stage_template": "standard_dual_review", "pipeline": "standard_dual_review", "frame_count": 48, "sort_order": 1, "created_by": user_map["director2"]},
        ]
        scene_objs = []
        for sd in scenes_data:
            s = Scene(**sd)
            db.add(s)
            scene_objs.append(s)
        db.flush()

        # Update base_scene_id for SC004_A
        sc004 = next(s for s in scene_objs if s.name == "SC004")
        sc004a = next(s for s in scene_objs if s.name == "SC004_A")
        sc004a.base_scene_id = sc004.id

        # 7. StageProgresses with demo statuses
        def _create_sp(scene, overrides):
            items = build_default_stage_progress(scene.stage_template, scene.project_id, scene.id)
            for item in items:
                item["status"] = overrides.get(item["stage_key"], item["status"])
                db.add(StageProgress(**item))

        _create_sp(scene_objs[0], {"storyboard": "approved", "ai_draw": "approved", "correction": "in_progress"})
        _create_sp(scene_objs[1], {"storyboard": "approved", "ai_draw": "reviewing"})
        _create_sp(scene_objs[2], {"storyboard": "approved", "layout_character": "in_progress", "layout_background": "pending"})
        for s in scene_objs[3:]:
            for item in build_default_stage_progress(s.stage_template, s.project_id, s.id):
                db.add(StageProgress(**item))

        # 8. SceneAssignments
        assignments = [
            SceneAssignment(scene_id=scene_objs[0].id, user_id=user_map["artist1"]),
            SceneAssignment(scene_id=scene_objs[1].id, user_id=user_map["artist1"]),
            SceneAssignment(scene_id=scene_objs[1].id, user_id=user_map["artist2"]),
            SceneAssignment(scene_id=scene_objs[2].id, user_id=user_map["artist2"]),
            SceneAssignment(scene_id=scene_objs[3].id, user_id=user_map["artist2"]),
            SceneAssignment(scene_id=scene_objs[3].id, user_id=user_map["artist3"]),
            SceneAssignment(scene_id=scene_objs[4].id, user_id=user_map["artist3"]),
            SceneAssignment(scene_id=scene_objs[5].id, user_id=user_map["artist1"]),
            SceneAssignment(scene_id=scene_objs[6].id, user_id=user_map["artist2"]),
        ]
        db.add_all(assignments)

        # 9. Assets
        assets = [
            Asset(project_id=p1.id, scene_id=scene_objs[0].id, scene_group_id=g1.id, stage_key="storyboard", media_type="image", filename="board_sc01.jpg", original_name="board_sc01.jpg", storage_path="", version=1, note="初版分镜", uploaded_by=user_map["artist1"]),
            Asset(project_id=p1.id, scene_id=scene_objs[0].id, scene_group_id=g1.id, stage_key="ai_draw", media_type="image", filename="ai_result_v1.jpg", original_name="ai_result_v1.jpg", storage_path="", version=1, note="第一轮抽卡", uploaded_by=user_map["artist1"]),
            Asset(project_id=p1.id, scene_id=scene_objs[0].id, scene_group_id=g1.id, stage_key="ai_draw", media_type="image", filename="ai_result_v2.jpg", original_name="ai_result_v2.jpg", storage_path="", version=2, note="光影修正版", uploaded_by=user_map["artist1"]),
            Asset(project_id=p1.id, scene_id=scene_objs[0].id, scene_group_id=g1.id, stage_key="correction", media_type="binary", filename="correct_v1.psd", original_name="correct_v1.psd", storage_path="", version=1, note="修正初稿", uploaded_by=user_map["artist1"]),
            Asset(project_id=p1.id, scene_id=scene_objs[0].id, scene_group_id=g1.id, stage_key="reference", media_type="image", filename="ref_pose.jpg", original_name="ref_pose.jpg", storage_path="", version=1, uploaded_by=user_map["artist1"]),
            Asset(project_id=p1.id, scene_id=scene_objs[1].id, scene_group_id=g1.id, stage_key="storyboard", media_type="image", filename="board_sc02.jpg", original_name="board_sc02.jpg", storage_path="", version=1, uploaded_by=user_map["artist2"]),
            Asset(project_id=p1.id, scene_id=scene_objs[2].id, scene_group_id=g1.id, stage_key="storyboard", media_type="image", filename="board_sc03.jpg", original_name="board_sc03.jpg", storage_path="", version=1, uploaded_by=user_map["artist2"]),
            Asset(project_id=p1.id, scene_id=scene_objs[2].id, scene_group_id=g1.id, stage_key="layout_character", media_type="image", filename="lo_char_v1.psd", original_name="lo_char_v1.psd", storage_path="", version=1, note="LO人物初稿", uploaded_by=user_map["artist2"]),
            Asset(project_id=p1.id, scene_group_id=g1.id, stage_key="reference", media_type="image", is_global=True, filename="char_design_hero.jpg", original_name="char_design_hero.jpg", storage_path="", version=1, note="主角人设图", uploaded_by=user_map["director1"]),
            Asset(project_id=p1.id, scene_group_id=g1.id, stage_key="reference", media_type="image", is_global=True, filename="bg_forest.jpg", original_name="bg_forest.jpg", storage_path="", version=1, note="森林背景设定", uploaded_by=user_map["director1"]),
        ]
        db.add_all(assets)
        db.flush()

        # 10. Annotations
        annotations = [
            Annotation(project_id=p1.id, target_asset_id=assets[0].id, target_version=1, author_id=user_map["director1"], author_role="director", canvas_json={"objects": []}, summary="构图OK"),
        ]
        db.add_all(annotations)

        # 11. BankMaterial
        bm = BankMaterial(
            project_id=p1.id, source_asset_id=assets[0].id, source_scene_id=scene_objs[0].id,
            source_stage_key="storyboard", name="路飞_坐着_身体", character_name="路飞", part_name="身体",
            pose="坐着", angle="正面", current_version=1, ref_count=1, created_by=user_map["director1"],
        )
        db.add(bm)
        db.flush()

        # 12. BankReference
        br = BankReference(
            bank_material_id=bm.id, project_id=p1.id, scene_id=scene_objs[3].id,
            stage_key="ai_draw", version=1, status="active", created_by=user_map["artist1"],
        )
        db.add(br)

        # 13. Reference
        ref = Reference(
            project_id=p1.id, source_type="asset", source_id=assets[0].id,
            target_type="asset", target_id=assets[8].id, relation_type="mention", created_by=user_map["director1"],
        )
        db.add(ref)

        # 14. Notifications
        notifications = [
            Notification(project_id=p1.id, user_id=user_map["artist1"], type="review", title="SC001 分镜已通过", content="导演A 通过了 SC001 的分镜审批", status="unread"),
            Notification(project_id=p1.id, user_id=user_map["artist1"], type="review", title="SC001 AI抽卡已通过", content="导演A 通过了 SC001 的AI抽卡审批", status="unread"),
        ]
        db.add_all(notifications)

        db.commit()
        print("Seed data created successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
