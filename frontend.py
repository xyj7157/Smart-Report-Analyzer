import time
import requests
import streamlit as st
import pandas as pd
import plotly.express as px

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="智能财报分析系统", page_icon="📊", layout="wide")
st.title("📊 智能财报分析系统 ")

with st.sidebar:
    # 👇 核心改动：加上 accept_multiple_files=True
    uploaded_files = st.file_uploader("请上传财报 PDF 文件 (可多选)", type=["pdf"], accept_multiple_files=True)
    analyze_btn = st.button("🚀 开始智能分析", use_container_width=True)

if analyze_btn:
    if not uploaded_files:
        st.warning("⚠️ 请先上传至少一份 PDF 文件！")
    else:
        tasks = []

        # 1. 批量提交任务
        with st.spinner(f"正在提交 {len(uploaded_files)} 个文件到后台队列..."):
            for uploaded_file in uploaded_files:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                response = requests.post(f"{API_URL}/analyze", files=files)
                if response.status_code == 200:
                    task_id = response.json()["task_id"]
                    tasks.append({"task_id": task_id, "filename": uploaded_file.name, "status": "pending"})
                else:
                    st.error(f"❌ {uploaded_file.name} 提交失败！")

        if tasks:
            st.success(f"✅ 成功提交 {len(tasks)} 个任务，AI 正在后台并发处理！")

            # 2. 创建多列布局，每个文件占一列
            cols = st.columns(len(tasks))
            placeholders = [col.empty() for col in cols]

            # 3. 轮询所有任务的状态
            all_done = False
            while not all_done:
                all_done = True
                for i, task in enumerate(tasks):
                    if task["status"] in ["success", "failed"]:
                        continue

                    # 查状态
                    status_res = requests.get(f"{API_URL}/status/{task['task_id']}").json()
                    current_status = status_res.get("status")

                    if current_status == "success":
                        task["status"] = "success"
                        task["result"] = status_res["result"]

                        # 渲染成功结果
                        with placeholders[i].container():
                            st.success(f"🎉 {task['filename']} 完成")
                            data = task["result"]
                            st.metric(f"{data['company_name']} - 行业", data['industry'])
                            growth = data['growth_rate']
                            st.metric("营收同比增长率", f"{growth}%", delta=f"{growth}%",
                                      delta_color="normal" if growth > 0 else "inverse")

                            st.markdown("**投资分析摘要：**")
                            st.info(data['summary'])

                            # 画图
                            chart_data = pd.DataFrame({
                                "财务指标": ["上期营收", "本期营收", "本期净利润"],
                                "金额 (亿元)": [data['revenue_previous'], data['revenue_current'], data['net_profit']]
                            })
                            fig = px.bar(chart_data, x="财务指标", y="金额 (亿元)", text_auto='.2f', color="财务指标")
                            fig.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
                            st.plotly_chart(fig, use_container_width=True)

                    elif current_status == "failed":
                        task["status"] = "failed"
                        with placeholders[i].container():
                            st.error(f"❌ {task['filename']} 处理失败:\n{status_res.get('message')}")
                    else:
                        all_done = False
                        with placeholders[i].container():
                            st.warning(f"⏳ {task['filename']}\n状态: {status_res.get('message')}")

                if not all_done:
                    time.sleep(2)