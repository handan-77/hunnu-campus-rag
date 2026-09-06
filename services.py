# -*- coding: utf-8 -*-
"""
校园服务模块（最终优化版·优化7）
- 学习服务：课表查询、成绩查询、考试安排、图书馆服务
- 生活服务：校园卡服务、设施报修、快递代取、会议室预约
- 全部接入可运行模拟数据（data/mock/*.json），提交即出结果，可直接演示交互；
  替换 JSON 文件内容即可接入真实官方数据。
- 办理类记录写入持久化用户存储（store），在「个人中心」可见。
"""
import json
import os
import time
import html as _h

import streamlit as st

import store

MOCK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mock")


def _esc(v):
    return _h.escape(str(v))


def _mock(name):
    """读取模拟数据文件（缺失时返回空表，页面不崩）"""
    try:
        with open(os.path.join(MOCK_DIR, f"{name}.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _fmt(v) -> str:
    v = str(v or "").strip()
    return v if v else "未填写"


def _table(headers, rows):
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return (f'<table class="mock-table"><thead><tr>{th}</tr></thead>'
            f'<tbody>{trs}</tbody></table>')


def _save_record(kind: str, text: str):
    """办理类服务写入持久化记录（个人中心可见）"""
    st.session_state["store"].setdefault("records", {}).setdefault(kind, []).append(text)
    store.save(st.session_state.get("user_id", "default"), st.session_state["store"])


# 字段类型: select / text / area / date
# follow：查询/办理完成后「去AI对话继续追问」携带的引导问题
SERVICES = [
    # ---------- 学习服务 ----------
    {"key": "timetable", "name": "课表查询", "group": "学习服务", "icon": "📅",
     "follow": "请帮我解读本学期的课表安排和注意事项",
     "fields": [
         {"t": "select", "label": "学期", "opts": ["2026-2027 第一学期", "2025-2026 第二学期"]},
         {"t": "select", "label": "视图", "opts": ["周视图", "日视图"]},
         {"t": "select", "label": "周次", "opts": ["全部周", "第1-8周", "第9-16周"]},
     ],
     "submit": "查询课表"},

    {"key": "score", "name": "成绩查询", "group": "学习服务", "icon": "📊",
     "follow": "请帮我分析我的成绩和绩点情况",
     "fields": [
         {"t": "select", "label": "学期", "opts": ["2026-2027 第一学期", "2025-2026 第二学期"]},
         {"t": "select", "label": "课程类型", "opts": ["全部课程", "必修课", "选修课"]},
     ],
     "submit": "查询成绩"},

    {"key": "exam", "name": "考试安排", "group": "学习服务", "icon": "📝",
     "follow": "请帮我梳理考试安排和备考注意事项",
     "fields": [
         {"t": "select", "label": "学期", "opts": ["2026-2027 第一学期", "2025-2026 第二学期"]},
     ],
     "submit": "查询考试安排"},

    {"key": "library", "name": "图书馆服务", "group": "学习服务", "icon": "📚",
     "follow": "请介绍图书馆的借阅规则和开放时间",
     "fields": [
         {"t": "select", "label": "业务", "opts": ["图书检索", "我的借阅", "续借办理", "个性化书籍推荐"]},
         {"t": "text", "label": "关键词", "ph": "如：书名 / 作者（选填）"},
     ],
     "submit": "办理图书馆业务"},

    # ---------- 生活服务 ----------
    {"key": "campuscard", "name": "校园卡服务", "group": "生活服务", "icon": "💳",
     "follow": "校园卡丢失了如何挂失补办？",
     "fields": [
         {"t": "select", "label": "业务", "opts": ["余额查询", "消费记录", "在线充值"]},
         {"t": "text", "label": "充值金额", "ph": "如：100（仅在线充值时填写）"},
     ],
     "submit": "办理校园卡业务"},

    {"key": "repair", "name": "校园设施报修", "group": "生活服务", "icon": "🔧",
     "follow": "报修提交后一般多久会有师傅上门处理？",
     "fields": [
         {"t": "text", "label": "报修地点", "ph": "如：桃花坪宿舍 3 栋 502"},
         {"t": "area", "label": "故障描述", "ph": "如：宿舍热水器无法加热"},
         {"t": "select", "label": "紧急程度", "opts": ["普通", "紧急"]},
     ],
     "submit": "提交报修",
     "record": "报修记录"},

    {"key": "express", "name": "快递代取", "group": "生活服务", "icon": "📦",
     "follow": "快递代取一般多久能送达？",
     "fields": [
         {"t": "text", "label": "快递单号", "ph": "粘贴物流单号"},
         {"t": "text", "label": "取件码", "ph": "如：3-2-1008"},
         {"t": "text", "label": "联系电话", "ph": "选填"},
     ],
     "submit": "提交代取申请",
     "record": "代办记录"},

    {"key": "meeting", "name": "会议室/场地预约", "group": "生活服务", "icon": "🏢",
     "follow": "会议室预约成功后如何取消或改期？",
     "fields": [
         {"t": "date", "label": "日期"},
         {"t": "select", "label": "时间段", "opts": ["8:00-10:00", "10:00-12:00", "14:00-16:00", "16:00-18:00", "18:00-21:00"]},
         {"t": "select", "label": "场地", "opts": ["图书馆研讨室 A", "图书馆研讨室 B", "中和楼 301", "中和楼 302", "学生活动中心多功能厅"]},
         {"t": "text", "label": "事由", "ph": "如：大创项目小组讨论"},
     ],
     "submit": "提交预约",
     "record": "预约记录"},
]


# ========== 模拟结果生成 ==========
def _result_html(key, vals):
    if key == "timetable":
        d = _mock("timetable")
        rows = [[r.get("day"), r.get("period"), r.get("name"), r.get("teacher"), r.get("room")]
                for r in d.get("rows", [])]
        body = _table(["星期", "时间", "课程", "教师", "教室"], rows)
        return f'📋 课表查询结果（{_esc(vals.get("学期", ""))} · {_esc(vals.get("视图", ""))} · {_esc(vals.get("周次", ""))}）', body

    if key == "score":
        d = _mock("grades")
        ftype = vals.get("课程类型", "全部课程")
        rows = [[g.get("course"), g.get("type"), g.get("credit"), g.get("score"), g.get("gpa")]
                for g in d.get("items", []) if ftype == "全部课程" or g.get("type") == ftype]
        body = _table(["课程", "类型", "学分", "成绩", "绩点"], rows)
        body += (f'<div class="mock-kv" style="margin-top:8px;">平均成绩：<b>{d.get("avg", "-")}</b>　'
                 f'平均绩点：<b>{d.get("gpa", "-")}</b>　专业排名：<b>{d.get("rank", "-")}</b></div>')
        return f'📊 成绩查询结果（{_esc(vals.get("学期", ""))}）', body

    if key == "exam":
        d = _mock("exams")
        rows = [[e.get("course"), e.get("date"), e.get("time"), e.get("room"), e.get("seat")]
                for e in d.get("items", [])]
        body = _table(["课程", "日期", "时间", "地点", "座位号"], rows)
        return f'📝 考试安排（{_esc(vals.get("学期", ""))}）', body

    if key == "library":
        d = _mock("library")
        biz = vals.get("业务", "图书检索")
        kw = (vals.get("关键词") or "").strip()
        if biz in ("我的借阅", "续借办理"):
            rows = [[b.get("title"), b.get("author"), b.get("borrow"), b.get("due"), b.get("status")]
                    for b in d.get("loans", [])]
            body = _table(["书名", "作者", "借出日期", "应还日期", "状态"], rows)
            if biz == "续借办理" and rows:
                body += '<div class="mock-kv" style="margin-top:8px;">本次续借：<b>全部在借书目续借 30 天成功</b></div>'
            return f'📚 我的借阅', body
        items = d.get("search", [])
        if kw:
            items = [b for b in items if kw in (b.get("title", "") + b.get("author", ""))] or d.get("search", [])
        rows = [[b.get("title"), b.get("author"), b.get("loc"), b.get("avail")] for b in items]
        body = _table(["书名", "作者", "馆藏位置", "状态"], rows)
        tip = f'（关键词：{_esc(kw)}）' if kw else ""
        return f'📚 图书检索结果{tip}', body

    if key == "campuscard":
        d = _mock("campuscard")
        biz = vals.get("业务", "余额查询")
        if biz == "余额查询":
            body = f'<div class="mock-kv">卡号：<b>{d.get("card_no", "2023****0301")}</b>　当前余额：<b>{d.get("balance", "-")} 元</b></div>'
            return '💳 校园卡余额', body
        if biz == "在线充值":
            amt = _fmt(vals.get("充值金额"))
            try:
                amt_f = float(amt)
                new = round(float(d.get("balance", 0)) + amt_f, 2)
                body = (f'<div class="mock-kv">充值金额：<b>{amt_f:.2f} 元</b>　'
                        f'支付渠道：<b>模拟支付（演示）</b>　充值后余额：<b>{new} 元</b></div>')
            except ValueError:
                body = '<div class="mock-kv">未填写有效金额，演示充值 <b>100.00 元</b> 成功（模拟支付）。</div>'
            return '💳 在线充值结果', body
        rows = [[r.get("time"), r.get("desc"), r.get("amount"), r.get("channel")]
                for r in d.get("records", [])]
        body = _table(["时间", "摘要", "金额（元）", "渠道"], rows)
        body += f'<div class="mock-kv" style="margin-top:8px;">当前余额：<b>{d.get("balance", "-")} 元</b></div>'
        return '💳 消费记录', body

    if key == "repair":
        no = "RP" + time.strftime("%Y%m%d%H%M%S")
        d = _mock("repair")
        body = (f'<div class="mock-kv">工单号：<b>{no}</b>　状态：<b>已受理</b>　'
                f'紧急程度：<b>{_esc(vals.get("紧急程度", "普通"))}</b></div>'
                f'<div class="mock-kv">报修地点：{_esc(_fmt(vals.get("报修地点")))}　'
                f'承诺响应：<b>{d.get("sla", "24 小时内上门")}</b></div>'
                f'<div class="mock-kv">维修师傅：<b>{d.get("master", "张师傅")}</b>　'
                f'联系电话：<b>{d.get("phone", "0731-888****")}</b></div>')
        return '🔧 报修受理结果', body

    if key == "express":
        no = "ED" + time.strftime("%Y%m%d%H%M%S")
        d = _mock("express")
        body = (f'<div class="mock-kv">代取单号：<b>{no}</b>　状态：<b>已接单</b>　'
                f'取件码：<b>{_esc(_fmt(vals.get("取件码")))}</b></div>'
                f'<div class="mock-kv">代取员：<b>{d.get("courier", "李同学")}</b>　'
                f'预计送达：<b>{d.get("eta", "今天 18:00 前")}</b>　'
                f'代取费：<b>{d.get("fee", "2 元/件")}</b></div>')
        return '📦 快递代取受理结果', body

    if key == "meeting":
        d = _mock("meeting")
        room = vals.get("场地", "")
        code = d.get("codes", {}).get(room, "A-302")
        body = (f'<div class="mock-kv">预约成功！确认码：<b>{code}</b></div>'
                f'<div class="mock-kv">场地：<b>{_esc(room)}</b>　日期：<b>{_esc(vals.get("日期", ""))}</b>　'
                f'时间段：<b>{_esc(vals.get("时间段", ""))}</b></div>'
                f'<div class="mock-kv">事由：{_esc(_fmt(vals.get("事由")))}　'
                f'温馨提示：{d.get("tip", "请提前 10 分钟到场签到使用")}</div>')
        return '🏢 会议室预约结果', body

    return "办理结果", "<div class='mock-kv'>演示数据暂未覆盖该业务。</div>"


def _chat_link(ask):
    """构造带 ts 的 AI对话链接（可重复点击重复提问）"""
    from urllib.parse import quote
    return ("/?" + "&".join(f"{k}={quote(str(v))}" for k, v in
                            (("view", "AI对话"), ("ask", ask),
                             ("ts", int(time.time() * 1000)))))


def render_services():
    """校园服务页：按 学习服务 / 生活服务 分组，双栏表单卡片，全屏通栏
    查询/办理结果直接显示在对应表单卡片内，并提供「去AI对话继续追问」入口"""
    st.markdown('<div class="m-sectitle">校园服务</div>', unsafe_allow_html=True)
    st.caption("以下全部为可运行测试数据。模拟数据存放目录：data/mock/（timetable、grades、exams、"
               "library、campuscard、repair、express、meeting.json），替换 JSON 内容即可接入真实官方数据。"
               "办理类提交后可在「个人中心」查看记录。")

    # 展开状态集合：URL svc 参数 / 表单提交都会加入，保证 rerun 后 expander 不被收起
    open_set = st.session_state.setdefault("svc_open", set())
    st.session_state.setdefault("svc_results", {})   # {service_key: (icon, title, body)}

    for group, icon in (("学习服务", "🎓"), ("生活服务", "🧰")):
        st.markdown(f'<div class="svc-group">{icon} {group}</div>', unsafe_allow_html=True)
        items = [x for x in SERVICES if x["group"] == group]
        cols = st.columns(2, gap="medium")
        for i, s in enumerate(items):
            with cols[i % 2]:
                with st.expander(f'{s["icon"]} {s["name"]}', expanded=(s["key"] in open_set)):
                    with st.form(f"form_{s['key']}", border=False):
                        vals = {}
                        for f in s["fields"]:
                            k = f"{s['key']}_{f['label']}"
                            if f["t"] == "select":
                                vals[f["label"]] = st.selectbox(f["label"], f["opts"], key=k)
                            elif f["t"] == "text":
                                vals[f["label"]] = st.text_input(f["label"], placeholder=f.get("ph", ""), key=k)
                            elif f["t"] == "area":
                                vals[f["label"]] = st.text_area(f["label"], placeholder=f.get("ph", ""), key=k)
                            elif f["t"] == "date":
                                vals[f["label"]] = st.date_input(f["label"], key=k)

                        if st.form_submit_button(s["submit"], type="primary", use_container_width=True):
                            open_set.add(s["key"])       # 提交后保持该卡片展开
                            if "record" in s:
                                detail = "；".join(f"{k2}：{_fmt(v)}" for k2, v in vals.items()
                                                  if k2 != "充值金额")
                                _save_record(s["record"], f'{s["name"]}｜{detail}')
                                st.toast("提交成功，已在「个人中心」生成记录")
                            title, body = _result_html(s["key"], vals)
                            st.session_state["svc_results"][s["key"]] = (s["icon"], title, body)

                    # —— 查询/办理结果：显示在对应表单卡片内 ——
                    res = st.session_state["svc_results"].get(s["key"])
                    if res:
                        r_icon, r_title, r_body = res
                        st.markdown(f'<div class="mock-card"><div class="mock-title">{r_icon} {r_title}</div>{r_body}</div>',
                                    unsafe_allow_html=True)
                        st.markdown(f'<a class="svc-ask" href="{_chat_link(s.get("follow", s["name"]))}">'
                                    f'🤖 去AI对话继续追问</a>', unsafe_allow_html=True)
