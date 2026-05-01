#!/usr/bin/env python3
"""Seed minimal demo data for frontend integration testing."""

from datetime import datetime

from pathlib import Path
import sys

import cv2
import numpy as np
from sqlalchemy import text
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings
from app.core.auth import generate_api_key
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.domains.stage_templates import build_default_stage_progress
from app.models.admin import (
    AccountPoolAccount,
    AccountProjectMembership,
    GenerationResult,
    GenerationTask,
    GenerationTemplate,
    ImageGroup,
    ImageGroupImage,
    PromptTemplate,
)
from app.models.annotation import Annotation, AnnotationAttachment
from app.models.asset import Asset, AssetAttachment
from app.models.bank import BankMaterial, BankReference
from app.models.notification import Notification
from app.models.project import Episode, Project, SceneAssignment, SceneGroup, UserProjectMembership
from app.models.reference import Reference
from app.models.scene import Scene, StageProgress
from app.models.user import User


def ensure_demo_media_files() -> dict[str, str]:
    """Create deterministic demo media files used by seed data."""
    media_root = settings.media_root_path
    demo_dir = media_root / "demo"
    annotation_dir = demo_dir / "annotations"
    demo_dir.mkdir(parents=True, exist_ok=True)
    annotation_dir.mkdir(parents=True, exist_ok=True)

    def create_jpeg(path: Path, color: tuple[int, int, int], label: str) -> None:
        if path.exists():
            return
        image = Image.new("RGB", (960, 540), color)
        image.save(path, format="JPEG", quality=92)

    def create_png(path: Path, color: tuple[int, int, int, int]) -> None:
        if path.exists():
            return
        image = Image.new("RGBA", (960, 540), color)
        image.save(path, format="PNG")

    def create_mp4(path: Path) -> None:
        if path.exists():
            return
        writer = cv2.VideoWriter(
            str(path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            6.0,
            (640, 360),
        )
        for idx in range(18):
            frame = np.zeros((360, 640, 3), dtype=np.uint8)
            frame[:] = (40 + idx * 4, 70 + idx * 3, 120 + idx * 2)
            cv2.putText(
                frame,
                f"SC005 PREVIEW {idx + 1:02d}",
                (40, 185),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            writer.write(frame)
        writer.release()

    create_jpeg(demo_dir / "ai_result_v1.jpg", (85, 120, 180), "AI V1")
    create_jpeg(demo_dir / "ai_result_v2.jpg", (120, 90, 160), "AI V2")
    create_jpeg(demo_dir / "char_design_hero.jpg", (150, 110, 90), "HERO")
    create_jpeg(demo_dir / "bg_forest.jpg", (60, 120, 80), "FOREST")
    create_jpeg(demo_dir / "scene005_preview.jpg", (80, 80, 120), "PREVIEW")
    create_png(annotation_dir / "frame142-overlay.png", (255, 0, 0, 80))
    create_png(annotation_dir / "frame142-merged.png", (255, 255, 255, 255))
    create_mp4(demo_dir / "scene005_preview.mp4")

    return {
        "ai_result_v1": "demo/ai_result_v1.jpg",
        "ai_result_v2": "demo/ai_result_v2.jpg",
        "char_design_hero": "demo/char_design_hero.jpg",
        "bg_forest": "demo/bg_forest.jpg",
        "scene005_preview_mp4": "demo/scene005_preview.mp4",
        "scene005_preview_jpg": "demo/scene005_preview.jpg",
        "overlay_png": "demo/annotations/frame142-overlay.png",
        "merged_png": "demo/annotations/frame142-merged.png",
    }


def clear_tables(db) -> None:
    """Clear all data using TRUNCATE with CASCADE."""
    tables = [
        "references",
        "audit_logs",
        "auth_sessions",
        "generation_results",
        "generation_tasks",
        "generation_templates",
        "image_group_images",
        "image_groups",
        "prompt_templates",
        "account_project_memberships",
        "account_pool_accounts",
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
        demo_media = ensure_demo_media_files()

        # 1. Users
        users = [
            User(username="admin", display_name="系统管理员", email="admin@studio.com", role="admin", api_key=generate_api_key(), password_hash=hash_password("admin123"), is_active=True),
            User(username="director1", display_name="导演A", email="director.a@studio.com", role="director", api_key=generate_api_key(), password_hash=hash_password("director123"), is_active=True),
            User(username="director2", display_name="导演B", email="director.b@studio.com", role="director", api_key=generate_api_key(), password_hash=hash_password("director123"), is_active=True),
            User(username="producer1", display_name="制片人小王", email="producer@studio.com", role="producer", api_key=generate_api_key(), password_hash=hash_password("producer123"), is_active=True),
            User(username="artist1", display_name="画师小红", email="artist.red@studio.com", role="artist", api_key=generate_api_key(), password_hash=hash_password("artist123"), is_active=True),
            User(username="artist2", display_name="画师小明", email="artist.ming@studio.com", role="artist", api_key=generate_api_key(), password_hash=hash_password("artist123"), is_active=True),
            User(username="artist3", display_name="画师小蓝", email="artist.blue@studio.com", role="artist", api_key=generate_api_key(), password_hash=hash_password("artist123"), is_active=True),
            User(username="visitor1", display_name="访客小张", email="visitor.zhang@studio.com", role="visitor", api_key=generate_api_key(), password_hash=hash_password("visitor123"), is_active=True),
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
            {"project_id": p2.id, "scene_group_id": g3.id, "name": "SC002", "description": "机甲起飞镜头", "level": "S", "stage_template": "standard_keyframe_review", "pipeline": "standard_keyframe_review", "frame_count": 36, "sort_order": 2, "created_by": user_map["director2"]},
            {"project_id": p2.id, "scene_group_id": g3.id, "name": "SC003", "description": "机库调度镜头", "level": "B", "stage_template": "standard_second_review", "pipeline": "standard_second_review", "frame_count": 30, "sort_order": 3, "created_by": user_map["director2"]},
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
        _create_sp(scene_objs[3], {"storyboard": "approved", "ai_draw": "rejected", "correction": "pending"})
        _create_sp(scene_objs[4], {"storyboard": "approved", "ai_draw": "approved", "correction": "approved", "final": "reviewing"})
        _create_sp(scene_objs[5], {"storyboard": "approved", "ai_draw": "pending"})
        _create_sp(scene_objs[6], {"storyboard": "approved", "layout_character": "approved", "layout_background": "approved", "keyframe": "reviewing"})
        for s in scene_objs[7:]:
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
            Asset(project_id=p1.id, scene_id=scene_objs[0].id, scene_group_id=g1.id, stage_key="ai_draw", media_type="image", filename="ai_result_v1.jpg", original_name="ai_result.jpg", storage_path=demo_media["ai_result_v1"], public_url=f'/media/{demo_media["ai_result_v1"]}', version=1, note="第一轮抽卡", uploaded_by=user_map["artist1"]),
            Asset(project_id=p1.id, scene_id=scene_objs[0].id, scene_group_id=g1.id, stage_key="ai_draw", media_type="image", filename="ai_result_v2.jpg", original_name="ai_result.jpg", storage_path=demo_media["ai_result_v2"], public_url=f'/media/{demo_media["ai_result_v2"]}', version=2, note="光影修正版", uploaded_by=user_map["artist1"]),
            Asset(project_id=p1.id, scene_id=scene_objs[0].id, scene_group_id=g1.id, stage_key="correction", media_type="binary", filename="correct_v1.psd", original_name="correct_v1.psd", storage_path="", version=1, note="修正初稿", uploaded_by=user_map["artist1"]),
            Asset(project_id=p1.id, scene_id=scene_objs[0].id, scene_group_id=g1.id, stage_key="reference", media_type="image", filename="ref_pose.jpg", original_name="ref_pose.jpg", storage_path="", version=1, uploaded_by=user_map["artist1"]),
            Asset(project_id=p1.id, scene_id=scene_objs[1].id, scene_group_id=g1.id, stage_key="storyboard", media_type="image", filename="board_sc02.jpg", original_name="board_sc02.jpg", storage_path="", version=1, uploaded_by=user_map["artist2"]),
            Asset(project_id=p1.id, scene_id=scene_objs[2].id, scene_group_id=g1.id, stage_key="storyboard", media_type="image", filename="board_sc03.jpg", original_name="board_sc03.jpg", storage_path="", version=1, uploaded_by=user_map["artist2"]),
            Asset(project_id=p1.id, scene_id=scene_objs[2].id, scene_group_id=g1.id, stage_key="layout_character", media_type="image", filename="lo_char_v1.psd", original_name="lo_char_v1.psd", storage_path="", version=1, note="LO人物初稿", uploaded_by=user_map["artist2"]),
            Asset(project_id=p1.id, scene_group_id=g1.id, stage_key="reference", media_type="image", is_global=True, filename="char_design_hero.jpg", original_name="char_design_hero.jpg", storage_path=demo_media["char_design_hero"], public_url=f'/media/{demo_media["char_design_hero"]}', version=1, note="主角人设图", uploaded_by=user_map["director1"]),
            Asset(project_id=p1.id, scene_group_id=g1.id, stage_key="reference", media_type="image", is_global=True, filename="bg_forest.jpg", original_name="bg_forest.jpg", storage_path=demo_media["bg_forest"], public_url=f'/media/{demo_media["bg_forest"]}', version=1, note="森林背景设定", uploaded_by=user_map["director1"]),
            Asset(project_id=p1.id, scene_id=scene_objs[4].id, scene_group_id=g2.id, stage_key="final", media_type="video", filename="scene005_preview.mp4", original_name="scene005_preview.mp4", storage_path=demo_media["scene005_preview_mp4"], public_url=f'/media/{demo_media["scene005_preview_mp4"]}', thumbnail_path=demo_media["scene005_preview_jpg"], thumbnail_url=f'/media/{demo_media["scene005_preview_jpg"]}', version=1, note="导演预览片段", metadata_json={"durationSeconds": 3.0, "width": 640, "height": 360}, uploaded_by=user_map["artist3"]),
        ]
        db.add_all(assets)
        db.flush()

        asset_attachments = [
            AssetAttachment(
                asset_id=assets[2].id,
                filename="ai_result_notes.pdf",
                media_type="binary",
                storage_path="projects/demo/attachments/ai_result_notes.pdf",
                public_url="/media/projects/demo/attachments/ai_result_notes.pdf",
                size_bytes=1024,
                uploaded_by=user_map["artist1"],
            )
        ]
        db.add_all(asset_attachments)

        # 10. Annotations
        annotations = [
            Annotation(project_id=p1.id, target_asset_id=assets[0].id, target_version=1, author_id=user_map["director1"], author_role="director", canvas_json={"objects": []}, summary="构图OK"),
            Annotation(
                project_id=p1.id,
                target_asset_id=assets[9].id,
                target_version=1,
                author_id=user_map["director1"],
                author_role="director",
                frame_number=142,
                timestamp_seconds=1.184,
                canvas_json={"objects": [{"type": "circle"}]},
                overlay_path=demo_media["overlay_png"],
                overlay_url=f'/media/{demo_media["overlay_png"]}',
                merged_path=demo_media["merged_png"],
                merged_url=f'/media/{demo_media["merged_png"]}',
                summary="第142帧角色手臂透视需要修正",
            ),
        ]
        db.add_all(annotations)
        db.flush()

        annotation_attachments = [
            AnnotationAttachment(
                annotation_id=annotations[1].id,
                filename="director-note.png",
                media_type="image",
                storage_path="projects/demo/annotation-attachments/director-note.png",
                public_url="/media/projects/demo/annotation-attachments/director-note.png",
                size_bytes=2048,
                uploaded_by=user_map["director1"],
            )
        ]
        db.add_all(annotation_attachments)

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

        # 15. Account pool
        accounts = [
            AccountPoolAccount(name="工作室主账号", email="studio.main@gmail.com", provider="gemini", status="active", success_count=1248, fail_count=12, remark="主力账号，优先使用", created_by=user_map["admin"]),
            AccountPoolAccount(name="备用账号A", email="backup.a@gmail.com", provider="gemini", status="active", success_count=856, fail_count=8, created_by=user_map["admin"]),
            AccountPoolAccount(name="备用账号B", email="backup.b@gmail.com", provider="gemini", status="cooldown", success_count=623, fail_count=45, remark="近期失败率较高，冷却中", created_by=user_map["admin"]),
        ]
        db.add_all(accounts)
        db.flush()
        db.add_all(
            [
                AccountProjectMembership(account_id=accounts[0].id, project_id=p1.id),
                AccountProjectMembership(account_id=accounts[0].id, project_id=p2.id),
                AccountProjectMembership(account_id=accounts[1].id, project_id=p1.id),
                AccountProjectMembership(account_id=accounts[2].id, project_id=p2.id),
            ]
        )

        # 16. Prompts
        prompts = [
            PromptTemplate(name="通用角色立绘", content="生成一位动漫风格角色立绘，全身，纯白背景，高精度，细节丰富", aspect_ratio="auto", resolution="2k", scope="global", use_count=156, created_by=user_map["admin"]),
            PromptTemplate(name="奇幻角色服装方案", content="为奇幻冒险角色设计服装方案，包含三视图，华丽的魔法袍，配饰精致", aspect_ratio="16:9", resolution="4k", scope="project", project_id=p1.id, use_count=89, created_by=user_map["director1"]),
            PromptTemplate(name="小红的私有模板", content="日系萌系角色设计，大眼睛，可爱表情，柔和光影", aspect_ratio="auto", resolution="1k", scope="private", user_id=user_map["artist1"], use_count=23, created_by=user_map["artist1"]),
        ]
        db.add_all(prompts)
        db.flush()

        # 17. Image groups
        groups = [
            ImageGroup(name="主角A参考图集", description="主角A的角色设定参考图片", project_id=p1.id, user_id=user_map["artist1"]),
            ImageGroup(name="服装材质参考", description="各种布料材质参考图片", project_id=p1.id, user_id=user_map["director1"], is_shared=True),
            ImageGroup(name="小蓝私有图组", description="个人收集的参考图", user_id=user_map["artist3"]),
        ]
        db.add_all(groups)
        db.flush()
        db.add_all(
            [
                ImageGroupImage(image_group_id=groups[0].id, name="ref_01.jpg", url="https://picsum.photos/seed/ref101/300/400", sort_order=0),
                ImageGroupImage(image_group_id=groups[0].id, name="ref_02.jpg", url="https://picsum.photos/seed/ref102/300/400", sort_order=1),
                ImageGroupImage(image_group_id=groups[1].id, name="fabric_01.jpg", url="https://picsum.photos/seed/fabric301/300/300", sort_order=0),
                ImageGroupImage(image_group_id=groups[2].id, name="private_01.jpg", url="https://picsum.photos/seed/private501/300/300", sort_order=0),
            ]
        )

        # 18. Generation templates
        templates = [
            GenerationTemplate(name="一原通用模板", description="动漫风格全身立绘", snapshot_json={"imageGroupId": groups[0].id, "prompt": prompts[0].content, "aspectRatio": "auto", "resolution": "2k", "count": 4}, user_id=user_map["artist1"], created_by=user_map["artist1"]),
            GenerationTemplate(name="服装方案模板", description="奇幻冒险服装三视图", snapshot_json={"imageGroupId": groups[1].id, "prompt": prompts[1].content, "aspectRatio": "16:9", "resolution": "4k", "count": 4}, project_id=p1.id, created_by=user_map["director1"]),
        ]
        db.add_all(templates)
        db.flush()

        # 19. Generation tasks and results
        tasks = [
            GenerationTask(user_id=user_map["artist1"], project_id=p1.id, scene_id=scene_objs[0].id, stage_key="keyframe", account_id=accounts[0].id, image_group_id=groups[0].id, prompt_id=prompts[0].id, prompt_content=prompts[0].content, aspect_ratio="auto", resolution="2k", status="success", result_count=4, requested_count=4, completed_at=datetime.utcnow()),
            GenerationTask(user_id=user_map["artist2"], project_id=p1.id, scene_id=scene_objs[1].id, stage_key="keyframe", account_id=accounts[0].id, image_group_id=groups[1].id, prompt_id=prompts[1].id, prompt_content=prompts[1].content, aspect_ratio="16:9", resolution="4k", status="running", result_count=0, requested_count=4),
            GenerationTask(user_id=user_map["artist3"], project_id=p2.id, scene_id=scene_objs[6].id, stage_key="inbetween", account_id=accounts[2].id, image_group_id=groups[2].id, prompt_content="自定义提示词：科幻机甲战士立绘", aspect_ratio="auto", resolution="2k", status="failed", result_count=0, requested_count=4, fail_reason="账号调用超时，请稍后重试"),
        ]
        db.add_all(tasks)
        db.flush()
        results = [
            GenerationResult(task_id=tasks[0].id, user_id=user_map["artist1"], project_id=p1.id, scene_id=scene_objs[0].id, stage_key="keyframe", image_group_id=groups[0].id, prompt_id=prompts[0].id, name="EP01_SC01_keyframe_01_0418", url="https://picsum.photos/seed/result1/400/600", thumbnail_url="https://picsum.photos/seed/result1/200/300", status="approved", review_comment="构图不错，光影方向统一", reviewed_by=user_map["director1"], reviewed_at=datetime.utcnow()),
            GenerationResult(task_id=tasks[0].id, user_id=user_map["artist1"], project_id=p1.id, scene_id=scene_objs[0].id, stage_key="keyframe", image_group_id=groups[0].id, prompt_id=prompts[0].id, name="EP01_SC01_keyframe_02_0418", url="https://picsum.photos/seed/result2/400/600", thumbnail_url="https://picsum.photos/seed/result2/200/300", status="rejected", review_comment="角色比例崩了，头部过大", reviewed_by=user_map["director1"], reviewed_at=datetime.utcnow()),
            GenerationResult(task_id=tasks[0].id, user_id=user_map["artist1"], project_id=p1.id, scene_id=scene_objs[0].id, stage_key="keyframe", image_group_id=groups[0].id, prompt_id=prompts[0].id, name="EP01_SC01_keyframe_03_0418", url="https://picsum.photos/seed/result3/400/600", thumbnail_url="https://picsum.photos/seed/result3/200/300", status="submitted"),
            GenerationResult(task_id=tasks[0].id, user_id=user_map["artist1"], project_id=p1.id, scene_id=scene_objs[0].id, stage_key="keyframe", image_group_id=groups[0].id, prompt_id=prompts[0].id, name="EP01_SC01_keyframe_04_0418", url="https://picsum.photos/seed/result4/400/600", thumbnail_url="https://picsum.photos/seed/result4/200/300", status="discarded"),
        ]
        db.add_all(results)

        db.commit()
        print("Seed data created successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
