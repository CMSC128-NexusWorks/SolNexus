FROM python:3.12-slim

WORKDIR /app

# Production builds leave INSTALL_DEV unset, so pytest and its HTTP client stay out of the image.
ARG INSTALL_DEV=false
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt     && if [ "$INSTALL_DEV" = "true" ]; then pip install --no-cache-dir -r requirements-dev.txt; fi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
