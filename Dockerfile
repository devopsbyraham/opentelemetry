FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY telemetry.py gateway.py order_service.py inventory_service.py ./
# which service to run is chosen in docker-compose.yml via `command:`
