FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Create data directory for database
RUN mkdir -p /app/data

# Set Python path
ENV PYTHONPATH=/app

# Run the application
CMD ["python", "src/main.py"]
