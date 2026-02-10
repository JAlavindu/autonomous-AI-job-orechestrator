import requests
import random
import time

API_URL = "http://127.0.0.1:8000/api/v1/jobs/"

def create_random_job(i):
    priority = random.randint(1, 10)
    duration = random.randint(1, 5)
    
    payload = {
        "name": f"Training Job {i}",
        "priority": priority,
        "estimated_duration": duration
    }
    
    try:
        requests.post(API_URL, json=payload)
        print(f"Created Job {i} [Priority: {priority}, Duration: {duration}s]")
    except Exception as e:
        print(f"Failed to connect to API: {e}")

if __name__ == "__main__":
    job_count = 50
    print(f"Sending {job_count} jobs to train the AI...")
    for i in range(job_count):
        create_random_job(i)
        # Sleep randomly to allow the scheduler to process and AI to learn
        time.sleep(random.uniform(0.5, 2.0))
