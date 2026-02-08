import requests
import time
import json

API_URL = "http://127.0.0.1:8000/api/v1/jobs/"

def create_job(name, priority, duration, depends_on=None):
    payload = {
        "name": name,
        "priority": priority,
        "estimated_duration": duration,
        "dependencies": depends_on or []
    }
    try:
        response = requests.post(API_URL, json=payload)
        response.raise_for_status()
        job_id = response.json()['id']
        print(f"[+] Created '{name}' (ID: {job_id})")
        if depends_on:
            print(f"    -> Depends on: {depends_on}")
        return job_id
    except Exception as e:
        print(f"[-] Error creating job {name}: {e}")
        return None

if __name__ == "__main__":
    print("=== DAG Workflow Test ===")
    print("Scenario: Job A (Root) -> Job B (Child) -> Job C (Grandchild)")
    print("Expectation: B waits for A, C waits for B.")
    print("-------------------------------------------------------------")
    
    # 1. Create Job A (The Parent) - Takes 5 seconds to run
    id_a = create_job("Job A (Root)", 10, 5)
    
    if id_a:
        # 2. Create Job B (Dependent on A)
        id_b = create_job("Job B (Child)", 8, 3, depends_on=[id_a])
        
        if id_b:
            # 3. Create Job C (Dependent on B)
            id_c = create_job("Job C (Grandchild)", 5, 3, depends_on=[id_b])
            
    print("\nCheck your dashboard/logs to verify execution order!")
