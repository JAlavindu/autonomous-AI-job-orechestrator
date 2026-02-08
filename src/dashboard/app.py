import streamlit as st
import pandas as pd
import redis
import json
import time
from datetime import datetime

# Connect to Redis directly to fetch data
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

st.set_page_config(page_title="AI Orchestrator Monitor", layout="wide")
st.title("🤖 Autonomous AI Job Orchestrator Dashboard")

# Auto-refresh every 2 seconds
if st.button('Refresh Data'):
    st.rerun()

# 1. Fetch Data
try:
    job_ids = r.smembers("jobs:index")
    jobs = []
    if job_ids:
        raw_data = r.mget([f"job:{jid}" for jid in job_ids])
        jobs = [json.loads(d) for d in raw_data if d]
    
    df = pd.DataFrame(jobs)
except Exception as e:
    st.error(f"Could not connect to Redis: {e}")
    st.stop()

if not df.empty:
    # Convert timestamps
    df['created_at'] = pd.to_datetime(df['created_at'])
    if 'completed_at' in df.columns:
        df['completed_at'] = pd.to_datetime(df['completed_at'])

    # 2. Metrics Row
    col1, col2, col3, col4 = st.columns(4)
    
    pending_count = len(df[df['status'] == 'PENDING'])
    completed_count = len(df[df['status'] == 'COMPLETED'])
    running_count = len(df[df['status'] == 'RUNNING'])
    failed_count = len(df[df['status'] == 'FAILED'])

    col1.metric("Pending Jobs", pending_count)
    col2.metric("Running Jobs", running_count)
    col3.metric("Completed Jobs", completed_count)
    col4.metric("Failed Jobs", failed_count)

    # 3. Active Queue (Detailed View)
    st.subheader("📋 Active Job Queue")
    active_df = df[df['status'].isin(['PENDING', 'RUNNING'])].sort_values(by='priority', ascending=False)
    st.dataframe(active_df[['id', 'name', 'status', 'priority', 'estimated_duration', 'created_at']], use_container_width=True)

    # 4. Success History
    st.subheader("📈 Completed Jobs History")
    completed_df = df[df['status'] == 'COMPLETED'].sort_values(by='completed_at', ascending=False)
    if not completed_df.empty:
        st.dataframe(completed_df[['name', 'priority', 'created_at', 'completed_at']])
else:
    st.info("No jobs found in the system.")

# Footer auto-refresh hint
time.sleep(2)
st.rerun()