FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (needed for some redis/numpy builds)
RUN apt-get update && apt-get install -y gcc

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install streamlit pandas  # Ensure these are installed

# Copy the rest of the application
COPY . .

# Set python path so imports work correctly
ENV PYTHONPATH=/app

# Default command (will be overridden by docker-compose)
CMD ["python", "src/main.py"]