import torch
import torch.optim as optim
import random
import numpy as np
from src.rl_engine.model import DQN

class RLAgent:
    def __init__(self, state_dim, action_dim, lr=1e-3, gamma=0.99, epsilon=1.0):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma  # Discount factor
        self.epsilon = epsilon  # Exploration rate
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Initialize Policy Network
        self.policy_net = DQN(state_dim, action_dim).to(self.device)
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=lr)
        self.loss_fn = torch.nn.MSELoss()

    def select_action(self, state, valid_actions_count=None):
        """
        Selects an action using Epsilon-Greedy strategy with Action Masking.
        valid_actions_count: The number of actual runnable jobs available (e.g., 3).
                             The agent should only pick indices 0, 1, or 2.
        """
        # Explore: pick random action from VALID range only
        if random.random() < self.epsilon:
            if valid_actions_count:
                return random.randint(0, valid_actions_count - 1)
            return random.randint(0, self.action_dim - 1)
        
        # Exploit: pick best action from Neural Net
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_values = self.policy_net(state_tensor)
            
            # Action Masking for Exploit phase
            if valid_actions_count is not None:
                # Set Q-values of invalid actions to negative infinity so they are never picked
                # We create a mask where valid indices are 0 and invalid are -inf
                mask = torch.full_like(q_values, float('-inf'))
                mask[0, :valid_actions_count] = 0
                q_values = q_values + mask
            
            return q_values.argmax().item()

    def train_step(self, state, action, reward, next_state, done):
        """
        Performs a single update step on the Neural Network.
        """
        state = torch.FloatTensor(state).to(self.device)
        next_state = torch.FloatTensor(next_state).to(self.device)
        action = torch.LongTensor([action]).to(self.device)
        reward = torch.FloatTensor([reward]).to(self.device)
        done = torch.FloatTensor([done]).to(self.device)
            

        # 1. Get current Q value
        q_values = self.policy_net(state)
        q_value = q_values.gather(0, action)

        # 2. Get max next Q value
        next_q_values = self.policy_net(next_state)
        next_q_value = next_q_values.max(0)[0].detach()
        
        # 3. Calculate Target Q (Bellman Equation)
        expected_q_value = reward + (self.gamma * next_q_value * (1 - done))

        # 4. Compute Loss & Backpropagate
        loss = self.loss_fn(q_value, expected_q_value)
        
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        # Decay epsilon
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
