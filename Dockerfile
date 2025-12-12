FROM python:3.13-slim-bullseye
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y procps && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app/
RUN pip install -e .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--reload"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD pgrep -f "uvicorn main:app --host 0.0.0.0 --reload" >/dev/null || exit 1
