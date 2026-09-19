FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Taipei
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

# 相依先裝（含 chromium 及其系統函式庫），之後改程式碼不會重裝
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY . /app
RUN mkdir -p /app/results && chmod -R 0777 /app/results

CMD ["python", "main.py"]
