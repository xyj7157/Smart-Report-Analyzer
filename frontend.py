import time
import requests
import streamlit as st
import pandas as pd
import plotly.express as px

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="智能财报分析系统", page_icon="📊", layout="wide")


# ===== 初始化登录状态 =====
if "token" not in st.session_state:
    st.session_state.token = None
if "username" not in st.session_state:
    st.session_state.username = None


def auth_headers():
    """构造带 token 的请求头"""
    return {"Authorization": f"Bearer {st.session_state.token}"}


# ===== 登录 / 注册界面（未登录时显示）=====
def show_login_page():
    st.title("🔐 智能财报分析系统 · 登录")
    tab1, tab2 = st.tabs(["登录", "注册"])

    with tab1:
        st.subheader("已有账号？登录")
        username = st.text_input("用户名", key="login_user")
        password = st.text_input("密码", type="password", key="login_pwd")
        if st.button("🚀 登录", use_container_width=True):
            try:
                resp = requests.post(
                    f"{API_URL}/login",
                    json={"username": username, "password": password},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state.token = data["token"]
                    st.session_state.username = data["username"]
                    st.success(f"✅ 欢迎回来，{data['username']}！")
                    st.rerun()
                else:
                    st.error(f"❌ 登录失败：{resp.json().get('detail')}")
            except Exception as e:
                st.error(f"❌ 无法连接后端：{e}")

    with tab2:
        st.subheader("新用户？注册")
        new_user = st.text_input("用户名", key="reg_user")
        new_pwd = st.text_input("密码（至少6位）", type="password", key="reg_pwd")
        if st.button("✅ 注册", use_container_width=True):
            try:
                resp = requests.post(
                    f"{API_URL}/register",
                    json={"username": new_user, "password": new_pwd},
                )
                if resp.status_code == 200:
                    st.success("🎉 注册成功！请切到「登录」标签页登录。")
                else:
                    st.error(f"❌ 注册失败：{resp.json().get('detail')}")
            except Exception as e:
                st.error(f"❌ 无法连接后端：{e}")


# ===== 主应用（已登录后显示）=====
def show_main_app():
    st.set_page_config(page_title="智能财报分析系统", page_icon="📊", layout="wide")
    st.title(f"📊 智能财报分析系统 · 你好，{st.session_state.username}")

    # 退出登录
    with st.sidebar:
        if st.button("🚪 退出登录"):
            st.session_state.token = None
            st.session_state.username = None
            st.rerun()

        st.divider()
        uploaded_files = st.file_uploader(
            "上传财报 PDF（可多选）", type=["pdf"], accept_multiple_files=True
        )
        analyze_btn = st.button("🚀 开始智能分析", use_container_width=True)

    # --- 上传分析区 ---
    if analyze_btn:
        if not uploaded_files:
            st.warning("⚠️ 请先上传至少一份 PDF 文件！")
        else:
            tasks = []
            with st.spinner(f"正在提交 {len(uploaded_files)} 个文件..."):
                for uploaded_file in uploaded_files:
                    files = {
                        "file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")
                    }
                    # 👇 关键：带上 token
                    response = requests.post(
                        f"{API_URL}/analyze", files=files, headers=auth_headers()
                    )
                    if response.status_code == 200:
                        task_id = response.json()["task_id"]
                        tasks.append({"task_id": task_id, "filename": uploaded_file.name})
                    else:
                        st.error(f"❌ {uploaded_file.name} 提交失败：{response.text}")

            if tasks:
                st.success(f"✅ 已提交 {len(tasks)} 个任务，AI 后台处理中！")
                cols = st.columns(len(tasks))
                placeholders = [c.empty() for c in cols]

                all_done = False
                while not all_done:
                    all_done = True
                    for i, task in enumerate(tasks):
                        if task.get("done"):
                            continue
                        status_res = requests.get(
                            f"{API_URL}/status/{task['task_id']}", headers=auth_headers()
                        ).json()
                        status = status_res.get("status")
                        if status == "success":
                            task["done"] = True
                            with placeholders[i].container():
                                data = status_res["result"]
                                st.success(f"🎉 {task['filename']} 完成")
                                st.markdown(f"**{data['company_name']}** · {data['industry']}")
                                st.metric("营收同比增长率", f"{data['growth_rate']}%")
                                st.info(data["summary"])
                        elif status == "failed":
                            task["done"] = True
                            with placeholders[i].container():
                                st.error(f"❌ {task['filename']} 失败：{status_res.get('message')}")
                        else:
                            all_done = False
                            with placeholders[i].container():
                                st.warning(f"⏳ {task['filename']}：{status_res.get('message')}")
                    if not all_done:
                        time.sleep(2)

    # --- 我的研报列表（数据隔离的体现）---
    st.divider()
    st.subheader("📚 我的研报（仅你可见）")
    try:
        resp = requests.get(f"{API_URL}/my-reports", headers=auth_headers())
        if resp.status_code == 200:
            reports = resp.json()
            if not reports:
                st.info("你还没有研报，上传一份 PDF 开始分析吧！")
            else:
                for r in reports:
                    with st.expander(f"📄 {r['company_name']} · {r['industry']}"):
                        st.write(f"营收：{r['revenue_current']} 亿元 ｜ 净利润：{r['net_profit']} 亿元")
                        st.write(f"同比增长率：{r['growth_rate']}%")
                        st.write(f"分析时间：{r['created_at']}")
                        st.info(r["summary"])
        else:
            st.error("加载研报列表失败")
    except Exception as e:
        st.error(f"❌ 加载失败：{e}")


# ===== 入口：根据是否登录决定显示哪个页面 =====
if st.session_state.token:
    show_main_app()
else:
    show_login_page()
