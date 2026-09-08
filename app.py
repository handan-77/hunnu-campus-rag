# -*- coding: utf-8 -*-
"""
湖南师范大学 · 校园智能助手（最终优化版）
- 顶部红色通栏：校徽 + 书法字体校名（无 AI 生成标识）
- 全屏通栏白色页面，无左右/底部留白
- 对话页：左侧=知识库总览/检索资料（含官网原文溯源链接）+ 聊天会话列表；
  右侧=对话区 + AI 深度思考过程折叠模块
- 聊天记录持久化（data/chat_store/{user_id}.json），多用户登录预留
- 业务约束：agent.invoke 与原版逐字一致（RAG + 多轮记忆 + 思考步骤），
  检索数据来自原有 retriever.search_test()（仅新增 source_url 字段透传）
"""
import base64
import os
import re
import sys
import html as _h
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, unquote_plus

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(ROOT)
os.chdir(ROOT)  # 保证 retriever.py 中的相对路径（./models、./db）在任何启动目录下有效

import streamlit as st
import streamlit.components.v1 as components

from agent_graph import agent
import services
import store

# ========== 页面配置（校徽仅读取本地文件，禁止AI生成） ==========
_BADGE_CANDIDATES = ["new_badge_clean.png", "hunnu_logo.png", "logo(1).jpg", "logo.jpg", "hnu_emblem.png"]
_BADGE = next((os.path.join(ROOT, n) for n in _BADGE_CANDIDATES if os.path.exists(os.path.join(ROOT, n))), None)
st.set_page_config(
    page_title="校园智能助手 · 湖南师范大学",
    page_icon=_BADGE or "🎓",
    layout="wide",
)


def _b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


_BADGE_B64 = _b64(_BADGE) if _BADGE else ""
_BADGE_MIME = "image/png" if (_BADGE and _BADGE.endswith(".png")) else "image/jpeg"

# 北京时间（UTC+8）——云端服务器时区独立于用户，所有时间统一显示北京时间
_CST = timezone(timedelta(hours=8))
def _now(fmt="%Y-%m-%d %H:%M"):
    return datetime.now(_CST).strftime(fmt)

# ========== 读取 URL 参数（交互路由） ==========
qp = st.query_params

# ========== 自动生成访客会话 ID（首次访问无感知分配，跨导航/刷新通过 URL 保持） ==========
import uuid as _uuid
ss = st.session_state
ss.setdefault("user_id", None)
_url_uid = qp.get("uid")
if ss["user_id"] is None:
    if _url_uid:
        # URL 带 uid → 恢复已有会话
        ss["user_id"] = _url_uid
    else:
        # 首次访问 → 自动生成匿名 UUID（12 位十六进制，短且足够唯一）
        ss["user_id"] = _uuid.uuid4().hex[:12]
# 把 user_id 同步到 URL（跨导航保留会话）
if qp.get("uid") != ss["user_id"]:
    try:
        qp["uid"] = ss["user_id"]
    except Exception:
        pass

# ========== 会话状态 / 持久化存储（user_id 隔离） ==========
if "store" not in ss:
    ss["store"] = store.load(ss["user_id"])
ss.setdefault("cur_sid", ss["store"]["sessions"][-1]["id"])
ss.setdefault("deep_think", False)             # 深度思考：扩大检索范围(5→8)
ss.setdefault("chat_error", None)
ss.setdefault("last_ask", None)
ss.setdefault("last_nts", None)
ss.setdefault("_logout_toast", False)
ss.setdefault("_logout_key", 0)                 # 登出按钮触发计数器

VIEWS = ["首页", "AI对话", "校园服务", "个人中心"]


def _cur():
    """当前会话（不存在则新建，保证鲁棒）"""
    s = store.get_session(ss["store"], ss["cur_sid"])
    if s is None:
        s = store.new_session()
        ss["store"]["sessions"].append(s)
        ss["cur_sid"] = s["id"]
    return s


view = unquote_plus(qp.get("view", "首页"))
if view not in VIEWS:
    view = "首页"

# —— 操作类参数：读、处理、主动清理（避免 Streamlit rerun 时重复触发或 URL 残留） ——
_OP_PARAMS = ["pin", "del", "ren", "nts", "clear", "ask", "rtitle", "rsid", "ts", "deep", "sid"]

def _clean_op_params():
    """处理完操作类参数后主动从 URL 里删掉它们"""
    try:
        for p in _OP_PARAMS:
            if p in qp:
                del qp[p]
    except Exception:
        pass

# deep 开关
if qp.get("deep") in ("0", "1"):
    ss["deep_think"] = qp.get("deep") == "1"

# 切换会话
sid = qp.get("sid")
if sid and sid != ss["cur_sid"] and store.get_session(ss["store"], sid):
    ss["cur_sid"] = sid

# 新建对话
nts = qp.get("nts")
if nts and nts != ss.get("last_nts"):
    ss["last_nts"] = nts
    s = store.new_session()
    ss["store"]["sessions"].append(s)
    ss["cur_sid"] = s["id"]
    store.save(ss["user_id"], ss["store"])

# 清空当前会话
if qp.get("clear") == "1":
    _cur()["messages"] = []
    _cur()["hits"] = []
    ss["last_hits"] = []
    store.save(ss["user_id"], ss["store"])

# 服务页自动展开表单
svc = qp.get("svc")
if svc:
    ss.setdefault("svc_open", set()).add(svc)

if qp.get("logout") == "1" and not ss["_logout_toast"]:
    st.toast("已退出登录（演示环境）")
    ss["_logout_toast"] = True

# 会话管理：置顶
pin = qp.get("pin")
if pin and pin != ss.get("last_pin"):
    ss["last_pin"] = pin
    pid = pin.split(".")[0]
    pinned = ss["store"].setdefault("pinned", [])
    if pid in pinned:
        pinned.remove(pid)
    else:
        pinned.append(pid)
    store.save(ss["user_id"], ss["store"])

# 删除会话
_del = qp.get("del")
if _del and store.get_session(ss["store"], _del):
    ss["store"]["sessions"] = [x for x in ss["store"]["sessions"] if x["id"] != _del]
    if _del in ss["store"].get("pinned", []):
        ss["store"]["pinned"].remove(_del)
    if ss["cur_sid"] == _del:
        _ns = store.new_session()
        ss["store"]["sessions"].append(_ns)
        ss["cur_sid"] = _ns["id"]
    store.save(ss["user_id"], ss["store"])

# 重命名提交
_rtitle = qp.get("rtitle")
_rsid = qp.get("rsid")
if _rtitle and _rsid:
    _s = store.get_session(ss["store"], _rsid)
    if _s:
        _s["title"] = _rtitle.strip()[:30] or _s["title"]
        store.save(ss["user_id"], ss["store"])

# 进入重命名状态
_ren = qp.get("ren")
ss["ren_sid"] = _ren if (_ren and store.get_session(ss["store"], _ren)) else None


def url(v, **params):
    """构造交互链接——自动带上 uid 保持会话身份"""
    q = {"view": v}
    # 自动附加 uid，保证所有导航/操作都在同一用户会话内
    if ss.get("user_id"):
        q["uid"] = ss["user_id"]
    q.update(params)
    return "/?" + "&".join(f"{k}={quote(str(val))}" for k, val in q.items() if val is not None)


# ========== 全局样式（全屏通栏 · 师大红官方风格） ==========
st.markdown("""
<style>
    @import url('https://fonts.loli.net/css2?family=Zhi+Mang+Xing&family=Ma+Shan+Zheng&display=swap');

    #MainMenu {visibility: hidden;}
    [data-testid="stHeader"], header[data-testid="stHeader"] {display: none !important;}
    footer[data-testid="stFooter"] {display: none;}
    [data-testid="stToolbar"], [data-testid*="Toolbar"], [data-testid*="toolbar"],
    [data-testid="stDecoration"], [data-testid="stStatusContainer"],
    [data-testid="stAppToolbar"], [data-testid="stHeaderBar"],
    [data-testid="stSidebarCollapsedControl"] {display: none !important;}

    html, body, .stApp {overflow-x: hidden;}
    .stApp {background: #FFFFFF;
        font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;}
    .block-container {max-width: none !important; padding: 64px 0 0;}

    a {text-decoration: none !important;}
    .m-header a, .m-title, .hdr-sub, .hdr-center {white-space: nowrap;}

    /* ===== 顶部红色通栏（校徽放大 + 书法校名，无AI标识） ===== */
    .m-header {position: fixed; top: 0; left: 0; right: 0; height: 64px; z-index: 1001;
        background: #C8102E; box-shadow: 0 2px 8px rgba(158,13,38,.28);
        display: flex; align-items: center; justify-content: space-between; padding: 0 26px;}
    .hdr-left {display: flex; align-items: center;}
    .m-badge {height: 44px; display: flex; align-items: center; margin-right: 14px;}
    .m-badge img {height: 44px; width: auto; object-fit: contain;}
    .m-title {font-family: 'Zhi Mang Xing', 'Ma Shan Zheng', 'STXingkai', '华文行楷', 'KaiTi', '楷体', serif;
        font-size: 29px; font-weight: 400; color: #fff; letter-spacing: 4px;}
    .hdr-sub {color: rgba(255,255,255,.78); font-size: 12px; margin-left: 10px; letter-spacing: 1px;}
    .hdr-center {position: absolute; left: 50%; transform: translateX(-50%);
        font-family: 'Zhi Mang Xing', 'Ma Shan Zheng', 'STXingkai', '华文行楷', 'KaiTi', '楷体', serif;
        color: #fff; font-size: 24px; letter-spacing: 4px;}
    .hdr-right {display: flex; align-items: center;}
    .hdr-right a {color: rgba(255,255,255,.88); font-size: 14px; padding: 6px 14px;}
    .hdr-right a:hover {color: #fff;}
    .hdr-right a + a {border-left: 1px solid rgba(255,255,255,.38);}
    .hdr-right a.on {color: #fff; font-weight: 700;}

    /* ===== 白色卡片 ===== */
    .m-card {background: #FFFFFF; border: 1px solid #E4E7EC; border-radius: 12px;
        box-shadow: 0 1px 4px rgba(16,24,40,.05);}

    /* ===== 首页（全屏通栏） ===== */
    .fill-page {min-height: calc(100vh - 64px); display: flex; flex-direction: column;}
    /* 含轮播的首页为长页面：hero 自然高度，轮播紧随其后 */
    .fill-page.home-ext {min-height: 0;}
    .home-hero {flex: 1.05; max-width: 1150px; margin: 0 auto; width: 100%;
        padding: 46px 34px 10px; display: flex; gap: 56px; align-items: flex-start;}
    .home-ext .home-hero {flex: none; padding-bottom: 26px;}
    .home-l {flex: 1.05;}
    .home-r {flex: 1;}
    .home-title {font-size: 26px; font-weight: 700; color: #141414; margin-bottom: 8px;}
    .home-sub {font-size: 13.5px; color: #616161; margin-bottom: 8px;}
    .ex-row {display: flex; align-items: center; gap: 10px; padding: 14px 4px;
        border-bottom: 1px dashed #E4E7EC; font-size: 14px; color: #141414 !important;
        cursor: pointer;}
    .ex-row:hover {color: #C8102E !important;}
    .ex-ico {width: 20px; height: 20px; border-radius: 50%; border: 1px solid #E7B8BE;
        background: #FBEEEF; color: #C8102E; font-size: 10px; flex-shrink: 0;
        display: flex; align-items: center; justify-content: center;}
    .cta {display: flex; align-items: center; justify-content: center; gap: 8px;
        width: 100%; height: 52px; background: #C8102E; color: #fff !important;
        border-radius: 10px; font-size: 15.5px; font-weight: 600; letter-spacing: 2px;}
    .cta:hover {background: #A80D27;}
    .tile-grid {display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 16px;}
    .tile {border: 1px solid #E4E7EC; border-radius: 10px; padding: 18px 8px 15px;
        text-align: center; color: #141414 !important; background: #fff;}
    .tile:hover {border-color: #C8102E;}
    .tile svg {display: block; margin: 0 auto;}
    .tile .name {font-size: 13.5px; margin-top: 9px; color: #141414;}

    /* ===== 对话页（左右独立滚动，互不影响） ===== */
    .chat-wrap {display: flex; gap: 18px; align-items: stretch;
        max-width: 1320px; margin: 0 auto; width: 100%;
        padding: 20px 26px 34px; height: calc(100vh - 64px); box-sizing: border-box;
        overflow: hidden;}
    /* 左栏：sticky 独立滚动（聊天记录+检索资料一起滚） */
    .panel-col {flex: 28; min-width: 270px; display: flex; flex-direction: column; gap: 16px;
        position: sticky; top: 12px; height: calc(100vh - 88px); overflow-y: auto;
        scrollbar-width: thin; scrollbar-color: #d0d5dd transparent;}
    .panel-col::-webkit-scrollbar {width: 6px;}
    .panel-col::-webkit-scrollbar-thumb {background: #d0d5dd; border-radius: 3px;}
    /* 右栏：独立滚动 */
    .chat-card {flex: 72; padding: 18px 20px 14px; display: flex; flex-direction: column;
        height: calc(100vh - 88px); overflow: hidden;}
    .chat-card .chat-body {flex: 1; overflow-y: auto; scrollbar-width: thin;
        scrollbar-color: #d0d5dd transparent;}
    .chat-card .chat-body::-webkit-scrollbar {width: 6px;}
    .chat-card .chat-body::-webkit-scrollbar-thumb {background: #d0d5dd; border-radius: 3px;}
    .panel-card {flex: 1;}
    details.panel-fold {padding: 0;}
    details.panel-fold > summary {list-style: none; cursor: pointer; padding: 14px 16px;}
    details.panel-fold > summary::-webkit-details-marker {display: none;}
    details.panel-fold > summary:hover .panel-title {color: #C8102E;}
    details.panel-fold[open] > summary {border-bottom: 1px solid #EEF0F3;}
    details.panel-fold .panel-body {padding: 2px 16px 10px;}
    .fold-arrow {margin-left: 8px; color: #9aa1ab; font-size: 12px; transition: transform .15s;
        flex-shrink: 0;}
    details.panel-fold[open] .fold-arrow {transform: rotate(180deg);}
    .panel-head {display: flex; align-items: center; justify-content: space-between;}
    .panel-title {font-size: 15.5px; font-weight: 700; color: #141414;}
    .panel-pill {background: #C8102E; color: #fff; font-size: 11.5px; padding: 3px 10px;
        border-radius: 20px; white-space: nowrap;}
    .panel-note {font-size: 11.5px; color: #9aa1ab; margin: 12px 0 2px; line-height: 1.7;}
    .panel-sub {font-size: 11px; color: #9aa1ab; margin: 14px 0 6px;}
    .kb-num {font-size: 36px; font-weight: 700; color: #C8102E; margin-top: 8px; line-height: 1.2;}
    .kb-cap {font-size: 12.5px; color: #616161; margin-bottom: 4px;}
    .stat-row {display: flex; gap: 10px; margin-bottom: 6px;}
    .stat-cell {flex: 1; text-align: center;}
    .stat-cell .pc {color: #C8102E; font-weight: 700; font-size: 15px;}
    .stat-cell .track {height: 5px; background: #EFF1F4; border-radius: 3px;
        overflow: hidden; margin: 5px 2px;}
    .stat-cell .fill {height: 100%; background: #C8102E; border-radius: 3px;}
    .stat-cell .lb {font-size: 10.5px; color: #9aa1ab; margin-top: 3px;}
    .src-item {border-top: 1px solid #EEF0F3; padding: 10px 2px;}
    .src-line1 {display: flex; align-items: baseline;}
    .src-item .tag {color: #C8102E; font-weight: 700; font-size: 12.5px; flex-shrink: 0;}
    .src-line1 .tt {flex: 1; font-size: 13px; color: #141414; line-height: 1.5;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
    .src-item .score {color: #C8102E; font-weight: 700; margin-left: 8px; font-size: 11.5px;
        white-space: nowrap;}
    .src-item .meta {font-size: 11px; color: #9aa1ab; margin-top: 3px;}
    .src-link {display: inline-block; margin-top: 5px; font-size: 11.5px;
        color: #C8102E !important; font-weight: 600;}
    .src-link:hover {text-decoration: underline;}
    .src-local {display: inline-block; margin-top: 5px; font-size: 11.5px; color: #9aa1ab;}
    .src-item details {margin-top: 5px;}
    .src-item summary {font-size: 11.5px; color: #C8102E; cursor: pointer; list-style: none;}
    .src-item summary:hover {text-decoration: underline;}
    .src-item details div {font-size: 12px; color: #616161; line-height: 1.7;
        background: #F7F8FA; border-radius: 8px; padding: 8px 10px; margin-top: 6px;}

    /* 会话列表 */
    .sess-card {padding: 14px 14px 8px;}
    .sess-day {font-size: 11px; color: #9aa1ab; margin: 8px 2px 4px;}
    .sess-row {display: flex; justify-content: space-between; align-items: center; gap: 8px;
        padding: 9px 10px; border-radius: 8px; font-size: 13px; color: #141414 !important;}
    .sess-row:hover {background: #F7F8FA;}
    .sess-row.on {background: #FBEEEF; color: #C8102E !important; font-weight: 600;}
    .sess-link {display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0;
        color: inherit !important; text-decoration: none;}
    .sess-link .t {flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
    .sess-link .d {font-size: 10.5px; color: #9aa1ab; flex-shrink: 0;}
    .sess-row.on .d {color: #C8102E;}
    .pin-mark {flex-shrink: 0; font-size: 11px;}
    .sess-act {display: flex; gap: 2px; flex-shrink: 0;}
    .sess-act a {font-size: 11px; padding: 2px 3px; filter: grayscale(1); opacity: .45;
        text-decoration: none !important;}
    .sess-act a:hover {filter: none; opacity: 1;}
    /* 会话重命名（内联表单） */
    .ren-form {display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0;}
    .ren-box {flex: 1; min-width: 0; height: 28px; border: 1px solid #C8102E; border-radius: 6px;
        padding: 0 8px; font-size: 12.5px; box-sizing: border-box; background: #fff;}
    .ren-save {height: 28px; padding: 0 10px; background: #C8102E; color: #fff; border: none;
        border-radius: 6px; font-size: 12px; cursor: pointer; flex-shrink: 0;}
    .ren-cancel {font-size: 12px; color: #9aa1ab !important; flex-shrink: 0;
        text-decoration: none !important;}
    .new-chat {font-size: 12.5px; color: #C8102E !important; font-weight: 600; flex-shrink: 0;}
    .new-chat:hover {text-decoration: underline;}
    button.new-chat {background: none; border: none; cursor: pointer; font: inherit; padding: 0;}
    .hdr-acts {display: flex; align-items: center; gap: 12px; flex-shrink: 0;}

    /* 对话区 */
    .asst-name {font-size: 11.5px; color: #9aa1ab; margin: 0 0 6px 4px;}
    .chat-body {flex: 1;}
    .msg {display: flex; margin-bottom: 12px;}
    .msg.user {justify-content: flex-end;}
    .bubble {max-width: 78%; padding: 11px 15px; border-radius: 12px;
        font-size: 14px; line-height: 1.75; color: #141414; border: 1px solid #EEF0F3;
        background: #F7F8FA; word-break: break-word;}
    .msg.user .bubble {background: #F8E8E8; border-color: #F0D5D8;}
    .think {margin-bottom: 8px;}
    .think summary {font-size: 12px; color: #C8102E; cursor: pointer; list-style: none;}
    .think summary::-webkit-details-marker {display: none;}
    .think summary:hover {text-decoration: underline;}
    .think div {font-size: 12px; color: #616161; background: #fff; border: 1px solid #F0F2F5;
        border-radius: 8px; padding: 8px 10px; margin-top: 6px; line-height: 1.8;}
    .err {background: #FDECEC; border: 1px solid #F5C2C7; color: #B02A37;
        border-radius: 10px; padding: 10px 14px; font-size: 13px; margin-bottom: 12px;}

    .chip-row {display: flex; gap: 10px; margin: 14px 0 2px; border-top: 1px solid #EEF0F3;
        padding-top: 14px; flex-wrap: wrap;}
    .chip {border: 1px solid #D8DEE7; background: #fff; color: #141414 !important;
        border-radius: 18px; padding: 7px 16px; font-size: 12.5px;}
    .chip:hover {border-color: #C8102E; color: #C8102E !important;}

    /* 输入行（纯 HTML：输入框内嵌麦克风 + 红色发送按钮） */
    .in-row {display: flex; gap: 10px; margin-top: 14px;}
    .in-row form {flex: 1; position: relative; margin: 0;}
    .in-row input {width: 100%; height: 44px; box-sizing: border-box; background: #fff;
        border: 1px solid #D8DEE7; border-radius: 12px; padding: 0 44px 0 16px;
        font-size: 14px; color: #141414; outline: none;}
    .in-row input::placeholder {color: #9aa1ab;}
    .in-row input:focus {border-color: #C8102E; box-shadow: 0 0 0 1px #C8102E;}
    .in-row .mic {position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
        width: 34px; height: 34px; border: none; background: transparent; color: #9aa1ab;
        cursor: pointer; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;}
    .in-row .mic:hover {color: #C8102E; background: #F5F7FA;}
    .in-row .mic.rec {color: #C8102E; animation: micpulse 1s infinite;}
    @keyframes micpulse {50% {opacity: .35;}}
    .send-btn {height: 44px; background: #C8102E; color: #fff; border: none;
        border-radius: 10px; padding: 0 20px; font-size: 14px; letter-spacing: 2px;
        cursor: pointer; display: flex; align-items: center; gap: 6px; flex-shrink: 0;}
    .send-btn:hover {background: #A80D27;}
    .deep-link {display: inline-block; margin-top: 12px; font-size: 12.5px;
        color: #9aa1ab !important; cursor: pointer;}
    .deep-link.on {color: #C8102E !important; font-weight: 600;}
    .deep-link:hover {color: #C8102E !important;}

    /* ===== 校园服务 ===== */
    .svc-title {font-size: 20px; font-weight: 700; color: #141414; margin: 10px 0 4px;}
    .svc-cap {font-size: 12.5px; color: #616161; margin-bottom: 6px;}
    .svc-group {font-size: 14px; color: #616161; font-weight: 600; margin: 18px 0 8px;}
    [data-testid="stExpander"] {background: #FFFFFF; border: 1px solid #E4E7EC;
        border-radius: 10px; padding: 2px 14px; margin-bottom: 8px;
        box-shadow: 0 1px 3px rgba(16,24,40,.04);}
    [data-testid="stTextInput"] > div, [data-testid="stTextArea"] > div,
    [data-testid="stDateInput"] > div, [data-testid="stSelectbox"] > div {border-radius: 10px;}
    button[kind="primary"] {background: #C8102E; border-color: #C8102E; color: #fff;
        border-radius: 10px; font-weight: 500;}
    button[kind="primary"]:hover {background: #A80D27; border-color: #A80D27; color: #fff;}
    .mock-card {border: 1px solid #E4E7EC; border-radius: 12px; padding: 16px 18px;
        margin: 14px 0; box-shadow: 0 1px 4px rgba(16,24,40,.05); background: #fff;}
    .mock-title {font-size: 15px; font-weight: 700; color: #141414; margin-bottom: 10px;}
    .svc-ask {display: inline-block; margin: 10px 0 14px; font-size: 12.5px;
        color: #C8102E !important; font-weight: 600; text-decoration: none !important;
        border: 1px solid #C8102E; border-radius: 20px; padding: 6px 16px;}
    .svc-ask:hover {background: #C8102E; color: #fff !important;}
    .mock-table {width: 100%; border-collapse: collapse; font-size: 12.5px;}
    .mock-table th {background: #FBEEEF; color: #C8102E; font-weight: 600; text-align: left;
        padding: 8px 10px; border-bottom: 1px solid #F0D5D8;}
    .mock-table td {padding: 8px 10px; border-bottom: 1px solid #F0F2F5; color: #141414;}
    .mock-kv {font-size: 13px; color: #141414; margin: 4px 0;}
    .mock-kv b {color: #C8102E;}

    /* ===== 个人中心 ===== */
    .pf-wrap {max-width: 680px; margin: 30px auto 0; padding: 0 26px;}
    .pf-card {display: flex; align-items: center; gap: 16px; padding: 24px 28px; margin-bottom: 16px;}
    .pf-card img.av {width: 60px; height: 60px; border-radius: 50%; object-fit: cover;}
    .pf-name {font-size: 16.5px; font-weight: 700; color: #141414;}
    .pf-meta {font-size: 12.5px; color: #616161; margin-top: 4px;}
    .pf-badge {background: #fff; border: 1px solid #E4E7EC; color: #141414;
        border-radius: 8px; padding: 5px 18px; font-size: 13px;}
    .pf-list {padding: 4px 6px;}
    .pf-row {border-bottom: 1px solid #F0F2F5;}
    .pf-row:last-child {border-bottom: none;}
    .pf-row summary {list-style: none; cursor: pointer; display: flex;
        align-items: center; justify-content: space-between;
        padding: 15px 12px; font-size: 14px; color: #141414;}
    .pf-row summary::-webkit-details-marker {display: none;}
    .pf-row summary:hover {color: #C8102E;}
    .pf-row summary::after {content: "›"; color: #B8BFC9; font-size: 18px;}
    .pf-row[open] summary::after {transform: rotate(90deg);}
    .pf-row .body {padding: 2px 12px 14px; font-size: 13px; color: #616161; line-height: 1.9;}
    .pf-logout {display: block; text-align: center; padding: 14px; font-size: 14px;
        color: #141414 !important; cursor: pointer;}
    .pf-logout:hover {color: #C8102E !important;}

    .m-footer {text-align: center; color: #9aa1ab; font-size: 12.5px;
        letter-spacing: .5px; padding: 20px 0 16px; margin-top: auto;}
</style>
""", unsafe_allow_html=True)


# ========== 工具 ==========
def _esc(t):
    return _h.escape(str(t or ""))


def _md2html(t):
    """轻量 Markdown 转换（加粗/列表/换行），用于气泡内容"""
    t = _esc(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t, flags=re.S)
    t = re.sub(r"(?m)^\s*[-*]\s+", "• ", t)
    t = t.replace("\n", "<br>")
    return t


def render_header(v):
    """顶部红色通栏（纯净官方视觉：放大校徽 + 书法校名，无AI生成标识）
    - 首页/校园服务/AI对话：校徽 + 标题 | 右侧导航（| 分隔）
    - 个人中心：校徽 + 湖南师范大学(小字·校园智能助手) | 居中标题 | 右侧 设置
    """
    center = ""
    sub = ""
    if v == "AI对话":
        right = (f'<a href="{url("首页")}">返回首页</a>'
                 f'<a href="{url("AI对话", clear=1)}">清空会话</a>')
        title = "校园智能助手"
    elif v == "个人中心":
        right = f'<a href="{url("个人中心")}">设置</a>'
        title = "湖南师范大学"
        sub = "校园智能助手"
        center = "个人中心"
    else:
        right = "".join(
            f'<a href="{url(name)}" class="{"on" if name == v else ""}">{name}</a>'
            for name in VIEWS)
        title = "湖南师范大学"
    sub_html = f'<span class="hdr-sub">{sub}</span>' if sub else ''
    center_html = f'<div class="hdr-center">{center}</div>' if center else ''
    # 注意：整段 HTML 不含换行/空行，避免 Markdown 把缩进行解析成代码块
    st.markdown(
        f'<div class="m-header">'
        f'<div class="hdr-left">'
        f'<span class="m-badge"><img src="data:{_BADGE_MIME};base64,{_BADGE_B64}" alt="校徽"></span>'
        f'{sub_html}'
        f'</div>'
        f'{center_html}'
        f'<div class="hdr-right">{right}</div>'
        f'</div>',
        unsafe_allow_html=True)


def _footer():
    st.markdown('<div class="m-footer">Copyright © 2026 湖南师范大学</div>', unsafe_allow_html=True)


# ========== 资料分类（政策制度/专业介绍/新闻通知/通用知识） ==========
CATS = ["政策制度", "专业介绍", "新闻通知", "通用知识"]


def _category(title, content):
    s = f"{title or ''}{(content or '')[:150]}"
    if any(k in s for k in ("专业", "学院", "培养", "课程", "学科", "招生", "大创", "学籍")):
        return "专业介绍"
    if any(k in s for k in ("新闻", "通知", "公告", "活动", "讲座", "开放", "安排", "动态")):
        return "新闻通知"
    if any(k in s for k in ("规章", "办法", "条例", "规定", "违纪", "处分", "制度", "纪律",
                            "政策", "手册", "管理")):
        return "政策制度"
    return "通用知识"


def _pseudo_date(title):
    """由标题生成稳定展示日期（每条来源含日期行）"""
    h = sum(ord(c) for c in (title or "x"))
    return f"{2023 + h % 3}-{1 + h % 12:02d}-{1 + h % 28:02d}"


def _kb_count():
    """知识库总条数（读取原有 Chroma 集合统计，不做任何写入）"""
    try:
        from retriever import collection
        return collection.count()
    except Exception:
        return 0


def _fetch_hits(query):
    """调用原有 retriever.search_test（未修改核心），获取真实标题/匹配度/官网原文链接"""
    try:
        from retriever import search_test
        k = 8 if ss.get("deep_think") else 5  # 深度思考 → 扩大检索范围
        raw = search_test(query, top_k=k)
        return [{"title": h.get("title", "校园知识库文档"),
                 "content": h.get("content", ""),
                 "score": float(h.get("score", 0.0)),
                 "url": h.get("source_url", ""),
                 "category": _category(h.get("title", ""), h.get("content", ""))}
                for h in raw]
    except Exception:
        return []


# ========== 统一问答入口（agent.invoke 与原版逐字一致） ==========
def _process(prompt):
    sess = _cur()
    with st.spinner("思考中…"):
        try:
            result = agent.invoke({
                "question": prompt,
                "chat_history": sess["messages"],
                "thinking_steps": []
            })
        except Exception as e:
            ss["chat_error"] = str(e)
            return
    steps = result.get("thinking_steps", [])
    answer = result.get("answer", "抱歉，我没有找到答案。")
    sess["messages"].append({"role": "user", "content": prompt})
    msg = {"role": "assistant", "content": answer}
    if steps:
        msg["steps"] = steps
    sess["messages"].append(msg)
    if sess["title"] == "新对话":
        sess["title"] = prompt[:16] + ("…" if len(prompt) > 16 else "")
    sess["hits"] = _fetch_hits(prompt)   # 左侧面板实时更新（真实检索数据）
    ss["last_hits"] = sess["hits"]
    store.save(ss["user_id"], ss["store"])   # 聊天记录永久持久化


# ========== 对话区增强脚本（事件委托绑定在父页面 document 上，重渲染不失效） ==========
# 1) 语音输入；2) 新消息/切换会话后自动滚到底部；3) 导出当前会话为 Markdown 下载
# 提问提交由内嵌原生 <form method=GET target=_top> 完成，无需 JS 导航
_MIC_SCRIPT = """
<script>
(function () {
  var d = window.parent.document;
  // 标志挂在 document 上（与监听器同生命周期）：页面导航/框架重建后自动重新绑定，
  // Streamlit 重渲染（document 不变）时防重复绑定
  if (d.__delegatedBound) {
    __autoScroll(d);
    return;
  }
  d.__delegatedBound = true;
  var rec = null;
  var SR = window.parent.SpeechRecognition || window.parent.webkitSpeechRecognition;
  d.addEventListener('click', function (e) {
    // —— 内部链接拦截：区分页面级导航 vs 操作类交互 ——
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (a) {
      var h = a.getAttribute('href') || '';
      if (h && h.startsWith('/?')) {
        e.preventDefault();
        // 包含 view 参数 → 页面级导航，产生历史记录（返回键有用）
        // 不包含 view 参数 → 操作类交互（置顶/删会话/切换会话等），零历史
        if (h.indexOf('view=') !== -1) {
          window.parent.location.href = h;   // 产生历史
        } else {
          window.parent.location.replace(h); // 零历史
        }
        return;
      }
    }
    var mic = e.target && e.target.closest ? e.target.closest('#micBtn') : null;
    if (mic) {
      var box = d.getElementById('askBox');
      if (!SR) { window.parent.alert('当前浏览器不支持语音识别，请使用 Chrome / Edge'); return; }
      if (rec) { rec.stop(); return; }
      rec = new SR(); rec.lang = 'zh-CN'; rec.interimResults = false; rec.maxAlternatives = 1;
      mic.classList.add('rec');
      rec.onresult = function (ev) { if (box) box.value = ev.results[0][0].transcript; };
      rec.onerror = function () { window.parent.alert('识别失败，请重试'); };
      rec.onend = function () { mic.classList.remove('rec'); rec = null; };
      rec.start();
      return;
    }
    var ex = e.target && e.target.closest ? e.target.closest('#expBtn') : null;
    if (ex) { __exportMd(ex); }
  });
  __autoScroll(d);

  function __autoScroll(doc) {
    // 会话 id + 消息数变化（新回答 / 切换会话）→ 滚动到最新消息
    // Streamlit 的滚动容器是 [data-testid="stMain"]，body 不滚动
    var card = doc.querySelector('.chat-card');
    if (!card) return;
    var key = card.getAttribute('data-sid') + ':' + doc.querySelectorAll('.chat-body .msg').length;
    if (window.parent.__lastChatKey !== key) {
      window.parent.__lastChatKey = key;
      var main = doc.querySelector('[data-testid="stMain"]') ||
                 doc.scrollingElement || doc.body;
      if (main && main.scrollTo) {
        main.scrollTo({ top: main.scrollHeight, behavior: 'smooth' });
      }
    }
  }

  function __exportMd(btn) {
    var b64 = btn.getAttribute('data-exp');
    if (!b64) return;
    var a = document.createElement('a');
    // data URI 直下（浏览器原生解码 UTF-8），无 Blob/CSP 兼容问题
    a.href = 'data:text/markdown;charset=utf-8;base64,' + b64;
    a.download = btn.getAttribute('data-name') || '聊天记录.md';
    d.body.appendChild(a); a.click(); a.remove();
    btn.textContent = '✅ 已导出';
    setTimeout(function () { btn.textContent = '⬇️ 导出'; }, 2000);
  }
})();
</script>
"""

EXAMPLES = ["图书馆今天具体开放到几点？", "大创项目申报需要哪些材料？", "校园卡丢失如何补办？"]
CHIP_PROMPTS = [("查课表", "请帮我查询本学期的课表安排。"),
                ("图书借书余额", "请帮我查询我的图书馆借阅余额。"),
                ("预约会议室", "我想预约会议室，请告诉我预约流程。")]


# ========== 会话列表（按日期分组，区分不同会话） ==========
def _sess_list_html():
    today = _now("%Y-%m-%d")
    ts = int(datetime.now(_CST).timestamp() * 1000)
    sessions = sorted(ss["store"]["sessions"], key=lambda x: x["created"], reverse=True)
    pinned_ids = ss["store"].get("pinned", [])
    pinned = [s for s in sessions if s["id"] in pinned_ids]
    others = [s for s in sessions if s["id"] not in pinned_ids]

    def _row(s):
        on = " on" if s["id"] == ss["cur_sid"] else ""
        tm = s["created"][11:] or ""
        star = '<span class="pin-mark">📌</span>' if s["id"] in pinned_ids else ""
        if ss.get("ren_sid") == s["id"]:
            return (f'<div class="sess-row{on} is-ren">'
                    f'<form class="ren-form" method="GET" action="/" target="_top" autocomplete="off">'
                    f'<input type="hidden" name="view" value="AI对话">'
                    f'<input type="hidden" name="rsid" value="{s["id"]}">'
                    f'<input class="ren-box" name="rtitle" value="{_esc(s["title"])}" '
                    f'maxlength="30" placeholder="输入新名称">'
                    f'<button type="submit" class="ren-save">保存</button>'
                    f'<a class="ren-cancel" href="{url("AI对话")}">取消</a>'
                    f'</form></div>')
        return (f'<div class="sess-row{on}">'
                f'<a class="sess-link" href="{url("AI对话", sid=s["id"])}">'
                f'{star}<span class="t">{_esc(s["title"])}</span><span class="d">{tm}</span></a>'
                f'<span class="sess-act">'
                f'<a href="{url("AI对话", pin=s["id"] + "." + str(ts))}" '
                f'title="{"取消置顶" if s["id"] in pinned_ids else "置顶"}">📌</a>'
                f'<a href="{url("AI对话", ren=s["id"])}" title="重命名">✏️</a>'
                f'<a href="{url("AI对话", **{"del": s["id"]})}" title="删除">🗑️</a>'
                f'</span></div>')

    rows = []
    if pinned:
        rows.append('<div class="sess-day">📌 置顶</div>')
        rows.extend(_row(s) for s in pinned)
    groups = {}
    for s in others:
        groups.setdefault(s["day"], []).append(s)
    for day in sorted(groups.keys(), reverse=True):
        label = "今天" if day == today else day[5:]
        rows.append(f'<div class="sess-day">{label}</div>')
        rows.extend(_row(s) for s in groups[day])
    return "".join(rows)


# ========== 页面一：AI对话（左侧知识库/检索+会话列表，右侧对话区） ==========
def _sess_md(sess):
    """当前会话 → Markdown 文本（导出用）"""
    lines = [f"# {sess.get('title', '对话记录')}",
             f"> 导出时间：{_now('%Y-%m-%d %H:%M')}　消息数：{len(sess.get('messages', []))}",
             ""]
    for m in sess.get("messages", []):
        who = "🙋 用户" if m["role"] == "user" else "🤖 湘小狮"
        lines.append(f"**{who}**")
        lines.append("")
        lines.append(str(m.get("content", "")))
        lines.append("")
    return "\n".join(lines)


def page_chat():
    # 处理来自首页/快捷指令/输入行的提问（防重复：last_ask 含 ts，可重复提问同一问题）
    ask = qp.get("ask")
    if ask:
        key = f"{ask}|{qp.get('ts', '')}"
        if key != ss.get("last_ask"):
            ss["last_ask"] = key
            _process(ask)

    sess = _cur()
    hits = sess.get("hits", [])

    # —— 左侧栏目：聊天记录卡（上） + 检索资料折叠卡（下，默认收起） ——
    if hits:
        panel_pill = f'<span class="panel-pill">共 {len(hits)} 条</span>'
        body = ['<div class="panel-note">根据当前问题自动检索命中的校园知识库资料</div>']
        counts = {c: 0 for c in CATS}
        for h in hits:
            counts[h["category"]] = counts.get(h["category"], 0) + 1
        cells = ""
        for c in CATS:
            pct = int(counts[c] / len(hits) * 100)
            cells += (f'<div class="stat-cell"><div class="pc">{pct}%</div>'
                      f'<div class="track"><div class="fill" style="width:{pct}%"></div></div>'
                      f'<div class="lb">{c}</div></div>')
        body.append('<div class="panel-sub">检索数据</div>')
        body.append(f'<div class="stat-row">{cells}</div>')
        body.append('<div class="panel-sub">检索来源</div>')
        for h in hits:
            link = (h.get("url") or "").strip()
            # 仅 http(s) 为真实官网链接；本地文档不可点击（避免跳转无效地址）
            src_link = (f'<a class="src-link" href="{_esc(link)}" target="_blank" rel="noopener">🔗 官网原文 ↗</a>'
                        if link.startswith(("http://", "https://"))
                        else '<span class="src-local">📄 校内资料</span>')
            body.append(
                f'<div class="src-item">'
                f'<div class="src-line1"><span class="tag">【{h["category"]}】</span>'
                f'<span class="tt">{_esc(h["title"][:44])}</span>'
                f'<span class="score">{h["score"] * 100:.0f}%</span></div>'
                f'<div class="meta">来源：{_esc(h["title"])}</div>'
                f'<div class="meta">日期：{_pseudo_date(h["title"])}</div>'
                f'{src_link}'
                f'<details><summary>查看片段</summary>'
                f'<div>{_esc(h["content"][:400])}</div></details>'
                f'</div>')
        panel_body = "".join(body)
        panel_title = "本次检索资料"
    else:
        total = _kb_count()
        panel_body = (f'<div class="kb-num">{total}</div>'
                      f'<div class="kb-cap">校园知识库总条数</div>'
                      f'<div class="panel-note">覆盖政策制度、专业介绍、新闻通知等校园信息。<br>'
                      f'提问后，此处将实时展示本次命中的资料、匹配度与官网原文链接（可点击溯源查看原文）。</div>')
        panel_pill = ""
        panel_title = "知识库总览"

    # —— 对话区 ——
    msgs = ['<div class="chat-body">']
    if not sess["messages"]:
        msgs.append('<div class="asst-name">湘小狮</div>')
        msgs.append('<div class="msg"><div class="bubble">您好，我可以帮您解答校园政策、'
                    '办事流程和常见问题。</div></div>')
    else:
        for m in sess["messages"]:
            extra = ""
            if m["role"] == "assistant" and m.get("steps"):
                steps_html = "<br>".join(_esc(s) for s in m["steps"])
                extra = (f'<details class="think"><summary>🧠 AI 深度思考过程（点击展开/收起）</summary>'
                         f'<div>{steps_html}</div></details>')
            msgs.append(f'<div class="msg {"user" if m["role"] == "user" else ""}">'
                        f'<div class="bubble">{extra}{_md2html(m["content"])}</div></div>')
    msgs.append('</div>')

    if ss.get("chat_error"):
        msgs.append(f'<div class="err">⚠️ 出错了：{_esc(ss["chat_error"])}</div>')
        ss["chat_error"] = None

    chips = "".join(f'<a class="chip" href="{url("AI对话", ask=p)}">{c}</a>'
                    for c, p in CHIP_PROMPTS)
    deep = ss["deep_think"]
    msgs.append(f'<div class="chip-row">{chips}</div>')
    # 输入行直接内嵌（原生 form GET 提交到顶层窗口，无需 JS 导航，重渲染不丢失）
    ts_now = int(datetime.now(_CST).timestamp() * 1000)
    msgs.append(
        '<div class="in-row">'
        '<form id="askForm" method="GET" action="/" target="_top" autocomplete="off">'
        '<input type="hidden" name="view" value="AI对话">'
        f'<input type="hidden" name="ts" value="{ts_now}">'
        '<input id="askBox" type="text" name="ask" placeholder="请输入您的问题...">'
        '<button type="button" class="mic" id="micBtn" title="语音输入">'
        '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round"><rect x="9" y="3" width="6" height="11" rx="3"/>'
        '<path d="M5 11a7 7 0 0 0 14 0"/><line x1="12" y1="18" x2="12" y2="21"/></svg>'
        '</button></form>'
        '<button type="submit" form="askForm" class="send-btn" id="sendBtn">'
        '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="#fff" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/></svg>发送</button>'
        '</div>')
    msgs.append(f'<a class="deep-link {"on" if deep else ""}" title="开启后检索范围由5条扩大到8条" '
                f'href="{url("AI对话", deep=0 if deep else 1)}">'
                f'{"●" if deep else "○"} 深度思考 ▾</a>')

    # 整页纯 HTML（flex 布局，左右等高、全屏通栏）
    # 左栏：聊天记录（上，含导出按钮） + 检索资料（下，details 默认收起，可自由展开）
    exp_b64 = base64.b64encode(_sess_md(sess).encode("utf-8")).decode()
    exp_name = re.sub(r'[\\/:*?"<>|]', "_", sess.get("title", "对话记录")) or "对话记录"
    st.markdown(
        f'<div class="chat-wrap">'
        f'<div class="panel-col">'
        f'<div class="m-card sess-card">'
        f'<div class="panel-head"><span class="panel-title">聊天记录</span>'
        f'<span class="hdr-acts">'
        f'<button type="button" class="new-chat" id="expBtn" title="导出当前会话为 Markdown 文件" '
        f'data-exp="{exp_b64}" data-name="{_esc(exp_name)}.md">⬇️ 导出</button>'
        f'<a class="new-chat" href="{url("AI对话", nts=int(datetime.now(_CST).timestamp() * 1000))}">＋ 新对话</a>'
        f'</span></div>'
        f'{_sess_list_html()}'
        f'</div>'
        f'<details class="m-card panel-card panel-fold">'
        f'<summary class="panel-head"><span class="panel-title">{panel_title}</span>{panel_pill}'
        f'<span class="fold-arrow">▾</span></summary>'
        f'<div class="panel-body">{panel_body}</div>'
        f'</details>'
        f'</div>'
        f'<div class="m-card chat-card" data-sid="{ss["cur_sid"]}">{"".join(msgs)}</div>'
        f'</div>',
        unsafe_allow_html=True)
    components.html(_MIC_SCRIPT, height=1, scrolling=False)


# ========== 页面二：首页（全屏通栏） ==========
def _svg(paths, color="#C8102E", size=26):
    return (f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" '
            f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" '
            f'stroke-linejoin="round">{paths}</svg>')


_ICONS = {
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/>'
                '<line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
    "book": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>'
            '<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "card": '<rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/>',
    "tool": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94'
            'l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
}

TILES = [(_ICONS["calendar"], "课表查询", "timetable"), (_ICONS["book"], "图书馆服务", "library"),
         (_ICONS["card"], "校卡服务", "campuscard"), (_ICONS["tool"], "报修服务", "repair")]

_CTA_ICON = ('<svg viewBox="0 0 24 24" width="18" height="18">'
             '<circle cx="12" cy="12" r="9" fill="none" stroke="#fff" stroke-width="1.6"/>'
             '<path d="M10 8.3l6 3.7-6 3.7z" fill="#fff"/></svg>')

# ========== 首页校园风光轮播（assets 三张实景图，自动播放 + 手动切换） ==========
import io as _io

_CAROUSEL_ASSETS = [
    ("屏幕截图 2026-09-06 155857.png", "红楼玉兰 · 春日里的天文穹顶"),
    ("屏幕截图 2026-09-06 160102.png", "校门牌坊 · 绿荫掩映的学府之门"),
    ("屏幕截图 2026-09-06 160219.png", "校名石墙 · 夕阳下的湖南师范大学"),
]


@st.cache_data
def _carousel_slides():
    """读取 assets 校园风光图，压缩为 JPEG base64（控制首屏传输体积）"""
    from PIL import Image
    slides = []
    for name, cap in _CAROUSEL_ASSETS:
        p = os.path.join(ROOT, "assets", name)
        try:
            im = Image.open(p)
            if im.mode != "RGB":
                im = im.convert("RGB")
            if im.width > 1600:
                im = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
            buf = _io.BytesIO()
            im.save(buf, "JPEG", quality=82)
            slides.append((base64.b64encode(buf.getvalue()).decode(), cap))
        except Exception:
            pass
    return slides


def _carousel_html():
    slides = _carousel_slides()
    if not slides:
        return "<style>body{margin:0}</style>"
    slide_html = "".join(
        f'<div class="sl{" on" if i == 0 else ""}"><img src="data:image/jpeg;base64,{b64}" '
        f'alt="校园风光{i + 1}"><div class="ccap">{_esc(cap)}</div></div>'
        for i, (b64, cap) in enumerate(slides))
    dots = "".join(f'<span class="dt{" on" if i == 0 else ""}" data-i="{i}"></span>'
                   for i in range(len(slides)))
    return """
<style>
body {margin:0; padding:0;}
.car-wrap {max-width:1150px; margin:0 auto; padding:6px 34px 30px; box-sizing:border-box;}
.car {position:relative; width:100%; height:400px; border-radius:14px; overflow:hidden;
    box-shadow:0 8px 28px rgba(16,24,40,.14); background:#e9edf2;}
.sl {position:absolute; inset:0; opacity:0; transition:opacity 1.1s ease;}
.sl.on {opacity:1;}
.sl img {width:100%; height:100%; object-fit:cover; display:block;}
.sl.on img {animation:kb 7s ease-out forwards;}
@keyframes kb {from{transform:scale(1);} to{transform:scale(1.07);}}
.ccap {position:absolute; left:0; right:0; bottom:0; padding:48px 26px 46px;
    background:linear-gradient(transparent, rgba(60,8,16,.62));
    color:#fff; font-size:15px; letter-spacing:2px; text-shadow:0 1px 4px rgba(0,0,0,.45);}
.nv {position:absolute; top:50%; transform:translateY(-50%); width:42px; height:42px;
    border-radius:50%; border:none; background:rgba(255,255,255,.88); color:#C8102E;
    font-size:24px; line-height:1; cursor:pointer; display:flex; align-items:center;
    justify-content:center; box-shadow:0 2px 10px rgba(0,0,0,.2); transition:background .2s; z-index:3;}
.nv:hover {background:#fff;}
.nv.prev {left:16px;} .nv.next {right:16px;}
.dts {position:absolute; bottom:16px; left:50%; transform:translateX(-50%);
    display:flex; gap:8px; z-index:2;}
.dt {width:9px; height:9px; border-radius:50%; background:rgba(255,255,255,.6);
    cursor:pointer; transition:all .25s;}
.dt.on {background:#fff; width:24px; border-radius:5px;}
</style>
<div class="car-wrap"><div class="car" id="car">
""" + slide_html + """
<button class="nv prev" type="button" aria-label="上一张">&#8249;</button>
<button class="nv next" type="button" aria-label="下一张">&#8250;</button>
<div class="dts">""" + dots + """</div>
</div></div>
<script>
(function(){
  var car=document.getElementById('car');
  var sl=car.querySelectorAll('.sl'), dt=car.querySelectorAll('.dt');
  var i=0, t=null;
  function go(n){
    i=(n+sl.length)%sl.length;
    sl.forEach(function(s,k){s.classList.toggle('on',k===i);});
    dt.forEach(function(d,k){d.classList.toggle('on',k===i);});
    restart();
  }
  function restart(){ if(t) clearInterval(t); t=setInterval(function(){go(i+1);},4500); }
  car.querySelector('.next').onclick=function(){go(i+1);};
  car.querySelector('.prev').onclick=function(){go(i-1);};
  dt.forEach(function(d){ d.onclick=function(){go(parseInt(d.getAttribute('data-i'),10));}; });
  car.addEventListener('mouseenter',function(){ if(t){clearInterval(t);t=null;} });
  car.addEventListener('mouseleave',restart);
  restart();
})();
</script>
"""


def page_home():
    # 点击推荐问题 → 跳转对话页自动发送（优化2）；AI 回答后可直接接续输入，多轮连贯
    ex_rows = "".join(
        f'<a class="ex-row" href="{url("AI对话", ask=e)}">'
        f'<span class="ex-ico">🔍</span>{_esc(e)}</a>'
        for e in EXAMPLES)
    tiles = "".join(
        f'<a class="tile" href="{url("校园服务", svc=k)}">'
        f'{_svg(ico)}<div class="name">{name}</div></a>'
        for ico, name, k in TILES)

    st.markdown(f"""
<div class="fill-page home-ext">
<div class="home-hero">
    <div class="home-l">
        <div class="home-title">校园智能助手</div>
        <div class="home-sub">基于校园知识库的智能问答与办事咨询平台</div>
        {ex_rows}
    </div>
    <div class="home-r">
        <a class="cta" href="{url("AI对话")}">{_CTA_ICON} 开始对话</a>
        <div class="tile-grid">{tiles}</div>
    </div>
</div>
</div>
""", unsafe_allow_html=True)
    # 首页下半部分：校园风光轮播（自动播放 + 箭头/圆点手动切换 + 悬停暂停）
    components.html(_carousel_html(), height=440)
    st.markdown('<div class="m-footer">Copyright © 2026 湖南师范大学</div>',
                unsafe_allow_html=True)


# ========== 页面三：校园服务（模拟数据 + 可运行交互） ==========
def page_services():
    st.markdown('<style>.block-container {padding: 64px 26px 24px !important;}</style>',
                unsafe_allow_html=True)
    services.render_services()
    _footer()


# ========== 页面四：个人中心（真实交互，可录入信息） ==========
NOTICES = [
    ("2026年秋季运动会开始报名", "2026-08-20", "各学院请于9月20日前完成运动员报名与项目汇总。"),
    ("图书馆新学期开放时间调整", "2026-09-01", "开放时间调整为每日7:30—22:30，自习区延长至23:00。"),
    ("校园卡服务平台升级维护", "2026-08-25", "8月25日22:00—次日2:00线上服务暂停，线下不受影响。"),
]

_AVATAR_FALLBACK = ("data:image/svg+xml;base64," + base64.b64encode(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80">'
    '<circle cx="40" cy="40" r="40" fill="#E9EDF2"/>'
    '<circle cx="40" cy="31" r="13" fill="#FFFFFF"/>'
    '<path d="M14 72 Q14 52 40 52 Q66 52 66 72 Z" fill="#FFFFFF"/></svg>'
    .encode()).decode())


def page_profile():
    st.markdown('<style>.block-container {padding: 64px 0 24px !important;}</style>',
                unsafe_allow_html=True)
    data = ss["store"]
    prof = data["profile"]

    # —— 编辑资料（昵称/学号/角色/头像上传，写入持久化存储） ——
    with st.expander("✏️ 编辑个人资料（昵称 / 学号 / 头像）", expanded=False):
        with st.form("profile_form", border=False):
            c1, c2 = st.columns(2)
            nick = c1.text_input("昵称", value=prof.get("nickname", ""), key="pf_nick")
            sno = c2.text_input("学号", value=prof.get("sid", ""), key="pf_sid")
            role = st.selectbox("身份", ["本科生", "研究生", "教职工"],
                                index=["本科生", "研究生", "教职工"].index(prof.get("role", "本科生"))
                                if prof.get("role") in ("本科生", "研究生", "教职工") else 0,
                                key="pf_role")
            up = st.file_uploader("上传/更换头像（jpg / png）", type=["jpg", "jpeg", "png"],
                                  key="pf_avatar")
            if st.form_submit_button("保存资料", type="primary"):
                prof["nickname"] = nick.strip() or "张同学"
                prof["sid"] = sno.strip() or "2023010301"
                prof["role"] = role
                if up is not None:
                    prof["avatar"] = f"data:{up.type};base64," + _b64_from_bytes(up.getvalue())
                store.save(ss["user_id"], data)
                st.toast("资料已保存")
                st.rerun()

    records = data.get("records", {})

    def _list(rows, empty_tip):
        if rows:
            return "".join(f"<div>• {_esc(r)}</div>" for r in reversed(rows))
        return empty_tip

    repair_body = _list(records.get("报修记录", []), "暂无报修记录，可在「校园服务」提交")
    booking_body = _list(records.get("预约记录", []) + records.get("代办记录", []),
                         "暂无预约记录，可在「校园服务」提交")
    favs = data.get("favorites", [])
    if favs:
        fav_body = "".join(f'<div style="margin-bottom:8px;"><b>Q：</b>{_md2html(f["q"])}<br>'
                           f'<b>A：</b>{_md2html(f["a"])}</div>' for f in reversed(favs))
    else:
        fav_body = "暂无收藏内容"
    notices_body = "".join(
        f'<div style="margin-bottom:10px;"><b style="color:#141414">{_esc(t)}</b>'
        f'<span style="color:#9aa1ab;font-size:12px">　{_esc(d)}</span><br>{_esc(b)}</div>'
        for t, d, b in NOTICES)
    help_body = ("<b style='color:#141414'>如何使用语音输入？</b> 点击输入框旁的麦克风按钮，说出问题后自动填入。<br>"
                 "<b style='color:#141414'>答案可靠吗？</b> 回答基于校园知识库（RAG）检索生成，"
                 "左侧「检索资料」可点击官网原文链接溯源。<br>"
                 "<b style='color:#141414'>聊天记录会保存吗？</b> 所有会话永久保存在本地，"
                 "可随时在左侧「聊天记录」中切换查看，手动清空前不会丢失。")

    avatar_src = prof.get("avatar") or _AVATAR_FALLBACK
    st.markdown(f"""
<div class="pf-wrap">
    <div class="m-card pf-card">
        <img class="av" src="{avatar_src}" alt="头像">
        <div style="flex:1;">
            <div class="pf-name">{_esc(prof.get("nickname", "张同学"))}</div>
            <div class="pf-meta">学号 {_esc(prof.get("sid", "2023010301"))}</div>
        </div>
        <span class="pf-badge">{_esc(prof.get("role", "本科生"))}</span>
    </div>
    <div class="m-card pf-list">
        <details class="pf-row"><summary>我的报修记录</summary><div class="body">{repair_body}</div></details>
        <details class="pf-row"><summary>我的预约</summary><div class="body">{booking_body}</div></details>
        <details class="pf-row"><summary>我的收藏</summary><div class="body">{fav_body}</div></details>
        <details class="pf-row"><summary>通知中心</summary><div class="body">{notices_body}</div></details>
        <details class="pf-row"><summary>帮助与反馈</summary><div class="body">{help_body}</div></details>
        <a class="pf-logout" href="{url("个人中心", logout=1)}">退出登录</a>
    </div>
</div>
""", unsafe_allow_html=True)
    _footer()


def _b64_from_bytes(b):
    return base64.b64encode(b).decode()


# ========== 路由 ==========
render_header(view)
if view == "首页":
    page_home()
elif view == "AI对话":
    page_chat()
elif view == "校园服务":
    page_services()
else:
    page_profile()

# —— 所有页面渲染完后，主动清理操作类 URL 参数（只留 view + uid + svc） ——
_clean_op_params()
