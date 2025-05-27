FROM python:3.6-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y build-essential libpq-dev

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the HPE Private Root CA and Intermediate CA for the Python modules
COPY HPEPrivRootCA.crt .
RUN cat HPEPrivRootCA.crt >> /usr/local/lib/python3.6/site-packages/certifi/cacert.pem

# Copy app code
COPY . .

# Default command (use overridden in docker-compose)
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "--workers", "4"]
