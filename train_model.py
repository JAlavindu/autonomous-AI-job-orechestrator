import uuid
import random
import time
from datetime import datetime, timedelta

from src.models.job import Job
from src.rl_engine.agent import RLAgent
from src.rl_engine.environment import encode_state, calculate_reward

# Training Hyperparameters
NUM_EPISODES = 50       # Number of full queue clears
JOBS_PER_EPISODE = 100  # Number of jobs per queue

def generate_training_jobs():
    """Generates a randomized batch of jobs for an episode."""
    jobs = []
    now = datetime.utcnow()
    for _ in range(JOBS_PER_EPISODE):
        jobs.append(Job(
            id=str(uuid.uuid4()),
            name=f"TrainJob-{random.randint(1000, 9999)}",
            priority=random.randint(1, 10),
            estimated_duration=random.uniform(0.5, 3.0),
            # Mix of tight and loose deadlines
            deadline=now + timedelta(seconds=random.uniform(1.0, 15.0)),
            status="PENDING",
            created_at=now
        ))
    return jobs

def train():
    print(f"🧠 Starting AI Training for {NUM_EPISODES} episodes...")
    
    state_size = 15
    action_size = 5
    agent = RLAgent(state_size, action_size)
    
    total_rewards = []
    
    for episode in range(1, NUM_EPISODES + 1):
        pending_jobs = generate_training_jobs()
        current_time = datetime.utcnow()
        episode_reward = 0
        
        while pending_jobs:
            # 1. Observe State
            window = pending_jobs[:action_size]
            state = encode_state(window)
            valid_count = len(window)
            
            # 2. Select Action
            action_idx = agent.select_action(state, valid_count)
            
            # Fallback if invalid 
            if action_idx >= valid_count:
                action_idx = 0
                
            selected_job = window[action_idx]
            
            # 3. Simulate Execution
            # Advance time by the duration of the job
            current_time += timedelta(seconds=selected_job.estimated_duration)
            selected_job.completed_at = current_time
            selected_job.status = "COMPLETED"
            
            # 4. Calculate Reward
            reward = calculate_reward(selected_job)
            episode_reward += reward
            
            # 5. Determine Next State
            pending_jobs.remove(selected_job)
            next_window = pending_jobs[:action_size]
            next_state = encode_state(next_window)
            done = len(pending_jobs) == 0
            
            # 6. Train the Neural Network
            agent.train_step(state, action_idx, reward, next_state, done)
            
        total_rewards.append(episode_reward)
        
        # Log progress
        if episode % 10 == 0 or episode == 1:
            avg_reward = sum(total_rewards[-10:]) / min(10, len(total_rewards))
            print(f"Episode {episode}/{NUM_EPISODES} | Avg Reward (last 10): {avg_reward:.2f} | Epsilon (Explore Rate): {agent.epsilon:.3f}")

    # 7. Save the trained brain
    print("\n✅ Training Complete!")
    agent.save_model("ai_brain.pth")
    print("💾 Saved weights to 'ai_brain.pth'. The AI is now ready to benchmark.")

if __name__ == "__main__":
    train()