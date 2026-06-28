import logging
import os
import random

import numpy as np
import torch
import torch.optim as optim

from src.rl_engine.model import DQN

logger = logging.getLogger(__name__)


class RLAgent:
    def __init__(self, state_dim, action_dim, lr=1e-3, gamma=0.99, epsilon=1.0):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.policy_net = DQN(state_dim, action_dim).to(self.device)
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=lr)
        self.loss_fn = torch.nn.MSELoss()

    def select_action(self, state, valid_actions_count=None):
        if random.random() < self.epsilon:
            if valid_actions_count:
                return random.randint(0, valid_actions_count - 1)
            return random.randint(0, self.action_dim - 1)

        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_values = self.policy_net(state_tensor)

            if valid_actions_count is not None:
                mask = torch.full_like(q_values, float("-inf"))
                mask[0, :valid_actions_count] = 0
                q_values = q_values + mask

            return q_values.argmax().item()

    def train_step(self, state, action, reward, next_state, done):
        state = torch.FloatTensor(state).to(self.device)
        next_state = torch.FloatTensor(next_state).to(self.device)
        action = torch.LongTensor([action]).to(self.device)
        reward = torch.FloatTensor([reward]).to(self.device)
        done = torch.FloatTensor([done]).to(self.device)

        q_values = self.policy_net(state)

        if action.item() >= q_values.shape[0]:
            logger.error(
                "Agent attempted to train on invalid action index %s (max: %s)",
                action.item(),
                q_values.shape[0] - 1,
            )
            return

        q_value = q_values[action]
        next_q_values = self.policy_net(next_state)
        next_q_value = next_q_values.max(0)[0].detach()
        expected_q_value = reward + (self.gamma * next_q_value * (1 - done))

        loss = self.loss_fn(q_value, expected_q_value)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

    def save_model(self, path: str = "model_checkpoint.pth"):
        try:
            torch.save(self.policy_net.state_dict(), path)
            logger.info("AI model saved to %s", path)
        except Exception as e:
            logger.error("Error saving model to %s: %s", path, e)

    def load_model(self, path: str = "model_checkpoint.pth"):
        if os.path.exists(path):
            try:
                self.policy_net.load_state_dict(torch.load(path))
                self.policy_net.eval()
                logger.info("AI model loaded from %s", path)
            except Exception as e:
                logger.error("Error loading model from %s: %s", path, e)
        else:
            logger.info("No checkpoint found at %s; starting with fresh model", path)
