FROM python:3.12-slim

WORKDIR /app

# Install spike-only Google libraries without expanding the FastAPI image.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The build context is this directory; OAuth files never enter the image.
COPY snx_21_gmail_probe.py .

ENTRYPOINT ["python", "/app/snx_21_gmail_probe.py"]
