# 🎤 Project Presentation Script: Autonomous AI Job Orchestrator

**Presenters:** J. A. L. Perera & A. A. Lokuliyana  
**Estimated Time:** 10-15 Minutes

---

## 1. Introduction (2 mins)
**[Slide/Screen: Show Title Page or GitHub README]**
* **Speaker 1:** "Welcome and thank you for taking the time to review our final year project. We built the *Autonomous AI Job Orchestrator*, a self-optimizing engine that uses Reinforcement Learning to schedule and process complex, distributed workloads."
* **Speaker 2:** "Modern schedulers usually rely on static rules, like First-In-First-Out (FIFO) or rigid Priority queues. However, these systems fail to adapt under heavy load—leading to high latency and missed deadlines. Our core objective was to replace these static rules with an AI brain—specifically a Deep Q-Network—that actively learns to balance priorities and deadlines simultaneously."
* **Speaker 1:** "To briefly explain, a **Deep Q-Network (DQN)** is a type of machine learning called Reinforcement Learning. Instead of hardcoding 'if-then' scheduling rules, the AI observes the environment (like job priorities and time until deadlines) and takes an action. It earns mathematical 'rewards' for meeting deadlines and 'penalties' for missing them. Over time, its neural network learns to predict the best sequence of decisions to maximize its total score."

---

## 2. Showcasing the Benchmark & AI Math (3 mins)
**[Screen: Open VS Code terminal]**
* **Action:** Run `python benchmark.py`
* **Speaker 1:** "Before diving into the visual platform, we want to prove the underlying math works. We built an offline evaluation script that tests 100 randomly generated jobs—with varying durations and deadlines—against three distinct schedulers: FIFO, strict Priority, and our trained AI."
* **Speaker 1:** *(Highlight the terminal output)* "As you can see, FIFO misses 42 deadlines. The absolute Priority queue does great on high-priority tasks, but it causes **'starvation'** for everything else. Starvation happens in rigid priority systems when new, high-priority jobs continually jump to the front of the queue, pushing low-priority tasks indefinitely to the back until their deadlines expire. This makes pure Priority the worst overall with 49 missed deadlines. Our AI, however, achieves the lowest overall missed deadline rate (39/100) because it learns the exact mathematical trade-off needed to prevent starvation while still honoring the most urgent deadlines."

---

## 3. Architecture & Booting the Cluster (2 mins)
**[Screen: Show `docker-compose.yml` briefly, then run the boot command]**
* **Action:** Run `docker-compose up --build -d`
* **Speaker 2:** "To make this system enterprise-ready, we designed a distributed, decoupled architecture. Using Docker Compose, we are spinning up four microservices right now:"
    1. A **Redis** message broker and state store.
    2. A **FastAPI** backend that houses our Scheduler Brain.
    3. An asynchronous **Worker** node that actually executes the physical tasks.
    4. A **Streamlit Dashboard** for real-time observability.
* **Action:** Run `docker-compose up -d --scale worker=2`
* **Speaker 2:** "Because the workers and scheduler are cleanly decoupled via Redis, we can effortlessly scale worker nodes horizontally on the fly—as we just did by spinning up a second worker."

---

## 4. Live Workload Simulation (3 mins)
**[Screen: Split screen. Left side = Terminal, Right side = Dashboard at `http://localhost:8501`]**
* **Action:** Run `python test_script.py` in the terminal.
* **Speaker 1:** "We are now firing 50 concurrent API requests into our job submission endpoint. If we look at our live Streamlit Dashboard..."
* *(Point at the active queue updating on the dashboard).*
* **Speaker 1:** "...you will see the system is alive. The AI actively scans the Pending jobs. It observes the system state—Priority, Duration, and Slack Time—and continuously extracts top jobs to the Redis 'Work Queue'. Notice how it intelligently interweaves high-priority jobs with quick, low-priority tasks to maximize success rates."

---

## 5. DAG Dependency Demonstration (2 mins)
**[Screen: Keep Dashboard open, clear terminal]**
* **Action:** Run `python test_dag.py`
* **Speaker 2:** "Beyond simple independent tasks, complex software infrastructure requires task dependencies. So, we successfully implemented Directed Acyclic Graph (DAG) logic."
* **Speaker 1:** "A **Directed Acyclic Graph (DAG)** is a topological map where execution flows in a specific direction without ever looping back on itself. In our project, it dictates the job execution order to prevent execution race conditions."
* **Speaker 2:** "Our script just submitted Job A and Job B. Job B formally depends on Job A. As you can see on the dashboard, even if Job B is picked by the logic, the Orchestrator forces it into a `PENDING - Waiting on dependencies` state until Job A reaches `COMPLETED`. This guarantees data integrity in distributed environments natively."

---

## 6. Self-Healing (1 min)
**[Screen: Switch to `scheduler.py` or API Code showing the zombie killer]**
* **Speaker 1:** "Finally, to guarantee resilience, we implemented a 'Zombie Killer' loop state. If a distributed worker theoretically crashes mid-task, the scheduler automatically times out the job via its `started_at` timestamp, marking it as FAILED, ensuring our system never deadlocks."

---

## 7. Future Improvements & Wrap-up (2 mins)
* **Speaker 1:** "Looking ahead, there are several exciting paths for **Future Improvements** on this architecture:
    1. **Dynamic Scaling:** Allowing the orchestrator to automatically spin up new Docker worker containers if the pending queue grows too large, instead of manual scaling.
    2. **Advanced Job Metrics:** Passing memory, IO, and CPU requirements into the AI's state vector so it can schedule tasks based on physical hardware availability.
    3. **Cloud Native Orchestration:** Migrating the infrastructure from simple Docker Compose over to a full Kubernetes deployment for true enterprise-grade high availability."
* **Speaker 2:** "To summarize: We successfully delivered all initial requirements and objectives. We built a fully containerized, DAG-capable, Redis-backed orchestration system where Deep Reinforcement Learning effectively outlasts and outperforms standard static industry baselines. Thank you. We are happy to take any questions."
* **Action:** Run `docker-compose down` 
