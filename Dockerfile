FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

# Copy configuration
COPY pyproject.toml poetry.lock* ./

# Turn off virtual env creation for Docker
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-interaction --no-ansi --no-root

# Copy source code
COPY . .

# Streamlit dashboard
EXPOSE 8505
CMD ["streamlit", "run", "src/interfaces/dashboard/app.py", "--server.port=8505", "--server.address=0.0.0.0"]
