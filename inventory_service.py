"""Service 3 (leaf): inventory-service  - port 5002
Pretends to be a database-backed stock checker. Has deliberate slowness and
failures so you have something interesting to find in traces.
"""
import logging
import random
import time

from flask import Flask, jsonify
from opentelemetry.trace import Status, StatusCode

from telemetry import setup_telemetry

app = Flask(__name__)
tracer, meter = setup_telemetry("inventory-service", app)
log = logging.getLogger("inventory")

STOCK = {"laptop": 5, "mouse": 50, "keyboard": 0}  # keyboard is always out of stock

# CUSTOM METRIC: a counter we increment ourselves
stock_checks = meter.create_counter(
    "inventory_checks_total", description="Number of stock lookups", unit="1"
)


@app.get("/stock/<item>")
def check_stock(item):
    # CUSTOM SPAN: wraps just the "database" part so we can see its duration
    with tracer.start_as_current_span("db.query_stock") as span:
        span.set_attribute("db.system", "fake-postgres")
        span.set_attribute("inventory.item", item)

        # simulate DB latency; "mouse" is occasionally very slow
        delay = random.uniform(0.02, 0.08)
        if item == "mouse" and random.random() < 0.3:
            delay = random.uniform(0.8, 1.2)
            log.warning("slow query detected for item=%s", item)
        time.sleep(delay)

        # simulate a random infrastructure failure (10%)
        if random.random() < 0.10:
            err = RuntimeError("database connection reset")
            span.record_exception(err)                       # stores stack trace on span
            span.set_status(Status(StatusCode.ERROR, str(err)))
            stock_checks.add(1, {"item": item, "result": "error"})
            log.error("db failure for item=%s", item)
            return jsonify(error="db unavailable"), 500

        qty = STOCK.get(item)
        if qty is None:
            stock_checks.add(1, {"item": item, "result": "unknown_item"})
            return jsonify(error="unknown item"), 404

        span.set_attribute("inventory.quantity", qty)
        stock_checks.add(1, {"item": item, "result": "ok"})
        log.info("stock lookup item=%s qty=%s", item, qty)
        return jsonify(item=item, quantity=qty)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
