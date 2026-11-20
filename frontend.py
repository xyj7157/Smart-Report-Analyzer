import streamlit as st
import requests
import plotly.express as px
import pandas as pd

# 后端 API 的地址
API_URL = "http://127.0.0.1:8000/analyze"

st.set_page_config(page_title="智能财报分析系统", page_icon="📊", layout="wide")

st.title("📊 智能财报分析系统")
st.markdown(
    "基于 **LangGraph + FastAPI + Streamlit** 构建。上传一份公司财报 PDF，AI 将为您提取核心数据、联网搜索同行对比，并生成专业研报。")

with st.sidebar:
    st.header("⚙️ 操作面板")
    uploaded_file = st.file_uploader("请上传财报 PDF 文件", type=["pdf"])
    analyze_btn = st.button("🚀 开始智能分析", use_container_width=True)
    st.divider()
    st.caption("提示：由于涉及大模型推理与联网搜索，分析可能需要 10-20 秒，请耐心等待。")

if analyze_btn:
    if uploaded_file is None:
        st.warning("⚠️ 请先上传一份 PDF 文件！")
    else:
        with st.spinner('🔍 正在发送至服务器，AI 深度解析中（可能需要十几秒）...'):
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                response = requests.post(API_URL, files=files, timeout=60)

                if response.status_code == 200:
                    data = response.json()

                    st.success("✅ 分析完成！数据已同步存入数据库。")
                    st.divider()

                    # 顶部核心指标卡片
                    st.subheader(f"🏢 {data['company_name']} - 核心指标")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("所属行业", data['industry'])

                    growth = data['growth_rate']
                    delta_color = "normal" if growth > 0 else "inverse"
                    col2.metric("营收同比增长率", f"{growth}%", delta=f"{growth}%", delta_color=delta_color)
                    col3.metric("研报状态", "已生成并入库")

                    st.divider()

                    # ================= 核心改动：Tabs 标签页 =================
                    tab1, tab2 = st.tabs(["📝 投资分析摘要", "📊 财务数据可视化"])

                    with tab1:
                        st.info(data['summary'])

                    with tab2:
                        # 准备画图的数据
                        # 准备画图的数据（加入安全获取，防止 KeyError）
                        chart_data = pd.DataFrame({
                            "财务指标": ["上期营收", "本期营收", "本期净利润"],
                            "金额 (亿元)": [
                                data.get('revenue_previous', 0),
                                data.get('revenue_current', 0),
                                data.get('net_profit', 0)
                            ]
                        })

                        # 用 Plotly 画柱状图
                        fig = px.bar(
                            chart_data,
                            x="财务指标",
                            y="金额 (亿元)",
                            text_auto='.2f',  # 在柱子上自动显示数值，保留两位小数
                            title=f"{data['company_name']} 核心财务数据对比",
                            color="财务指标",
                            color_discrete_sequence=px.colors.qualitative.Pastel  # 用柔和的色彩
                        )
                        # 优化图表样式
                        fig.update_layout(showlegend=False, height=500)

                        # 在网页上渲染图表
                        st.plotly_chart(fig, use_container_width=True)
                    # =======================================================

                else:
                    st.error(f"❌ 后端处理失败，错误码：{response.status_code}")
                    st.json(response.json())

            except requests.exceptions.ConnectionError:
                st.error("❌ 无法连接到服务器！请确保 FastAPI 后端（uvicorn）正在运行。")
            except Exception as e:
                st.error(f"❌ 发生未知错误: {e}")