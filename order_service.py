"""Service 2 (middle): order-service - port 5001
Receives an order, asks inventory-service if stock exists, "charges" the card.
"""
import logging
import os
import random
import time

import requests
from flask import Flask, jsonify, request
from opentelemetry.trace import Status, StatusCode

from telemetry import setup_telemetry

app = Flask(__name__)
tracer, meter = setup_telemetry("order-service", app)
log = logging.getLogger("orders")

INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:5002")

# CUSTOM METRICS - business-level numbers, not just HTTP numbers
orders_counter = meter.create_counter(
    "orders_total", description="Orders processed", unit="1"
)
order_value = meter.create_histogram(
    "order_value_dollars", description="Value of each order", unit="USD"
)

PRICES = {"laptop": 1200.0, "mouse": 25.0, "keyboard": 70.0}


@app.post("/orders")
def create_order():
    body = request.get_json(force=True)
    item, qty = body["item"], int(body.get("qty", 1))
    log.info("received order item=%s qty=%s", item, qty)

    # outgoing HTTP call. RequestsInstrumentor automatically:
    #   - creates a CLIENT span
    #   - adds the `traceparent` header so inventory-service joins THIS trace
    resp = requests.get(f"{INVENTORY_URL}/stock/{item}", timeout=3)
    if resp.status_code != 200:
        orders_counter.add(1, {"item": item, "status": "failed"})
        log.error("inventory check failed status=%s", resp.status_code)
        return jsonify(error="inventory problem", upstream=resp.status_code), 502

    available = resp.json()["quantity"]
    if available < qty:
        orders_counter.add(1, {"item": item, "status": "out_of_stock"})
        log.warning("out of stock item=%s available=%s wanted=%s", item, available, qty)
        return jsonify(error="out of stock"), 409

    # CUSTOM SPAN around business logic
    with tracer.start_as_current_span("payment.charge") as span:
        total = PRICES[item] * qty
        span.set_attribute("payment.amount", total)
        span.set_attribute("payment.currency", "USD")
        time.sleep(random.uniform(0.05, 0.15))
        if random.random() < 0.05:
            err = RuntimeError("card declined")
            span.record_exception(err)
            span.set_status(Status(StatusCode.ERROR, "card declined"))
            orders_counter.add(1, {"item": item, "status": "payment_failed"})
            log.error("payment failed amount=%s", total)
            return jsonify(error="payment failed"), 402

    orders_counter.add(1, {"item": item, "status": "success"})
    order_value.record(total, {"item": item})
    log.info("order complete item=%s total=%s", item, total)
    return jsonify(status="confirmed", item=item, qty=qty, total=total)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
