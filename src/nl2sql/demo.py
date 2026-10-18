"""Streamlit 仅负责展示，查询通过 FastAPI 的同一安全路径。"""

import os

import httpx
import pandas as pd
import streamlit as st

st.set_page_config(page_title="NL2SQL 数据问答", page_icon="🔎", layout="wide")
API = os.getenv("NL2SQL_API_URL", "http://127.0.0.1:8000")
MODES = {
    "基线 · 一次生成": "baseline",
    "选表选列": "v1_schema_link",
    "选表选列 + 校验修复": "v2_repair",
    "选表选列 + 修复 + 示例检索": "v3_retrieval",
}
st.title("用一句话，查询数据库")
st.caption("个人项目 · 基于 Spider 公开数据集评测 · 本地只读演示")

try:
    response = httpx.get(API + "/databases", timeout=10)
    response.raise_for_status()
    databases = response.json()
except (httpx.HTTPError, ValueError):
    st.error("还没有连接到服务。请双击项目中的「启动演示.command」，或按 README 启动 FastAPI。")
    st.stop()

with st.sidebar:
    st.header("查询设置")
    db_id = st.selectbox(
        "数据库",
        databases,
        index=databases.index("concert_singer") if "concert_singer" in databases else 0,
    )
    label = st.selectbox("运行方式", list(MODES), index=3)
    limit = st.number_input("最多展示行数", min_value=1, max_value=1000, value=100)
    st.caption("每次查询会调用配置的模型接口。模型开销会显示在结果中。")
    with st.expander("查看数据库结构"):
        schema_response = httpx.get(API + f"/schema/{db_id}", timeout=10)
        if schema_response.status_code == 200:
            for table, info in schema_response.json().items():
                st.markdown(f"**{table}**")
                st.code(", ".join(info["columns"]), language=None)

with st.form("question"):
    question = st.text_area("你想了解什么？", "按年龄从大到小列出歌手姓名和年龄。", height=100)
    submitted = st.form_submit_button("查询数据库", type="primary", use_container_width=True)

if submitted:
    with st.spinner("正在生成、检查并执行 SQL…"):
        try:
            response = httpx.post(
                API + "/ask",
                json={
                    "db_id": db_id,
                    "question": question,
                    "mode": MODES[label],
                    "row_limit": limit,
                },
                timeout=420,
            )
            response.raise_for_status()
            st.session_state["answer"] = response.json()
        except httpx.HTTPError as error:
            st.error(f"查询请求失败：{type(error).__name__}。请检查服务日志和接口配置。")
            st.session_state.pop("answer", None)

if "answer" in st.session_state:
    answer = st.session_state["answer"]
    st.subheader("生成的 SQL")
    st.code(answer["sql"] or "未生成可执行 SQL", language="sql")
    if answer["error"]:
        st.error(answer["error"])
    else:
        st.subheader("查询结果")
        if answer["rows"]:
            labels = [
                f"{name} ({i + 1})" if answer["columns"].count(name) > 1 else name
                for i, name in enumerate(answer["columns"])
            ]
            st.dataframe(
                pd.DataFrame(answer["rows"], columns=labels),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("查询执行成功，没有匹配的记录。")
    st.caption(
        f"耗时 {answer['latency_seconds']:.2f} 秒 · "
        f"模型调用 {answer['usage']['calls']} 次 · "
        f"已报告 token {answer['usage']['reported_tokens']} · "
        f"展示上限 {answer['row_limit']} 行"
    )
    if not answer["usage"]["complete"]:
        st.warning("部分请求没有返回 token 用量，以上并非完整计费用量。")
    with st.expander("查看执行过程"):
        for event in answer["trace"]:
            st.markdown(f"**{event['node']}**")
            st.json(event)

st.divider()
st.caption("展示行数受限；正式评测比较完整结果。准确率与安全测试记录见项目 README。")
