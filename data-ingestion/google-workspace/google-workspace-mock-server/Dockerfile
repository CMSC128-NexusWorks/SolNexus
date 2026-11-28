# Mock Google server (SNX-69): fake Gmail and Calendar APIs with synthetic data. Local, CI and dev only.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
# Dependencies first, so code changes do not reinstall them.
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY *.py ./

# Run as an unprivileged user: the mock needs no root access.
RUN useradd --create-home --uid 10001 mock && chown -R mock:mock /app
USER mock

EXPOSE 8090
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/_mock/health', timeout=2)"

# --factory: settings are validated inside the factory, so a bad config exits before the port opens.
CMD ["uvicorn", "--factory", "mock_app:build_mock_google_app_from_environment", "--host", "0.0.0.0", "--port", "8090"]
