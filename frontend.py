import json
import requests
import streamlit as st
import pandas as pd
import plotly.express as px

import os
# 如果环境变量里没有，默认用 localhost:8000（方便本地调试）
API_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000/analyze")

st.set_page_config(page_title="智能财报分析系统", page_icon="📊", layout="wide")
st.title("📊 智能财报分析系统 (全栈版)")
st.markdown(
    "基于 **LangGraph + FastAPI + Streamlit** 构建。上传一份公司财报 PDF，AI 将为您提取核心数据、联网搜索同行对比，并生成专业研报。")

with st.sidebar:
    st.header("⚙️ 操作面板")
    uploaded_file = st.file_uploader("请上传财报 PDF 文件", type=["pdf"])
    analyze_btn = st.button("🚀 开始智能分析", use_container_width=True)

if analyze_btn:
    if uploaded_file is None:
        st.warning("⚠️ 请先上传一份 PDF 文件！")
    else:
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}

        # 使用 stream=True 保持长连接
        response = requests.post(API_URL, files=files, stream=True)

        if response.status_code == 200:
            st.success("✅ 解析成功，AI 正在深度推理中...")
            st.divider()

            st.subheader("📝 投资分析摘要")
            text_placeholder = st.empty()  # 创建一个占位符，用于动态更新文字

            full_text = ""
            metadata = {}

            # 逐行读取后端发来的流式数据
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        try:
                            data = json.loads(line_str[6:])

                            # 接收到文字，拼接到前面，并刷新前端
                            if data['type'] == 'text':
                                full_text += data['content']
                                text_placeholder.markdown(full_text)

                            # 接收到元数据，保存下来准备画图
                            elif data['type'] == 'metadata':
                                metadata = data['data']

                            elif data['type'] == 'error':
                                st.error(f"❌ 分析失败: {data['message']}")
                        except json.JSONDecodeError:
                            continue

            # 分析全部完成后，渲染下方的数据图表
            if metadata:
                st.divider()
                st.subheader(f"🏢 {metadata.get('company_name', '未知')} - 核心指标")
                col1, col2, col3 = st.columns(3)
                col1.metric("所属行业", metadata.get('industry', ''))

                growth = metadata.get('growth_rate', 0)
                col2.metric("营收同比增长率", f"{growth}%", delta=f"{growth}%",
                            delta_color="normal" if growth > 0 else "inverse")
                col3.metric("研报状态", "已生成并入库")

                # 画图表
                chart_data = pd.DataFrame({
                    "财务指标": ["上期营收", "本期营收", "本期净利润"],
                    "金额 (亿元)": [metadata.get('revenue_previous', 0), metadata.get('revenue_current', 0),
                                    metadata.get('net_profit', 0)]
                })
                fig = px.bar(chart_data, x="财务指标", y="金额 (亿元)", text_auto='.2f', color="财务指标")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.error(f"❌ 后端处理失败，错误码：{response.status_code}")