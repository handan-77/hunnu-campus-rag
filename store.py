# -*- coding: utf-8 -*-
"""
用户数据持久化层（优化6/7/8）
- 聊天会话永久保存到本地 JSON，除非用户手动清空
- 个人资料（昵称/学号/头像）与服务办理记录同一文件管理
- 按 user_id 分文件存储，为后续真实登录系统预留（当前固定 default 用户）
"""
import json
import os
import time
import uuid

ROOT = os.path.dirname(os.path.abspath(__file__))
CHAT_DIR = os.path.join(ROOT, "data", "chat_store")
os.makedirs(CHAT_DIR, exist_ok=True)

DEFAULT_PROFILE = {"nickname": "张同学", "sid": "2023010301", "role": "本科生", "avatar": ""}


def new_session():
    return {"id": uuid.uuid4().hex[:8],
            "title": "新对话",
            "created": time.strftime("%Y-%m-%d %H:%M"),
            "day": time.strftime("%Y-%m-%d"),
            "messages": [],
            "hits": []}


def _path(user_id):
    return os.path.join(CHAT_DIR, f"{user_id}.json")


def load(user_id: str = "default") -> dict:
    p = _path(user_id)
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("sessions"):
                data.setdefault("profile", dict(DEFAULT_PROFILE))
                data.setdefault("records", {})
                data.setdefault("favorites", [])
                data.setdefault("pinned", [])   # 置顶会话 id 列表
                return data
        except Exception:
            pass
    return {"profile": dict(DEFAULT_PROFILE), "records": {}, "favorites": [],
            "pinned": [], "sessions": [new_session()]}


def save(user_id: str, data: dict):
    try:
        with open(_path(user_id), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def get_session(store: dict, sid: str):
    return next((s for s in store["sessions"] if s["id"] == sid), None)
