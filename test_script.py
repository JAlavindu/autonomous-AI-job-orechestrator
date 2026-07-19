import os
import random
import time

import requests

API_URL = "http://127.0.0.1:8000/api/v1/jobs/"
API_KEY = os.environ.get("ORCHESTRATOR_API_KEY", "ork_dev_operator_replace_me")
HEADERS = {"X-API-Key": API_KEY}


def create_random_job(i):
    priority = random.randint(1, 10)
    duration = random.randint(1, 5)

    payload = {
        "name": f"Training Job {i}",
        "priority": priority,
        "estimated_duration": duration,
        "payload": {"type": "sleep"},
    }

    try:
        resp = requests.post(API_URL, json=payload, headers=HEADERS)
        if resp.status_code == 201:
            print(f"Created Job {i} [Priority: {priority}, Duration: {duration}s]")
        else:
            print(f"Job {i} REJECTED: HTTP {resp.status_code} {resp.text[:120]}")
    except Exception as e:
        print(f"Failed to connect to API: {e}")


if __name__ == "__main__":
    job_count = 50
    print(f"Sending {job_count} jobs...")
    for i in range(job_count):
        create_random_job(i)
        time.sleep(random.uniform(0.05, 0.2))
