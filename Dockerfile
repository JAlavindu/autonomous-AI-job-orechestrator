FROM python:3.14-slim-bookworm

WORKDIR /app

# Dependencies install from wheels; no gcc required.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir streamlit==1.41.1 pandas==2.3.3

COPY . .

ENV PYTHONPATH=/app

CMD ["python", "src/main.py"]
