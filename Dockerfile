FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY cc_team_intel/ cc_team_intel/

RUN pip install --no-cache-dir ".[server]"

ENV CCTI_DATA_DIR=/data

EXPOSE 8000

CMD ["ccti", "serve", "--host", "0.0.0.0", "--port", "8000"]
