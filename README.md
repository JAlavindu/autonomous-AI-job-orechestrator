# 🤖 Autonomous AI Job Orchestrator

A distributed, self-optimizing system that uses Reinforcement Learning (Deep Q-Network) to schedule and orchestrate jobs based on priority, deadlines, and system load.

![Project Status](https://img.shields.io/badge/status-active-success.svg)
![Python](https://img.shields.io/badge/python-3.10-blue.svg)
![Docker](https://img.shields.io/badge/docker-compose-blue.svg)

## 📋 Overview
This project implements an intelligent job scheduler that outperforms standard FIFO (First-In-First-Out) queues by learning from experience. It uses a **Deep Q-Network (DQN)** to decide which job to pick from the queue to maximize "Rewards" (meeting deadlines, handling high-priority tasks).

### Key Features
*   **🧠 AI-Driven Scheduling**: Replaces static rules with a Neural Network that optimizes for long-term efficiency.
*   **⚡ Distributed Architecture**: Decoupled Scheduler and Worker nodes using Redis Queues. Supports horizontal scaling (just add more workers).
*   **🔗 DAG Support**: Handles complex dependency graphs (e.g., Job C waits for Job B, which waits for Job A).
*   **🧟 Self-Healing**: Automatically detects and terminates "Zombie" jobs that exceed execution timeouts.
*   **📊 Real-time Dashboard**: Streamlit UI to visualize queues, job status, and success rates.

---

## 🛠️ Tech Stack

| Component | Technology | Description |
|-----------|------------|-------------|
| **Core** | Python 3.10 | Main programming language |
| **API** | FastAPI | High-performance REST API |
| **AI Engine** | PyTorch | Deep Q-Network (DQN) implementation |
| **Database** | Redis | In-memory store for Jobs and Queues |
| **UI** | Streamlit | Real-time monitoring dashboard |
| **DevOps** | Docker | Containerization & Orchestration |

---

## 🚀 Quick Start Guide

### Prerequisites
*   Docker & Docker Compose installed
*   *(Optional)* Python 3.10+ for local development

### Method 1: Run with Docker (Recommended)
This spins up the entire cluster: API, Database, Dashboard, and Workers.

1.  **Build and Start**:
    ```bash
    docker-compose up --build
    ```
    *This creates 4 containers: `api`, `redis`, `dashboard`, `worker`.*

2.  **Scale Workers (Optional)**:
    Want to process jobs faster? Add more workers instantly:
    ```bash
    docker-compose up -d --scale worker=3
    ```

3.  **Access Interfaces**:
    *   **API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
    *   **Dashboard**: [http://localhost:8501](http://localhost:8501)

### Method 2: Manual Setup (Local Dev)
1.  **Start Redis**:
    ```bash
    docker run -d -p 6379:6379 redis:7-alpine
    ```
2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run Components in Separate Terminals**:
    *   **API/Scheduler**: `uvicorn src.main:app --reload`
    *   **Worker**: `python src/orchestrator/worker.py`
    *   **Dashboard**: `streamlit run src/dashboard/app.py`

---

## 🧪 Testing & Verification

We have included scripts to verify different aspects of the system.

### 1. Load Testing (Train the AI)
Generates 50 random jobs to flood the queue and train the Neural Network.
```bash
python test_script.py
```
*Observe the Dashboard to watch the AI prioritize high-value jobs.*

### 2. DAG / Dependency Test
Verifies that the orchestrator respects dependencies (Parent -> Child).
```bash
python test_dag.py
```
*Expected Behavior: Job B will stay 'PENDING' until Job A completes.*

### 3. Unit Tests
Run the automated test suite to verify API and DB logic.
```bash
pytest
```

---

## 🧠 How the AI Works

The system uses Reinforcement Learning (RL) to make decisions.

1.  **Observation (State)**:
    The Scheduler looks at the top 5 pending jobs. For each job, it calculates:
    *   `Priority` (Normalized 0-1)
    *   `Duration` (Normalized)
    *   `Slack Time` (Time until deadline)

2.  **Decision (Action)**:
    The **DQN Agent** predicts which index (0-4) has the highest "Q-Value" (Expected future reward).

3.  **Feedback (Reward)**:
    After a job finishes, the environment calculates a reward score:
    *   **+10.0**: Finished before deadline.
    *   **+ (Priority * 0.5)**: High priority bonus.
    *   **-5.0**: Missed deadline or Failed.

4.  **Learning**:
    The agent updates its brain (`ai_brain.pth`) using Backpropagation to minimize the error in its predictions.

---

## 📂 Project Structure

```bash
autonomous-ai-job-orchestrator/
├── src/
│   ├── api/            # FastAPI Routes (POST /jobs, GET /status)
│   ├── core/           # Config & Settings
│   ├── dashboard/      # Streamlit UI App
│   ├── db/             # Redis Client & CRUD
│   ├── models/         # Pydantic Data Models (Job, JobStatus)
│   ├── orchestrator/   # Core Logic
│   │   ├── scheduler.py    # The Brain (AI Loop)
│   │   ├── worker.py       # The Muscle (Job Executor)
│   │   └── job_manager.py  # Status & Dependency Manager
│   └── rl_engine/      # AI Magic
│       ├── agent.py        # DQN Agent
│       ├── model.py        # Neural Network Architecture
│       └── environment.py  # State Encoding & Rewards
├── tests/              # Pytest Suite
├── docker-compose.yml  # Container Config
├── Dockerfile          # Image Definition
└── requirements.txt    # Python Dependencies
```

## 🛡️ License
MIT License