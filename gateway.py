"""Service 1 (entry point): gateway - port 5000
What a user/browser talks to. It forwards to order-service.
"""
import logging
import os

import requests
from flask import Flask, jsonify, request

from telemetry import setup_telemetry

app = Flask(__name__)
tracer, meter = setup_telemetry("gateway", app)
log = logging.getLogger("gateway")

ORDER_URL = os.getenv("ORDER_URL", "http://localhost:5001")


@app.get("/checkout")
def checkout():
    item = request.args.get("item", "laptop")
    qty = int(request.args.get("qty", 1))
    log.info("checkout requested item=%s qty=%s", item, qty)

    # The trace STARTS here (FlaskInstrumentor made the root span).
    # This call makes the trace continue into order-service.
    r = requests.post(f"{ORDER_URL}/orders", json={"item": item, "qty": qty}, timeout=5)
    return jsonify(r.json()), r.status_code


@app.get("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
