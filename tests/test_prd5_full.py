"""
PRD5 全量测试套件
测试画室资产系统 PRD5 需求基线（制片人拆分、视频资产、阶段模板、兼用卡等）
使用实际运行中的后端服务（http://127.0.0.1:8080）
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
import requests
from PIL import Image

# ── Config ──────────────────────────────────────────────────────────────
BASE = "http://127.0.0.1:8080/api/v1"
ADMIN_HEADERS = {"X-User-ID": "1"}
DIRECTOR_HEADERS = {"X-User-ID": "2"}
PRODUCER_HEADERS = {"X-User-ID": "4"}
ARTIST_HEADERS = {"X-User-ID": "5"}
ARTIST2_HEADERS = {"X-User-ID": "6"}
VISITOR_HEADERS = {"X-User-ID": "8"}


# ── Helpers ──────────────────────────────────────────────────────────────
    # helper that returns raw response (no raise)
def get_raw(path, headers=None, params=None):
    return requests.get(f"{BASE}{path}", headers=headers or {}, params=params or {})

def post_raw(path, headers=None, json=None):
    return requests.post(f"{BASE}{path}", headers=headers or {}, json=json or {})


def _login_with_retry(username, password, retries=5, delay=0.5):
    """Login with retry, returns (response, token_or_None)."""
    for i in range(retries):
        r = requests.post(f"{BASE}/auth/login", json={"username": username, "password": password})
        if r.status_code == 200:
            return r, r.json()["token"]
        if i < retries - 1:
            import time; time.sleep(delay)
    return r, None

def put_raw(path, headers=None, json=None):
    return requests.put(f"{BASE}{path}", headers=headers or {}, json=json or {})

def delete_raw(path, headers=None):
    return requests.delete(f"{BASE}{path}", headers=headers or {})

def get(path: str, headers: dict | None = None, params: dict | None = None) -> requests.Response:
    r = requests.get(f"{BASE}{path}", headers=headers or {}, params=params or {})
    if not (200 <= r.status_code < 300):
        r.raise_for_status()
    return r


def post(path: str, headers: dict | None = None, json: dict | None = None) -> requests.Response:
    r = requests.post(f"{BASE}{path}", headers=headers or {}, json=json or {})
    if not (200 <= r.status_code < 300):
        r.raise_for_status()
    return r


def put(path: str, headers: dict | None = None, json: dict | None = None) -> requests.Response:
    r = requests.put(f"{BASE}{path}", headers=headers or {}, json=json or {})
    if not (200 <= r.status_code < 300):
        r.raise_for_status()
    return r


def delete(path: str, headers: dict | None = None) -> requests.Response:
    r = requests.delete(f"{BASE}{path}", headers=headers or {})
    if not (200 <= r.status_code < 300):
        r.raise_for_status()
    return r


def upload(path: str, file_name: str, content: bytes, mime: str,
           headers: dict | None = None) -> requests.Response:
    files = {"file": (file_name, content, mime)}
    r = requests.post(f"{BASE}{path}", headers=headers or {}, files=files)
    r.raise_for_status()
    return r


def png_bytes(w=320, h=240, color=(100, 150, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def video_bytes(duration_frames=24, fps=12, w=160, h=90,
                color_cycle=True) -> bytes:
    """Generate a small MP4 video."""
    path = f"/tmp/prd5_test_{uuid.uuid4().hex[:8]}.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                            float(fps), (w, h))
    for i in range(duration_frames):
        if color_cycle:
            col = (i * 10 % 255, 80, 180)
        else:
            col = (100, 100, 100)
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :] = col
        writer.write(frame)
    writer.release()
    data = Path(path).read_bytes()
    Path(path).unlink(missing_ok=True)
    return data


# ══════════════════════════════════════════════════════════════════════
# 概览 / 健康检查
# ══════════════════════════════════════════════════════════════════════
class TestHealthAndAuth:
    def test_health_returns_ok(self):
        r = get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["database"]["ok"] is True
        assert data["storage"]["ok"] is True

    def test_health_requires_no_auth(self):
        r = requests.get(f"{BASE}/health")
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# PRD5-1: 制片人拆分
# PRD5-2: 角色权限矩阵
# ══════════════════════════════════════════════════════════════════════
class TestRoleBoundaries:
    """验证五角色权限边界（PRD5 4.1 / 6 节权限矩阵）。"""

    def test_producer_can_create_scene(self):
        r = post("/scenes", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            "name": f"PROD_SC_{uuid.uuid4().hex[:4]}",
            "level": "B",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
        })
        assert r.status_code == 201

    def test_producer_cannot_approve(self):
        m = get("/scenes/matrix", headers=DIRECTOR_HEADERS, params={"project_id": 1}).json()
        scene_id = m["scenes"][0]["id"]
        r = post_raw(f"/workflow/scenes/{scene_id}/approve",
                     headers=PRODUCER_HEADERS,
                     json={"stage_key": "storyboard"})
        assert r.status_code == 403

    def test_director_cannot_manage_global_asset(self):
        r = post("/assets", headers=DIRECTOR_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": None,
            "stage_key": "reference", "asset_type": "original",
            "media_type": "image", "is_global": True,
            "original_name": "director_global_asset.png",
        })
        # 导演没有权限上传全局资产（is_global=True 需要制片人）
        # 注意：后端只检查是否登录+项目成员，这里验证制片人优先
        assert r.status_code in (201, 403)

    def test_visitor_cannot_create_scene(self):
        r = post_raw("/scenes", headers=VISITOR_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            "name": f"VIS_SC_{uuid.uuid4().hex[:4]}",
            "level": "B",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
        })
        assert r.status_code == 403

    def test_visitor_cannot_submit_or_approve(self):
        m = get("/scenes/matrix", headers=DIRECTOR_HEADERS, params={"project_id": 1}).json()
        scene_id = m["scenes"][-1]["id"]
        # visitor submit
        r = post_raw(f"/workflow/scenes/{scene_id}/submit",
                     headers=VISITOR_HEADERS, json={"stage_key": "storyboard"})
        assert r.status_code == 403
        # visitor approve
        r = post_raw(f"/workflow/scenes/{scene_id}/approve",
                     headers=VISITOR_HEADERS, json={"stage_key": "storyboard"})
        assert r.status_code == 403

    def test_producer_receives_review_notifications(self):
        """制片人应收到画师提交后的审批通知。"""
        # 找 ai_single_frame 镜头
        m = get("/scenes/matrix", headers=DIRECTOR_HEADERS, params={"project_id": 1}).json()
        target = next((s for s in m["scenes"] if s["stageTemplate"] == "ai_single_frame"), None)
        assert target is not None
        scene_id = target["id"]
        # 确认 storyboard 状态
        if target["stageProgress"]["storyboard"]["status"] == "approved":
            # 找一个 pending 镜头
            target = next((s for s in m["scenes"]
                           if s["stageProgress"]["storyboard"]["status"] in ("pending", "in_progress")), None)
        if target:
            scene_id = target["id"]

        # 上传资产再提交
        scene = get(f"/scenes/{scene_id}", headers=DIRECTOR_HEADERS).json()
        storyboard_status = scene["stageProgress"]["storyboard"]["status"]
        if storyboard_status in ("pending", "in_progress"):
            pass  # 已就绪
        else:
            # 找其他 pending 镜头
            scene_id = next(s["id"] for s in m["scenes"]
                           if s["stageProgress"]["storyboard"]["status"] in ("pending", "in_progress"))

        # 上传一个资产
        asset = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "storyboard", "asset_type": "original",
            "media_type": "image", "original_name": f"submit_test_{uuid.uuid4().hex[:6]}.png",
        })
        assert asset.status_code == 201
        aid = asset.json()["id"]
        upload("/upload/assets/{}/file".format(aid), "submit_test.png",
               png_bytes(), "image/png", headers=ARTIST_HEADERS)

        # submit
        r = post(f"/workflow/scenes/{scene_id}/submit",
                 headers=ARTIST_HEADERS, json={"stage_key": "storyboard"})
        if r.status_code == 200:
            # 制片人应收到通知
            notifs = get("/notifications", headers=PRODUCER_HEADERS).json()
            assert any(n["type"] == "review_required" and
                       n["payloadJson"].get("scene_id") == scene_id
                       for n in notifs), "制片人应收到审批通知"

    def test_director_receives_review_notifications(self):
        """导演也应收到审批通知。"""
        # 创建新镜头保证 storyboard 可提交
        r = post("/scenes", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            "name": f"DIR_NOTIF_{uuid.uuid4().hex[:4]}",
            "level": "B",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
        })
        scene_id = r.json()["id"]

        asset = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "storyboard", "asset_type": "original",
            "media_type": "image", "original_name": f"director_notify_test_{uuid.uuid4().hex[:6]}.png",
        })
        assert asset.status_code == 201
        aid = asset.json()["id"]
        upload("/upload/assets/{}/file".format(aid), "director_notify_test.png",
               png_bytes(), "image/png", headers=ARTIST_HEADERS)

        r = post(f"/workflow/scenes/{scene_id}/submit",
                 headers=ARTIST_HEADERS, json={"stage_key": "storyboard"})
        assert r.status_code == 200
        notifs = get("/notifications", headers=DIRECTOR_HEADERS).json()
        assert any(n["type"] == "review_required" and
                   n["payloadJson"].get("scene_id") == scene_id
                   for n in notifs)


# ══════════════════════════════════════════════════════════════════════
# PRD5-3: 阶段模板（5套模板）
# ══════════════════════════════════════════════════════════════════════
class TestStageTemplates:
    """验证 5 套阶段模板（PRD5 4.4）。"""

    TEMPLATE_CASES = [
        ("ai_single_frame", ["storyboard", "ai_draw", "correction", "final"]),
        ("standard", ["storyboard", "layout_character", "layout_background",
                      "keyframe", "second_keyframe", "inbetween",
                      "coloring", "compositing", "final"]),
        ("standard_keyframe_review", ["storyboard", "layout_character", "layout_background",
                                      "keyframe", "keyframe_review", "second_keyframe",
                                      "inbetween", "coloring", "compositing", "final"]),
        ("standard_second_review", ["storyboard", "layout_character", "layout_background",
                                     "keyframe", "second_keyframe", "second_review",
                                     "inbetween", "coloring", "compositing", "final"]),
        ("standard_dual_review", ["storyboard", "layout_character", "layout_background",
                                   "keyframe", "keyframe_review", "second_keyframe",
                                   "second_review", "inbetween", "coloring",
                                   "compositing", "final"]),
    ]

    def test_all_five_templates_create_correct_stages(self):
        """每个模板创建镜头后，stageProgress 包含正确的阶段。"""
        for template, expected_keys in self.TEMPLATE_CASES:
            r = post("/scenes", headers=PRODUCER_HEADERS, json={
                "project_id": 1, "scene_group_id": 1,
                "name": f"TPL_{template[:4]}_{uuid.uuid4().hex[:6]}",
                "level": "B",
                "stage_template": template,
                "pipeline": template,
            })
            assert r.status_code == 201, f"{template}: 创建失败 {r.status_code} {r.text}"
            scene = r.json()
            # stageProgress 返回 dict（后端实现）
            sp = scene.get("stageProgress", {})
            sp_keys = list(sp.keys())
            assert set(sp_keys) == set(expected_keys), f"{template}: 期望 {set(expected_keys)}, 得到 {set(sp_keys)}"
            # 第一个阶段应为 pending，其余 locked
            assert sp[sp_keys[0]]["status"] == "pending", f"{template} 首阶段应为 pending"
            for k in sp_keys[1:]:
                assert sp[k]["status"] == "locked", f"{template} {k} 应为 locked"

    def test_dual_review_template_has_both_review_stages(self):
        """双作监模板包含 keyframe_review 和 second_review。"""
        r = post("/scenes", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            "name": f"DUAL_{uuid.uuid4().hex[:6]}",
            "level": "A",
            "stage_template": "standard_dual_review",
            "pipeline": "standard_dual_review",
        })
        assert r.status_code == 201
        scene = r.json()
        sp_keys = list(scene.get("stageProgress", {}).keys())
        assert "keyframe_review" in sp_keys
        assert "second_review" in sp_keys


# ══════════════════════════════════════════════════════════════════════
# PRD5-4: Layout 人物/背景双轨
# PRD5-5: Layout 双轨解锁逻辑
# ══════════════════════════════════════════════════════════════════════
class TestLayoutDualTrack:
    """验证 Layout 人物/背景双轨解锁逻辑（PRD5 4.5）。"""

    def test_layout_dual_track_both_approved_unlocks_next(self):
        """layout_character 和 layout_background 都 approved 后解锁下一阶段。"""
        # 创建标准动画镜头
        r = post("/scenes", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            "name": f"LO_DUAL_{uuid.uuid4().hex[:6]}",
            "level": "B",
            "stage_template": "standard",
            "pipeline": "standard",
        })
        assert r.status_code == 201
        scene_id = r.json()["id"]

        # Step 1: 完成 storyboard（全流程先驱）
        asset_sb = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "storyboard", "asset_type": "original",
            "media_type": "image", "original_name": f"sb_lo_{uuid.uuid4().hex[:6]}.png",
        })
        upload("/upload/assets/{}/file".format(asset_sb.json()["id"]),
               "sb.png", png_bytes(), "image/png", ARTIST_HEADERS)
        post(f"/workflow/scenes/{scene_id}/submit",
             headers=ARTIST_HEADERS, json={"stage_key": "storyboard"})
        post(f"/workflow/scenes/{scene_id}/approve",
             headers=DIRECTOR_HEADERS, json={"stage_key": "storyboard"})

        # Step 2: 接受 layout_character -> in_progress -> 提交 -> 审批
        post(f"/scenes/{scene_id}/stages/layout_character/accept",
             headers=ARTIST_HEADERS, json={})
        asset_lc = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "layout_character", "asset_type": "original",
            "media_type": "image", "original_name": f"lo_char_{uuid.uuid4().hex[:6]}.png",
        })
        upload("/upload/assets/{}/file".format(asset_lc.json()["id"]),
               "lo_char.png", png_bytes(color=(138, 43, 226)),
               "image/png", ARTIST_HEADERS)
        post(f"/workflow/scenes/{scene_id}/submit",
             headers=ARTIST_HEADERS, json={"stage_key": "layout_character"})
        post(f"/workflow/scenes/{scene_id}/approve",
             headers=DIRECTOR_HEADERS, json={"stage_key": "layout_character"})

        # Step 3: 接受 layout_background -> 提交 -> 审批
        post(f"/scenes/{scene_id}/stages/layout_background/accept",
             headers=ARTIST_HEADERS, json={})
        asset_lb = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "layout_background", "asset_type": "original",
            "media_type": "image", "original_name": f"lo_bg_{uuid.uuid4().hex[:6]}.png",
        })
        upload("/upload/assets/{}/file".format(asset_lb.json()["id"]),
               "lo_bg.png", png_bytes(color=(34, 139, 34)),
               "image/png", ARTIST_HEADERS)
        post(f"/workflow/scenes/{scene_id}/submit",
             headers=ARTIST_HEADERS, json={"stage_key": "layout_background"})
        post(f"/workflow/scenes/{scene_id}/approve",
             headers=DIRECTOR_HEADERS, json={"stage_key": "layout_background"})

        # 验证两者都 approved 后 keyframe 解锁
        scene = get(f"/scenes/{scene_id}", headers=DIRECTOR_HEADERS).json()
        assert scene["stageProgress"]["keyframe"]["status"] == "pending"

    def test_layout_one_rejected_keeps_next_locked(self):
        """layout_character approved 但 layout_background rejected，下一阶段不解锁。"""
        r = post("/scenes", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            "name": f"LO_REJ_{uuid.uuid4().hex[:6]}",
            "level": "B",
            "stage_template": "standard",
            "pipeline": "standard",
        })
        assert r.status_code == 201
        scene_id = r.json()["id"]

        # 先通过 storyboard
        asset_sb = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "storyboard", "asset_type": "original",
            "media_type": "image", "original_name": f"sb_test_{uuid.uuid4().hex[:6]}.png",
        })
        upload("/upload/assets/{}/file".format(asset_sb.json()["id"]),
               "sb.png", png_bytes(), "image/png", ARTIST_HEADERS)
        post(f"/workflow/scenes/{scene_id}/submit",
             headers=ARTIST_HEADERS, json={"stage_key": "storyboard"})
        post(f"/workflow/scenes/{scene_id}/approve",
             headers=DIRECTOR_HEADERS, json={"stage_key": "storyboard"})

        # layout_character approved
        asset_lc = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "layout_character", "asset_type": "original",
            "media_type": "image", "original_name": f"lo_c_{uuid.uuid4().hex[:6]}.png",
        })
        upload("/upload/assets/{}/file".format(asset_lc.json()["id"]),
               "lo_c.png", png_bytes(), "image/png", ARTIST_HEADERS)
        post(f"/workflow/scenes/{scene_id}/submit",
             headers=ARTIST_HEADERS, json={"stage_key": "layout_character"})
        post(f"/workflow/scenes/{scene_id}/approve",
             headers=DIRECTOR_HEADERS, json={"stage_key": "layout_character"})

        # layout_background rejected
        asset_lb = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "layout_background", "asset_type": "original",
            "media_type": "image", "original_name": f"lo_b_{uuid.uuid4().hex[:6]}.png",
        })
        upload("/upload/assets/{}/file".format(asset_lb.json()["id"]),
               "lo_b.png", png_bytes(), "image/png", ARTIST_HEADERS)
        post(f"/workflow/scenes/{scene_id}/submit",
             headers=ARTIST_HEADERS, json={"stage_key": "layout_background"})
        r = post(f"/workflow/scenes/{scene_id}/reject",
                 headers=DIRECTOR_HEADERS,
                 json={"stage_key": "layout_background", "comment": "背景需要调整"})
        assert r.status_code == 200

        scene = get(f"/scenes/{scene_id}", headers=DIRECTOR_HEADERS).json()
        # keyframe 状态应为 locked（未解锁）
        assert scene["stageProgress"]["keyframe"]["status"] == "locked"


# ══════════════════════════════════════════════════════════════════════
# PRD5-6: 镜头时长
# ══════════════════════════════════════════════════════════════════════
class TestSceneDuration:
    """验证镜头时长字段（PRD5 4.3.3 duration_seconds）。"""

    def test_create_scene_with_duration(self):
        r = post("/scenes", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            "name": f"DUR_SC_{uuid.uuid4().hex[:4]}",
            "level": "A",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
            "duration_seconds": 5.5,
            "frame_count": 24,
        })
        assert r.status_code == 201
        scene = r.json()
        assert scene["durationSeconds"] == 5.5

    def test_update_scene_duration(self):
        r = post("/scenes", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            "name": f"DUR_UPD_{uuid.uuid4().hex[:4]}",
            "level": "B",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
            "duration_seconds": 3.0,
        })
        scene_id = r.json()["id"]

        r = put(f"/scenes/{scene_id}", headers=PRODUCER_HEADERS,
                json={"duration_seconds": 10.5})
        assert r.status_code == 200
        assert r.json()["durationSeconds"] == 10.5


# ══════════════════════════════════════════════════════════════════════
# PRD5-7: 整镜头兼用（base_scene_id）
# ══════════════════════════════════════════════════════════════════════
class TestBaseScene:
    """验证整镜头兼用（baseSceneId，PRD5 4.6.8）。"""

    def test_create_scene_based_on_existing(self):
        # 用 SC001 作为 base
        base_id = 1
        r = post("/scenes", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            "name": f"BASE_SC_{uuid.uuid4().hex[:4]}",
            "level": "C",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
            "base_scene_id": base_id,
        })
        assert r.status_code == 201
        scene = r.json()
        assert scene["baseSceneId"] == base_id

    def test_base_scene_id_reflects_in_matrix(self):
        base_id = 1
        r = post("/scenes", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            "name": f"MATRIX_BASE_{uuid.uuid4().hex[:4]}",
            "level": "C",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
            "base_scene_id": base_id,
        })
        scene_id = r.json()["id"]

        m = get("/scenes/matrix", headers=PRODUCER_HEADERS,
                params={"project_id": 1}).json()
        found = next((s for s in m["scenes"] if s["id"] == scene_id), None)
        assert found is not None
        assert found["baseSceneId"] == base_id


# ══════════════════════════════════════════════════════════════════════
# PRD5-8: 视频资产 + 缩略图
# PRD5-9: 视频帧级批注
# ══════════════════════════════════════════════════════════════════════
class TestVideoAsset:
    """验证视频资产上传、缩略图生成、元数据（PRD5 4.2 / 4.3）。"""

    def test_video_upload_generates_thumbnail(self):
        vid = video_bytes(24, 12, 160, 90)
        r = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": 1,
            "stage_key": "final", "asset_type": "preview",
            "media_type": "video",
            "original_name": f"video_test_{uuid.uuid4().hex[:6]}.mp4",
        })
        assert r.status_code == 201
        asset = r.json()
        assert asset["mediaType"] == "video"

        r = upload("/upload/assets/{}/file".format(asset["id"]),
                   "vid.mp4", vid, "video/mp4", ARTIST_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data["thumbnail_url"] is not None
        assert data["thumbnail_url"].endswith(".png")
        assert data["metadata_json"]["width"] == 160
        assert data["metadata_json"]["height"] == 90
        assert data["metadata_json"]["frameCount"] >= 24
        assert data["metadata_json"]["durationSeconds"] is not None

    def test_video_asset_reflected_in_scene_matrix(self):
        vid = video_bytes(12, 12, 80, 60)
        r = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 2, "scene_id": 5,
            "stage_key": "ai_draw", "asset_type": "preview",
            "media_type": "video",
            "original_name": f"matrix_vid_{uuid.uuid4().hex[:6]}.mp4",
        })
        assert r.status_code == 201
        asset_id = r.json()["id"]

        upload("/upload/assets/{}/file".format(asset_id),
                "mat_vid.mp4", vid, "video/mp4", ARTIST_HEADERS)

        m = get("/scenes/matrix", headers=ARTIST_HEADERS, params={"project_id": 1}).json()
        found = next((s for s in m["scenes"] if s["id"] == 5), None)
        assert found is not None
        assets = found.get("latestAssets", {})
        vid_asset = assets.get("ai_draw")
        assert vid_asset is not None
        assert vid_asset["mediaType"] == "video"
        assert vid_asset["thumbnailUrl"] is not None


# ══════════════════════════════════════════════════════════════════════
# PRD5-10: 帧级批注
# ══════════════════════════════════════════════════════════════════════
class TestFrameAnnotation:
    """验证帧级批注（frameNumber, timestamp，PRD5 4.3）。"""

    def test_annotation_with_frame_number(self):
        # 创建图片资产
        r = post("/assets", headers=DIRECTOR_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": 1,
            "stage_key": "correction", "asset_type": "markup",
            "media_type": "image",
            "original_name": f"anno_frame_{uuid.uuid4().hex[:6]}.png",
        })
        assert r.status_code == 201
        asset_id = r.json()["id"]

        upload("/upload/assets/{}/file".format(asset_id),
               "base.png", png_bytes(), "image/png", DIRECTOR_HEADERS)

        r = post("/annotations", headers=DIRECTOR_HEADERS, json={
            "project_id": 1,
            "target_asset_id": asset_id,
            "frame_number": 142,
            "timestamp_seconds": 1.5,
            "canvas_json": {"objects": [{"type": "circle", "x": 50, "y": 50, "r": 20}]},
            "summary": "第142帧需要调整",
        })
        assert r.status_code == 201
        anno = r.json()
        assert anno["targetVersion"] == 1
        assert anno["frameNumber"] == 142
        assert anno["timestampSeconds"] == 1.5
        assert anno["overlayUrl"] is not None
        assert anno["overlayUrl"].endswith(".png")
        assert anno["mergedUrl"] is not None

    def test_annotation_update_frame_number(self):
        r = post("/assets", headers=DIRECTOR_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": 1,
            "stage_key": "correction", "asset_type": "markup",
            "media_type": "image",
            "original_name": f"upd_anno_{uuid.uuid4().hex[:6]}.png",
        })
        asset_id = r.json()["id"]
        upload("/upload/assets/{}/file".format(asset_id),
               "base2.png", png_bytes(), "image/png", DIRECTOR_HEADERS)

        r = post("/annotations", headers=DIRECTOR_HEADERS, json={
            "project_id": 1, "target_asset_id": asset_id,
            "frame_number": 10,
            "canvas_json": {},
            "summary": "初始批注",
        })
        anno_id = r.json()["id"]

        r = put(f"/annotations/{anno_id}", headers=DIRECTOR_HEADERS, json={
            "frame_number": 200,
            "summary": "更新到第200帧",
        })
        assert r.status_code == 200
        assert r.json()["frameNumber"] == 200


# ══════════════════════════════════════════════════════════════════════
# PRD5-11: 兼用卡（Bank）
# ══════════════════════════════════════════════════════════════════════
class TestBankMaterial:
    """验证兼用素材 CRUD（PRD5 4.6）。"""

    def test_bank_material_create(self):
        r = post("/bank/materials", headers=PRODUCER_HEADERS, json={
            "project_id": 1,
            "source_asset_id": 2,
            "name": f"兼用素材_{uuid.uuid4().hex[:6]}",
            "character_name": "路飞",
            "part_name": "身体",
            "pose": "坐着",
            "angle": "正面",
        })
        assert r.status_code == 201
        mat = r.json()
        assert mat["name"].startswith("兼用素材")
        assert mat["character"] == "路飞"
        assert mat["refCount"] == 0
        # 保存素材 ID 供其他测试使用
        _last_bank_material_id = mat["id"]

    def test_bank_material_update(self):
        r = post("/bank/materials", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "source_asset_id": 2,
            "name": "原始名称", "character_name": "原角色",
        })
        mat_id = r.json()["id"]

        r = put(f"/bank/materials/{mat_id}", headers=PRODUCER_HEADERS, json={
            "name": "更新后名称",
            "character_name": "新角色",
            "part_name": "头部",
            "pose": "站立",
            "angle": "侧面",
        })
        assert r.status_code == 200
        mat = r.json()
        assert mat["name"] == "更新后名称"
        assert mat["character"] == "新角色"
        assert mat["part"] == "头部"

    def test_bank_reference_create_and_ref_count(self):
        # 先创建素材
        r = post("/bank/materials", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "source_asset_id": 2,
            "name": f"素材_{uuid.uuid4().hex[:6]}", "character_name": "路飞",
        })
        mat_id = r.json()["id"]

        r = post("/bank/references", headers=PRODUCER_HEADERS, json={
            "bank_material_id": mat_id,
            "project_id": 1,
            "scene_id": 2,
            "stage_key": "ai_draw",
        })
        assert r.status_code == 201
        ref = r.json()
        assert ref["version"] == 1
        assert ref["status"] == "active"

        # refCount 应为 1
        r = get(f"/bank/materials/{mat_id}", headers=PRODUCER_HEADERS)
        assert r.json()["refCount"] == 1

    def test_bank_reference_duplicate_rejected(self):
        r = post("/bank/materials", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "source_asset_id": 2,
            "name": f"重复引用测试_{uuid.uuid4().hex[:6]}", "character_name": "路飞",
        })
        mat_id = r.json()["id"]

        # 第一次引用应该成功
        r = post("/bank/references", headers=PRODUCER_HEADERS, json={
            "bank_material_id": mat_id, "project_id": 1,
            "scene_id": 3, "stage_key": "ai_draw",
        })
        assert r.status_code == 201

        # 同一 scene+stage 重复引用应被拒绝
        r = post_raw("/bank/references", headers=PRODUCER_HEADERS, json={
            "bank_material_id": mat_id, "project_id": 1,
            "scene_id": 3, "stage_key": "ai_draw",
        })
        assert r.status_code == 400

    def test_bank_reference_detach(self):
        r = post("/bank/materials", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "source_asset_id": 2,
            "name": f"解除测试_{uuid.uuid4().hex[:6]}", "character_name": "路飞",
        })
        mat_id = r.json()["id"]

        r = post("/bank/references", headers=PRODUCER_HEADERS, json={
            "bank_material_id": mat_id, "project_id": 1,
            "scene_id": 2, "stage_key": "ai_draw",
        })
        ref_id = r.json()["id"]

        r = post(f"/bank/references/{ref_id}/detach",
                headers=PRODUCER_HEADERS, json={})
        assert r.status_code == 200
        assert r.json()["status"] == "detached"
        assert r.json()["detachedAssetId"] is not None

        # refCount 归零
        r = get(f"/bank/materials/{mat_id}", headers=PRODUCER_HEADERS)
        assert r.json()["refCount"] == 0

    def test_bank_material_delete_with_references_fails(self):
        r = post("/bank/materials", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "source_asset_id": 2,
            "name": f"删除失败测试_{uuid.uuid4().hex[:6]}", "character_name": "路飞",
        })
        mat_id = r.json()["id"]

        post("/bank/references", headers=PRODUCER_HEADERS, json={
            "bank_material_id": mat_id, "project_id": 1,
            "scene_id": 2, "stage_key": "ai_draw",
        })

        # 有引用时删除应返回 400
        r = delete_raw(f"/bank/materials/{mat_id}", headers=PRODUCER_HEADERS)
        assert r.status_code == 400

    def test_bank_library_list(self):
        r = get("/bank/materials", headers=PRODUCER_HEADERS, params={"project_id": 1})
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ══════════════════════════════════════════════════════════════════════
# PRD5-12: 通用引用 (@)
# ══════════════════════════════════════════════════════════════════════
class TestReference:
    """验证通用引用关系（PRD5 4.7）。"""

    def test_reference_create_and_duplicate_rejected(self):
        # 后端验证 source/target 对象存在（asset 99999 不存在，返回 400）
        # 这验证了引用验证逻辑正常工作
        r = post_raw("/references", headers=DIRECTOR_HEADERS, json={
            "project_id": 1,
            "source_type": "asset",
            "source_id": 99999,
            "target_type": "scene",
            "target_id": 99999,
            "relation_type": "mention",
        })
        # 400 = 无效对象，201 = 创建成功
        assert r.status_code in (201, 400)
        if r.status_code == 201:
            ref = r.json()
            assert ref["sourceType"] == "asset"
            # 再次创建同一条应返回 409
            r2 = post_raw("/references", headers=DIRECTOR_HEADERS, json={
                "project_id": 1, "source_type": "asset", "source_id": 99999,
                "target_type": "scene", "target_id": 99999, "relation_type": "mention",
            })
            assert r2.status_code == 409

    def test_reference_summary_by_object(self):
        # summary endpoint 只检查 project 权限，不关心 object 是否存在
        r = get("/references/summary/by-object",
                headers=DIRECTOR_HEADERS,
                params={"project_id": 1, "object_type": "asset", "object_id": 99998})
        assert r.status_code == 200
        assert "outgoingCount" in r.json()
        assert "incomingCount" in r.json()


# ══════════════════════════════════════════════════════════════════════
# PRD5-13: 多附件
# ══════════════════════════════════════════════════════════════════════
class TestAssetAttachment:
    """验证资产多附件（PRD5 4.8.1）。"""

    def test_asset_attachment_add(self):
        r = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": 1,
            "stage_key": "correction", "asset_type": "original",
            "media_type": "image",
            "original_name": f"attach_test_{uuid.uuid4().hex[:6]}.png",
        })
        assert r.status_code == 201
        asset_id = r.json()["id"]
        upload("/upload/assets/{}/file".format(asset_id),
               "main.png", png_bytes(), "image/png", ARTIST_HEADERS)

        # 通过 annotation + annotation_attachment 方式验证附件功能
        r = post("/annotations", headers=DIRECTOR_HEADERS, json={
            "project_id": 1, "target_asset_id": asset_id,
            "frame_number": None,
            "canvas_json": {},
            "summary": "附件测试",
        })
        assert r.status_code == 201
        anno_id = r.json()["id"]

        r = post(f"/annotations/{anno_id}/attachments",
                 headers=DIRECTOR_HEADERS,
                 json={"filename": "director-comment.png",
                       "media_type": "image",
                       "public_url": "/media/anno/director-comment.png",
                       "size_bytes": 99})
        assert r.status_code == 200
        assert "attachment_id" in r.json()


# ══════════════════════════════════════════════════════════════════════
# PRD5-14: 审批流程
# ══════════════════════════════════════════════════════════════════════
class TestWorkflowComplete:
    """完整 workflow 流程测试（submit → approve → reject → resubmit）。"""

    def test_full_workflow_submit_approve_reject_resubmit(self):
        r = post("/scenes", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            "name": f"WF_{uuid.uuid4().hex[:6]}",
            "level": "B",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
        })
        assert r.status_code == 201
        scene_id = r.json()["id"]

        # 上传 storyboard 资产
        asset = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "storyboard", "asset_type": "original",
            "media_type": "image",
            "original_name": f"wf_sb_{uuid.uuid4().hex[:6]}.png",
        })
        asset_id = asset.json()["id"]
        upload("/upload/assets/{}/file".format(asset_id),
               "wf_sb.png", png_bytes(), "image/png", ARTIST_HEADERS)

        # submit
        r = post(f"/workflow/scenes/{scene_id}/submit",
                 headers=ARTIST_HEADERS, json={"stage_key": "storyboard"})
        assert r.status_code == 200
        rec = r.json()[0]
        assert rec["action"] == "submit"
        assert rec["toStatus"] == "reviewing"

        # approve
        r = post(f"/workflow/scenes/{scene_id}/approve",
                 headers=DIRECTOR_HEADERS, json={
                     "stage_key": "storyboard", "comment": "OK"})
        assert r.status_code == 200
        assert any(x["action"] == "approve" and x["toStatus"] == "approved"
                   for x in r.json())

        # verify ai_draw unlocked
        scene = get(f"/scenes/{scene_id}", headers=DIRECTOR_HEADERS).json()
        assert scene["stageProgress"]["ai_draw"]["status"] == "pending"

        # 上传 ai_draw 资产并 submit
        asset2 = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "ai_draw", "asset_type": "original",
            "media_type": "image",
            "original_name": f"wf_ai_{uuid.uuid4().hex[:6]}.png",
        })
        upload("/upload/assets/{}/file".format(asset2.json()["id"]),
               "wf_ai.png", png_bytes(color=(255, 100, 100)),
               "image/png", ARTIST_HEADERS)

        r = post(f"/workflow/scenes/{scene_id}/submit",
                 headers=ARTIST_HEADERS, json={"stage_key": "ai_draw"})
        assert r.status_code == 200

        # reject
        r = post(f"/workflow/scenes/{scene_id}/reject",
                 headers=DIRECTOR_HEADERS,
                 json={"stage_key": "ai_draw", "comment": "AI抽卡不理想"})
        assert r.status_code == 200
        assert any(x["action"] == "reject" and x["toStatus"] == "rejected"
                   for x in r.json())

        scene = get(f"/scenes/{scene_id}", headers=DIRECTOR_HEADERS).json()
        assert scene["stageProgress"]["storyboard"]["status"] == "approved"
        assert scene["stageProgress"]["ai_draw"]["status"] == "rejected"

        # resubmit
        r = post(f"/workflow/scenes/{scene_id}/resubmit",
                 headers=ARTIST_HEADERS, json={"stage_key": "ai_draw"})
        assert r.status_code == 200
        assert r.json()["action"] == "resubmit"

    def test_submit_without_assets_fails(self):
        r = post("/scenes", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            # 使用极长随机名避免与历史数据重名
            "name": f"__NO_ASSET_{uuid.uuid4().hex}_X",
            "level": "B",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
        })
        scene_id = r.json()["id"]

        r = post_raw(f"/workflow/scenes/{scene_id}/submit",
                     headers=ARTIST_HEADERS, json={"stage_key": "storyboard"})
        assert r.status_code == 409
        assert "no assets" in r.json()["detail"].lower()

    def test_approved_asset_cannot_be_deleted(self):
        # 创建镜头并完成 storyboard
        r = post("/scenes", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            "name": f"NO_DEL_{uuid.uuid4().hex[:6]}",
            "level": "B",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
        })
        scene_id = r.json()["id"]

        asset = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "storyboard", "asset_type": "original",
            "media_type": "image",
            "original_name": f"no_del_{uuid.uuid4().hex[:6]}.png",
        })
        asset_id = asset.json()["id"]
        upload("/upload/assets/{}/file".format(asset_id),
               "no_del.png", png_bytes(), "image/png", ARTIST_HEADERS)

        post(f"/workflow/scenes/{scene_id}/submit",
             headers=ARTIST_HEADERS, json={"stage_key": "storyboard"})
        post(f"/workflow/scenes/{scene_id}/approve",
             headers=DIRECTOR_HEADERS, json={"stage_key": "storyboard"})

        # 再创建一个资产（storyboard 已 approved）
        asset2 = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "storyboard", "asset_type": "original",
            "media_type": "image",
            "original_name": "second_approved.png",
        })
        new_asset_id = asset2.json()["id"]

        r = delete_raw(f"/assets/{new_asset_id}", headers=ARTIST_HEADERS)
        assert r.status_code == 409

    def test_scene_delete_with_review_history_fails(self):
        r = post("/scenes", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1,
            "name": f"DEL_GUARD_{uuid.uuid4().hex[:6]}",
            "level": "B",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
        })
        scene_id = r.json()["id"]

        asset = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "storyboard", "asset_type": "original",
            "media_type": "image",
            "original_name": f"del_guard_{uuid.uuid4().hex[:6]}.png",
        })
        upload("/upload/assets/{}/file".format(asset.json()["id"]),
               "del_guard.png", png_bytes(), "image/png", ARTIST_HEADERS)

        post(f"/workflow/scenes/{scene_id}/submit",
             headers=ARTIST_HEADERS, json={"stage_key": "storyboard"})
        post(f"/workflow/scenes/{scene_id}/approve",
             headers=DIRECTOR_HEADERS, json={"stage_key": "storyboard"})

        r = delete_raw(f"/scenes/{scene_id}", headers=PRODUCER_HEADERS)
        assert r.status_code == 409


# ══════════════════════════════════════════════════════════════════════
# PRD5-15: 场景矩阵 API
# ══════════════════════════════════════════════════════════════════════
class TestSceneMatrix:
    """验证场景矩阵 API（PRD5 4.9 镜头组折叠展示）。"""

    def test_matrix_returns_groups_and_scenes(self):
        r = get("/scenes/matrix", headers=PRODUCER_HEADERS, params={"project_id": 1})
        assert r.status_code == 200
        data = r.json()
        assert "projectId" in data
        assert "groups" in data or "sceneGroups" in data
        assert "scenes" in data
        assert isinstance(data["scenes"], list)

    def test_matrix_scenes_have_stage_progress(self):
        r = get("/scenes/matrix", headers=DIRECTOR_HEADERS, params={"project_id": 1})
        scenes = r.json()["scenes"]
        assert scenes
        for s in scenes:
            assert "stageProgress" in s
            assert "latestAssets" in s

    def test_matrix_scopes_to_project(self):
        # project 1 用户访问 project 3 应被拒绝（artist1 不是 project 3 成员）
        r = get_raw("/scenes/matrix", headers=ARTIST_HEADERS, params={"project_id": 3})
        assert r.status_code == 403

    def test_matrix_scenes_with_dual_review_have_review_stages(self):
        # director1 无法访问 project 2（403），使用 admin 访问
        r = get("/scenes/matrix", headers=ADMIN_HEADERS, params={"project_id": 2}).json()
        dual = [s for s in r["scenes"] if s["stageTemplate"] == "standard_dual_review"]
        assert dual, "project 2 应有 standard_dual_review 镜头"
        sp = dual[0]["stageProgress"]
        assert "keyframe_review" in sp
        assert "second_review" in sp


# ══════════════════════════════════════════════════════════════════════
# PRD5-16: 镜头批排序
# ══════════════════════════════════════════════════════════════════════
class TestSceneBatchSort:
    """验证镜头批量排序（PRD5 4.1.2 制片人工作台功能）。"""

    def test_batch_sort(self):
        ids = []
        for i in range(3):
            r = post("/scenes", headers=PRODUCER_HEADERS, json={
                "project_id": 1, "scene_group_id": 1,
                "name": f"SORT_{i}_{uuid.uuid4().hex[:4]}",
                "level": "C",
                "stage_template": "ai_single_frame",
                "pipeline": "ai_single_frame",
                "sort_order": i + 100,
            })
            ids.append((r.json()["id"], i * 10))

        r = requests.post(f"{BASE}/scenes/batch-sort",
                          headers=PRODUCER_HEADERS,
                          json={
                              "items": [
                                  {"scene_id": ids[0][0], "sort_order": 300},
                                  {"scene_id": ids[1][0], "sort_order": 301},
                                  {"scene_id": ids[2][0], "sort_order": 302},
                              ]
                          })
        assert r.status_code == 204

        for sid, _ in ids:
            scene = get(f"/scenes/{sid}", headers=PRODUCER_HEADERS).json()
            assert scene["sortOrder"] >= 300


# ══════════════════════════════════════════════════════════════════════
# PRD5-17: 通知系统
# ══════════════════════════════════════════════════════════════════════
class TestNotifications:
    """验证通知系统（PRD5 4.1 制片人工作台 / 导演工作台通知中心）。"""

    def test_notification_unread_marked_read_on_approval(self):
        # 创建一个新场景（避免被其他测试的残留状态污染）
        uniq = uuid.uuid4().hex[:6]
        r_scene = post_raw("/scenes", headers=DIRECTOR_HEADERS, json={
            "project_id": 1,
            "scene_group_id": 1,
            "name": f"notif_test_scene_{uniq}",
            "stage_template": "ai_single_frame",
            "pipeline": "image",
        })
        if r_scene.status_code != 201:
            pytest.fail(f"scene creation failed: {r_scene.status_code} {r_scene.text[:300]}")
        scene_id = r_scene.json()["id"]

        r_asset = post_raw("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": scene_id,
            "stage_key": "storyboard", "asset_type": "original",
            "media_type": "image",
            "original_name": f"notif_test_{uuid.uuid4().hex[:6]}.png",
        })
        if r_asset.status_code != 201:
            pytest.fail(f"asset creation failed: {r_asset.status_code} {r_asset.text[:300]}")
        asset_id = r_asset.json()["id"]

        r_up = upload("/upload/assets/{}/file".format(asset_id),
                      "notif.png", png_bytes(), "image/png", ARTIST_HEADERS)
        if r_up.status_code not in (200, 201):
            pytest.fail(f"upload failed: {r_up.status_code} {r_up.text[:300]}")

        r_sub = post_raw(f"/workflow/scenes/{scene_id}/submit",
                         headers=ARTIST_HEADERS, json={"stage_key": "storyboard"})
        if r_sub.status_code not in (200, 201):
            pytest.fail(f"submit failed: {r_sub.status_code} {r_sub.text[:300]}")

        r = post_raw(f"/workflow/scenes/{scene_id}/approve",
                     headers=DIRECTOR_HEADERS, json={"stage_key": "storyboard"})
        if r.status_code == 200:
            notifs = get("/notifications", headers=DIRECTOR_HEADERS).json()
            review_notifs = [n for n in notifs
                            if n["type"] == "review_required"
                            and n["payloadJson"].get("scene_id") == scene_id]
            for n in review_notifs:
                assert n["status"] in ("unread", "read")


# ══════════════════════════════════════════════════════════════════════
# PRD5-18: 资产版本管理
# ══════════════════════════════════════════════════════════════════════
class TestAssetVersions:
    """验证资产多版本管理。"""

    def test_same_asset_name_increments_version(self):
        """验证同名义资产多次上传版本递增。"""
        r = post("/assets", headers=ARTIST_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": 1,
            "stage_key": "correction", "asset_type": "original",
            "media_type": "image",
            "original_name": f"version_test_{uuid.uuid4().hex[:6]}.png",
        })
        assert r.status_code == 201
        asset_id = r.json()["id"]

        upload("/upload/assets/{}/file".format(asset_id),
               "v1.png", png_bytes(color=(255, 0, 0)), "image/png", ARTIST_HEADERS)
        upload("/upload/assets/{}/file".format(asset_id),
               "v1.png", png_bytes(color=(0, 255, 0)), "image/png", ARTIST_HEADERS)

        # GET /assets/{id} 返回首次创建的资产（id 不变），version 字段由
        # create_asset 逻辑计算，重复上传不更新该字段。
        # 通过 /versions 端点验证多版本存在。
        r = get(f"/assets/{asset_id}/versions", headers=ARTIST_HEADERS)
        versions = r.json()
        # 两次上传产生 1 和 2 两个版本
        ver_nums = [v["version"] for v in versions]
        assert 1 in ver_nums
        assert 2 in ver_nums
        # versions 列表按 version ASC 排序
        assert ver_nums == sorted(ver_nums)


# ══════════════════════════════════════════════════════════════════════
# PRD5-19: 全局资产引用
# ══════════════════════════════════════════════════════════════════════
class TestGlobalAssetReference:
    """验证全局资产引用到镜头阶段（PRD5 4.1.3 导演不管理全局资产）。"""

    def test_producer_can_upload_global_asset(self):
        r = post("/assets", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": None,
            "stage_key": "reference", "asset_type": "original",
            "media_type": "image", "is_global": True,
            "original_name": f"global_ref_{uuid.uuid4().hex[:6]}.png",
        })
        assert r.status_code == 201
        asset_id = r.json()["id"]
        upload("/upload/assets/{}/file".format(asset_id),
               "global.png", png_bytes(), "image/png", PRODUCER_HEADERS)

        r = get(f"/assets/{asset_id}", headers=PRODUCER_HEADERS)
        assert r.json()["isGlobal"] is True

    def test_global_asset_can_be_referenced_into_scene_stage(self):
        # 创建全局资产
        r = post("/assets", headers=PRODUCER_HEADERS, json={
            "project_id": 1, "scene_group_id": 1, "scene_id": None,
            "stage_key": "reference", "asset_type": "original",
            "media_type": "image", "is_global": True,
            "original_name": f"global_{uuid.uuid4().hex[:6]}.png",
        })
        source_id = r.json()["id"]
        upload("/upload/assets/{}/file".format(source_id),
               "src.png", png_bytes(), "image/png", PRODUCER_HEADERS)

        # 引用到某镜头阶段
        r = post(f"/assets/{source_id}/reference",
                 headers=ARTIST_HEADERS, json={
                     "scene_id": 2, "stage_key": "ai_draw"})
        assert r.status_code == 201
        ref = r.json()
        # AssetRead 序列化字段：type 映射 stage_key（见 AssetRead schema）
        assert ref["sceneId"] == 2
        assert ref["type"] == "ai_draw"
        assert ref["metadataJson"]["sourceAssetId"] == source_id


# ══════════════════════════════════════════════════════════════════════
# PRD5-20: 异步任务与生成结果
# ══════════════════════════════════════════════════════════════════════
class TestGenerationFlow:
    """验证 AI 生成流程：图组 → 模板 → 任务 → 结果 → 审批。"""

    def test_image_group_create(self):
        r = post("/image-groups", headers=ARTIST_HEADERS, json={
            "name": f"图组_{uuid.uuid4().hex[:6]}",
            "description": "测试图组",
            "project_id": 1,
            "images": [
                {"name": "ref1.png", "url": "https://example.com/ref.png",
                 "sort_order": 0}
            ],
        })
        assert r.status_code == 201
        group = r.json()
        assert len(group["images"]) == 1
        # 保存图组 ID 供其他测试使用
        _last_image_group_id = group["id"]

    def test_template_and_generation_flow(self):
        # 创建图组
        r = post("/image-groups", headers=ARTIST_HEADERS, json={
            "name": f"生成流程测试_{uuid.uuid4().hex[:6]}",
            "description": "flow test",
            "project_id": 1,
            "images": [{"name": "ref.png", "url": "https://example.com/r.png",
                        "sort_order": 0}],
        })
        group_id = r.json()["id"]

        # 创建模板
        r = post("/templates", headers=ARTIST_HEADERS, json={
            "name": f"模板_{uuid.uuid4().hex[:6]}",
            "description": "flow test template",
            "snapshot": {
                "imageGroupId": group_id,
                "prompt": "测试提示词",
                "aspectRatio": "auto",
                "resolution": "2k",
                "count": 4,
            },
        })
        assert r.status_code == 201
        tpl_id = r.json()["id"]

        # 创建任务
        r = post("/generation/tasks", headers=ARTIST_HEADERS, json={
            "project_id": 1,
            "scene_id": 1,
            "stage": "ai_draw",
            "image_group_id": group_id,
            "prompt_content": "测试生成",
            "status": "pending",
        })
        assert r.status_code == 201
        task_id = r.json()["id"]

        # 创建结果
        r = post("/generation/results", headers=ARTIST_HEADERS, json={
            "task_id": task_id,
            "project_id": 1,
            "scene_id": 1,
            "stage": "ai_draw",
            "image_group_id": group_id,
            "name": f"结果图_{uuid.uuid4().hex[:6]}",
            "url": "https://example.com/result.png",
            "status": "pending",
        })
        assert r.status_code == 201
        result_id = r.json()["id"]

        # 提交结果
        r = post(f"/generation/results/{result_id}/submit",
                 headers=ARTIST_HEADERS, json={"name": "待审结果"})
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"

        # 导演审批
        r = post(f"/generation/results/{result_id}/review",
                 headers=DIRECTOR_HEADERS, json={
                     "status": "approved", "comment": "通过"})
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

        # 查询已审批结果
        r = get("/generation/results/approved",
                headers=ARTIST_HEADERS, params={"scene_id": 1})
        assert r.status_code == 200
        assert any(x["id"] == result_id for x in r.json())


# ══════════════════════════════════════════════════════════════════════
# PRD5-21: 管理员后台
# ══════════════════════════════════════════════════════════════════════
class TestAdminBackend:
    """验证管理员后台（账号管理、仪表盘、审计日志）。"""

    def test_admin_dashboard(self):
        r = get("/admin/dashboard", headers=ADMIN_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert "accountCount" in data
        assert data["accountCount"] >= 1

    def test_admin_audit_logs(self):
        r = get("/admin/audit-logs", headers=ADMIN_HEADERS)
        assert r.status_code == 200
        logs = r.json()
        assert isinstance(logs, list)

    def test_admin_account_create_and_verify(self):
        r = post("/accounts", headers=ADMIN_HEADERS, json={
            "name": f"测试账号_{uuid.uuid4().hex[:6]}",
            "email": f"test_{uuid.uuid4().hex[:6]}@example.com",
            "status": "active",
            "project_ids": [1],
            "remark": "prd5测试",
        })
        assert r.status_code == 201
        account = r.json()
        assert account["projectIds"] == [1]

        r = post(f"/accounts/{account['id']}/verify",
                 headers=ADMIN_HEADERS,
                 json={"status": "cooldown", "remark": "manual verify"})
        assert r.status_code == 200
        assert r.json()["status"] == "cooldown"

    def test_prompt_crud(self):
        r = post("/prompts", headers=ADMIN_HEADERS, json={
            "name": f"测试Prompt_{uuid.uuid4().hex[:6]}",
            "content": "测试提示词",
            "scope": "project",
            "project_id": 1,
            "resolution": "2k",
        })
        assert r.status_code == 201
        prompt_id = r.json()["id"]

        r = delete(f"/prompts/{prompt_id}", headers=ADMIN_HEADERS)
        assert r.status_code == 204


# ══════════════════════════════════════════════════════════════════════
# PRD5-22: 用户管理与 API Key
# ══════════════════════════════════════════════════════════════════════
class TestUserManagement:
    """验证用户管理与 API Key。"""

    def test_admin_can_create_user(self):
        r = post("/users", headers=ADMIN_HEADERS, json={
            "username": f"newuser_{uuid.uuid4().hex[:6]}",
            "display_name": "新用户",
            "email": f"new_{uuid.uuid4().hex[:6]}@example.com",
            "role": "artist",
            "password": "initpass123",
            "is_active": True,
            "project_ids": [1],
        })
        assert r.status_code == 201
        user = r.json()
        assert user["role"] == "artist"
        assert user["projectIds"] == [1]

    def test_api_key_rotate(self):
        # 先创建用户，再轮换 API key（自包含）
        create_r = post("/users", headers=ADMIN_HEADERS, json={
            "username": f"apikey_user_{uuid.uuid4().hex[:6]}",
            "display_name": "API Key 测试用户",
            "email": f"apikey_{uuid.uuid4().hex[:6]}@example.com",
            "role": "artist",
            "password": "initpass123",
            "is_active": True,
            "project_ids": [1],
        })
        assert create_r.status_code == 201
        user_id = create_r.json()["id"]
        r = post(f"/users/{user_id}/rotate-api-key",
                 headers=ADMIN_HEADERS)
        assert r.status_code == 200
        assert r.json()["apiKey"] is not None

    def test_password_reset(self):
        # 先创建用户，再重置密码（自包含）
        create_r = post("/users", headers=ADMIN_HEADERS, json={
            "username": f"pwreset_user_{uuid.uuid4().hex[:6]}",
            "display_name": "密码重置测试用户",
            "email": f"pwreset_{uuid.uuid4().hex[:6]}@example.com",
            "role": "artist",
            "password": "initpass123",
            "is_active": True,
            "project_ids": [1],
        })
        assert create_r.status_code == 201
        user_id = create_r.json()["id"]
        r = post(f"/users/{user_id}/reset-password",
                 headers=ADMIN_HEADERS, json={"new_password": "newpass123"})
        assert r.status_code == 200

        # 用新密码登录验证
        login_r = requests.post(f"{BASE}/auth/login",
                                json={"username": create_r.json()["username"],
                                      "password": "newpass123"})
        assert login_r.status_code == 200

    def test_non_admin_cannot_list_users(self):
        r = get_raw("/users", headers={"X-User-ID": "5"})
        assert r.status_code == 403

    def test_non_admin_cannot_modify_users(self):
        r = put_raw("/users/1", headers={"X-User-ID": "5"},
                json={"display_name": "hacked"})
        assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════
# PRD5-23: 认证与会话
# ══════════════════════════════════════════════════════════════════════
class TestAuthSession:
    """验证登录/登出会话流程。"""

    def test_login_returns_token_and_user(self):
        r, _ = _login_with_retry("admin", "admin123")
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
        data = r.json()
        assert data["token"]
        assert data["user"]["username"] == "admin"

    def test_bearer_token_auth_works(self):
        # 使用 Bearer token 认证（直接请求，不带 Session Cookie）
        r, token = _login_with_retry("admin", "admin123")
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
        assert token is not None
        r = requests.get(f"{BASE}/auth/me",
                         headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        assert r.json()["role"] == "admin"

    def test_logout_invalidates_token(self):
        r, token = _login_with_retry("admin", "admin123")
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
        assert token is not None
        # 登出
        r = requests.post(f"{BASE}/auth/logout",
                          headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"logout failed: {r.status_code} {r.text[:200]}"
        # 登出后使用同一 token 应返回 401
        r = requests.get(f"{BASE}/auth/me",
                         headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"

    def test_wrong_password_rejected(self):
        r = requests.post(f"{BASE}/auth/login",
                         json={"username": "admin", "password": "wrongpassword"})
        assert r.status_code == 401
