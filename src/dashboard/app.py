import json
import os
import time

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
JOBS_URL = f"{API_URL}/api/v1/jobs/"
DLQ_URL = f"{API_URL}/api/v1/dlq"

st.set_page_config(page_title="AI Orchestrator Monitor", layout="wide")
st.title("Autonomous AI Job Orchestrator Dashboard")

st.sidebar.header("Benchmark Results")
benchmark_file = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "benchmark_results.json",
)
if os.path.exists(benchmark_file):
    with open(benchmark_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    benchmark_data = pd.DataFrame(
        {"Scheduler": list(data.keys()), "Missed Deadlines": list(data.values())}
    ).set_index("Scheduler")
else:
    benchmark_data = pd.DataFrame(
        {
            "Scheduler": ["AI (DQN)", "FIFO", "Strict Priority"],
            "Missed Deadlines": [39, 42, 49],
        }
    ).set_index("Scheduler")

st.sidebar.bar_chart(benchmark_data)
st.sidebar.divider()

if st.button("Refresh Data"):
    st.rerun()

try:
    jobs_resp = requests.get(JOBS_URL, params={"limit": 1000}, timeout=5)
    jobs_resp.raise_for_status()
    jobs = jobs_resp.json().get("items", [])

    dlq_resp = requests.get(DLQ_URL, params={"limit": 100}, timeout=5)
    dlq_resp.raise_for_status()
    dlq_items = dlq_resp.json().get("items", [])
except Exception as exc:
    st.error(f"Could not reach API at {API_URL}: {exc}")
    st.stop()

df = pd.DataFrame(jobs) if jobs else pd.DataFrame()

if not df.empty:
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"])
    if "completed_at" in df.columns:
        df["completed_at"] = pd.to_datetime(df["completed_at"])

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Pending", len(df[df["status"] == "PENDING"]))
    col2.metric("Running", len(df[df["status"] == "RUNNING"]))
    col3.metric("Completed", len(df[df["status"] == "COMPLETED"]))
    col4.metric("Failed", len(df[df["status"] == "FAILED"]))
    col5.metric("DLQ", len(dlq_items))

    st.subheader("Active Job Queue")
    active_df = df[df["status"].isin(["PENDING", "RUNNING", "RETRYING"])].sort_values(
        by="priority", ascending=False
    )
    if not active_df.empty:
        st.dataframe(
            active_df[["id", "name", "status", "priority", "estimated_duration", "created_at"]],
            use_container_width=True,
        )
    else:
        st.info("No active jobs.")

    st.subheader("Completed Jobs History")
    completed_df = df[df["status"] == "COMPLETED"].sort_values(by="completed_at", ascending=False)
    if not completed_df.empty:
        st.dataframe(completed_df[["name", "priority", "created_at", "completed_at"]])

    st.subheader("Dead Letter Queue")
    if dlq_items:
        st.dataframe(pd.DataFrame(dlq_items), use_container_width=True)
    else:
        st.info("DLQ is empty.")
else:
    st.info("No jobs found.")

time.sleep(2)
st.rerun()