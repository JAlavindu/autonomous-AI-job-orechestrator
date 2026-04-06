# 🤖 Autonomous AI Job Orchestrator

A distributed, self-optimizing system that uses Reinforcement Learning (Deep Q-Network) to schedule and orchestrate jobs based on priority, deadlines, and system load.

![Project Status](https://img.shields.io/badge/status-active-success.svg)
![Python](https://img.shields.io/badge/python-3.10-blue.svg)
![Docker](https://img.shields.io/badge/docker-compose-blue.svg)

## 📋 Overview
This project implements an intelligent job scheduler that outperforms standard FIFO (First-In-First-Out) queues by learning from experience. It uses a **Deep Q-Network (DQN)** to decide which job to pick from the queue to maximize "Rewards" (meeting deadlines, handling high-priority tasks).

### Key Features
*   **🧠 AI-Driven Scheduling**: Replaces static rules with a Neural Network (DQN) that minimizes missed deadlines and effectively mitigates **starvation** for lower priority tasks.
*   **⚡ Distributed Architecture**: Decoupled Scheduler and Worker nodes using Redis Queues. Supports horizontal scaling (just add more workers).
*   **🔗 DAG Support**: Handles complex Directed Acyclic Graph (DAG) dependencies (e.g., Job C waits for Job B, which waits for Job A) preventing race conditions.
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

## 🧪 Testing, Training & Evaluation

We have included scripts to verify different aspects of the system, train the AI, and benchmark performance.

### 1. Pre-training the AI (Offline Learning)
Run the offline training loop for 500 episodes to generate a robust `ai_brain.pth` weights file before starting the cluster.
```bash
python train_model.py
```
*This simulates thousands of tasks so the DQN learns to balance priorities and deadlines, preventing task starvation.*

### 2. Benchmarking the Schedulers (AI vs Baseline)
Evaluate the trained AI against standard FIFO and strict Priority queues over a batch of 100 randomized jobs.
```bash
python benchmark.py
```
*Empirical Results:*
- **FIFO**: 52 Missed Deadlines
- **Strict Priority**: 52 Missed Deadlines (Suffers from **Starvation** of low-priority tasks)
- **AI (DQN)**: 49 Missed Deadlines (Balancing both priority and deadlines optimally)

### 3. Live Workload Simulation
Generates 50 random jobs to flood the live queue while the Docker cluster is running.
```bash
python test_script.py
```
*Observe the Streamlit Dashboard to watch the AI prioritize high-value jobs in real-time.*

### 4. DAG / Dependency Test
Verifies that the orchestrator respects Directed Acyclic Graph (DAG) dependencies (Parent -> Child).
```bash
python test_dag.py
```
*Expected Behavior: Job B will stay 'PENDING - Waiting on dependencies' until Job A completes.*

---

## 🧠 How the AI Works

The system uses Reinforcement Learning (RL) to make decisions.

1.  **Observation (State)**:
    The Scheduler looks at the top 15 pending jobs. For each job, it calculates:
    *   `Priority` (Normalized 0-1)
    *   `Duration` (Normalized)
    *   `Slack Time` (Scaled mathematically over an impending threshold so the Neural Network properly detects urgency)

2.  **Decision (Action)**:
    The **DQN Agent** predicts which index (0-14) has the highest "Q-Value" (Expected future reward).

3.  **Feedback (Reward)**:
    After a job finishes, the environment calculates a reward score:
    *   **+10.0**: Finished before deadline.
    *   **+ (Priority * 0.5)**: High priority bonus.
    *   **-5.0**: Missed deadline or Failed.

4.  **Learning**:
    The agent updates its brain (`ai_brain.pth`) using Backpropagation to minimize the Mean Squared Error (MSE) via the Bellman Equation.

---

## 🚀 Future Improvements

1. **Dynamic Scaling:** Allowing the orchestrator to automatically spin up new Docker worker containers if the pending queue grows too large, instead of manual scaling.
2. **Advanced Job Metrics:** Passing memory, IO, and CPU requirements into the AI's state vector so it can schedule tasks based on physical hardware availability.
3. **Cloud Native Orchestration:** Migrating the infrastructure from simple Docker Compose over to a full Kubernetes deployment for true enterprise-grade high availability.

---

## 📂 Project Structure

```bash
autonomous-ai-job-orchestrator/
├── src/
│   ├── api/            # FastAPI Routes (POST /jobs, GET /status)
│   ├── core/           # Config & Settings
│   ├── dashboard/      # Streamlit UI App
│   ├── db/             # Redis Client & CRUD
│   ├── models/         # Pydantic Data Models (Job, JobDAG)
│   ├── orchestrator/   # Core Logic
│   │   ├── scheduler.py    # The Brain (AI Loop)
│   │   ├── worker.py       # The Muscle (Job Executor)
│   │   └── job_manager.py  # Status & Dependency Manager
│   └── rl_engine/      # AI Magic
│       ├── agent.py        # DQN Agent
│       ├── model.py        # Neural Network Architecture
│       └── environment.py  # State Encoding & Rewards
├── tests/              # Pytest Suite
├── benchmark.py        # Offline Evaluation Script
├── train_model.py      # DQN Training Script
├── docker-compose.yml  # Container Config
├── Dockerfile          # Image Definition
└── requirements.txt    # Python Dependencies
```

## 🛡️ License
MIT License