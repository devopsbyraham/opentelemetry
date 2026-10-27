# OpenTelemetry in 30 Minutes — Hands-On (Zero to Interview-Ready)

You will run a tiny shop made of 3 Python services, watch one request travel through all of them, and learn every OpenTelemetry (OTel) concept by touching it.

```
 you ──► gateway:5000 ──► order-service:5001 ──► inventory-service:5002
              │                  │                      │
              └──────────────────┴──── OTLP ────────────┘
                                  ▼
                        OpenTelemetry Collector :4317
                          │                  │
                       traces             metrics
                          ▼                  ▼
                    Jaeger :16686      Prometheus :9090
```

---

## The problem OTel solves

A user says "checkout is slow". The request touched 3 services. Which one is slow? Why?

**Observability** = being able to answer *"what is happening inside my system?"* from the outside, using the data it emits. That data has 3 types (the **three pillars / signals**):

| Signal | Question it answers | Example in this project |
|---|---|---|
| **Traces** | *Where* did this one request spend time / fail? | gateway → order → inventory, with timings |
| **Metrics** | *How much / how often* overall? | `orders_total`, `order_value_dollars` |
| **Logs** | *What exactly happened* at a moment? | `payment failed amount=1200` |

**OpenTelemetry** = a free, vendor-neutral standard (a CNCF project) for *generating and shipping* these signals: APIs, SDKs, auto-instrumentation libraries, a wire protocol (OTLP) and the Collector. It is **not** a backend: it does not store or display anything. Jaeger/Prometheus/Grafana/Datadog/etc. do that.

> Interview one-liner: *"OTel is the vendor-neutral way to instrument apps and ship telemetry; backends are pluggable, so I can switch from Jaeger to Datadog without touching app code."*

---

##  The vocabulary (learn these, they are the interview)

- **Span** – one unit of work with a name, start time, duration, status, and attributes. E.g. `GET /checkout`, `db.query_stock`.
- **Trace** – a tree of spans sharing one **trace_id**. One user request = one trace.
- **Parent/child** – each span stores its parent's span_id; that builds the tree.
- **Attributes** – key/value tags on a span (`payment.amount=1200`). Add business context here.
- **Events / exceptions** – timestamped notes on a span (`span.record_exception(err)`).
- **Status** – OK / ERROR. Mark failed spans ERROR so you can filter them.
- **Resource** – attributes about *who emitted* the data (`service.name`, version, environment). Most important: `service.name`.
- **Context propagation** – how the trace continues across a network call: the caller puts a `traceparent` HTTP header (W3C Trace Context standard) containing trace_id + parent span_id; the callee reads it and creates child spans. **This is the magic that makes distributed tracing work.** Format: `00-<trace_id>-<span_id>-<flags>`.
- **Instrumentation** – code that creates telemetry. *Auto* (libraries patch Flask/requests for you) vs *manual* (you write `start_as_current_span`).
- **SDK vs API** – API = interfaces your code calls (stable). SDK = the implementation that processes/exports. Libraries depend only on the API.
- **Exporter** – sends data somewhere (console, OTLP, Jaeger…).
- **OTLP** – OpenTelemetry Protocol, the native wire format (gRPC on **4317**, HTTP on **4318**).
- **Collector** – a standalone service: **receivers → processors → exporters**. Apps send to it; it fans out to backends.
- **Sampling** – keeping only a % of traces to control cost (head-based = decide at start; tail-based = decide after seeing the whole trace, done in the Collector).

---

##  Read the code (in this order)

### 1. `telemetry.py` — the heart (≈75 lines)
Follow the numbered comments 1→6:
1. **Resource** – names the service.
2. **Exporters** – OTLP to the collector (or console if `OTEL_EXPORTER=console`).
3. **TracerProvider + BatchSpanProcessor** – spans are batched and exported in the background so your request path isn't slowed.
4. **MeterProvider + PeriodicExportingMetricReader** – metrics pushed every 5 s.
5. **LoggingInstrumentor** – injects `trace_id`/`span_id` into every log line. This is how you jump from a trace to its logs.
6. **FlaskInstrumentor + RequestsInstrumentor** – the *auto-instrumentation*. Every incoming request → SERVER span. Every `requests.get/post` → CLIENT span **plus** the `traceparent` header injected.

### 2. `gateway.py`
Zero tracing code in the endpoint. The root span exists purely because of `FlaskInstrumentor`. The `requests.post(...)` carries the trace onward.

### 3. `order_service.py`
Shows **manual** instrumentation:
- `tracer.start_as_current_span("payment.charge")` – custom child span with attributes.
- `span.record_exception(err)` + `set_status(ERROR)` – proper error recording.
- `meter.create_counter("orders_total")` and `create_histogram("order_value_dollars")` – **business metrics** with labels (`item`, `status`).

### 4. `inventory_service.py`
The leaf. Has built-in problems to hunt for: `mouse` is slow ~30% of the time, `keyboard` is out of stock, `ghost` is unknown, and 10% of calls fail randomly.

### 5. `otel-collector-config.yaml`
Read it top to bottom: `receivers` (otlp) → `processors` (memory_limiter, add `team` attribute, batch) → `exporters` (Jaeger for traces, Prometheus endpoint for metrics, debug). The `service.pipelines` section wires them. **Nothing runs unless it appears in a pipeline.**

---

##  Run it and investigate like a DevOps engineer

```bash
docker-compose up --build -d
python loadgen.py 100        # needs `pip install requests`, or use curl in a loop
```

Single request test:
```bash
curl "localhost:5000/checkout?item=laptop"
```

### Exercise A — see one request across 3 services (Jaeger)
1. Open **http://localhost:16686** → Service: `gateway` → *Find Traces*.
2. Open any trace. You'll see a waterfall: `GET /checkout` → `POST` → `POST /orders` → `GET` → `GET /stock/<item>` → `db.query_stock`, plus `payment.charge`.
3. Click a span → see **Tags** (attributes) and **Process** (the Resource: service.name).
**Learn:** one trace_id, 3 services, parent/child tree = context propagation working.

### Exercise B — find the slow requests
1. In Jaeger, Service `gateway`, set **Min Duration = 800ms**.
2. Open a result: the long bar is `db.query_stock`, with `inventory.item=mouse`.
**Learn:** *traces tell you which service and which operation is slow.* Metrics only would have told you "p99 is high" with no idea where.

### Exercise C — find errors
1. In Jaeger, Tags: `error=true`.
2. Open a trace: the red span shows an exception event with the stack trace (`database connection reset` or `card declined`).
3. Notice the gateway span may be red too: errors bubble up the tree.

### Exercise D — metrics (Prometheus)
Open **http://localhost:9090** → Graph. Try:
```promql
sum by (status) (rate(orders_total[1m]))                 # orders/sec by outcome
sum(rate(orders_total{status="success"}[1m])) / sum(rate(orders_total[1m]))   # success ratio
histogram_quantile(0.95, sum by (le) (rate(order_value_dollars_bucket[5m])))  # p95 order value
sum by (result) (rate(inventory_checks_total[1m]))       # inventory outcomes
```
(Metric names can show a `_total` suffix or unit suffix depending on the Collector version; type `orders` in the box to see exact names.)
**Learn:** *metrics tell you how big the problem is and whether it's getting worse*, cheaply, and are what you alert on.

### Exercise E — logs ↔ traces
```bash
docker-compose logs order-service | tail -20
```
Each line contains `trace_id=...`. Copy one, paste into the Jaeger search box → you land on the exact trace for that log line.
**Learn:** correlation is what turns three separate data streams into one story.

### Exercise F — prove the Collector's value
```bash
docker compose stop jaeger
curl "localhost:5000/checkout?item=laptop"      # app still works!
docker-compose start jaeger
```
Your apps never talk to Jaeger directly. Want to switch backends? Edit only the Collector config. **That is the architecture argument interviewers want.**

### Exercise G — no Docker? Console mode
```bash
pip install -r requirements.txt
export OTEL_EXPORTER=console
python inventory_service.py &  python order_service.py &  python gateway.py &
curl "localhost:5000/checkout?item=laptop"
```
You'll see raw spans printed as JSON. Match `trace_id` across the three terminals and see `parent_id` linking spans. (Tested: the same trace_id appeared in all three services.)

---

## Minute 26–30: How real-time observability works in production

**The workflow for an incident:**
1. **Alert fires** from a *metric* (error ratio > 2% for 5 min, p95 latency > 1s). Metrics are cheap and fast.
2. **Dashboard** (Grafana) shows which service/endpoint changed.
3. **Traces** show the exact slow/failing operation across services.
4. **Logs** (via trace_id) give the precise error message.
5. Fix, then add an alert or better attribute so you catch it sooner next time.

**Production architecture used by real teams**
- Apps → **Collector agent** (sidecar/DaemonSet on each node) → **Collector gateway** (central) → backends (Tempo/Jaeger, Prometheus/Mimir, Loki, or a SaaS).
- Use the Collector for: batching, retries, **sampling**, dropping sensitive attributes, adding `k8s.*` metadata, routing to multiple backends.
- Set **service.name, version, environment** on everything. Without them, data is useless.
- Beware **high-cardinality** metric labels (user_id, request_id): they explode Prometheus memory. Put those on *spans*, not metrics.
- Sample traces in high-traffic systems (e.g. keep 10%, but 100% of errors/slow via tail sampling).

---

## Interview Q&A (say these in your own words)

**1. What is OpenTelemetry?** Vendor-neutral CNCF standard: APIs, SDKs, instrumentation, OTLP and Collector for generating and exporting traces, metrics, logs. It does not store or visualize data.

**2. Monitoring vs observability?** Monitoring watches known failure conditions (dashboards/alerts you defined). Observability lets you ask *new* questions about unknown problems from rich telemetry.

**3. Three signals and when to use each?** Metrics to detect (alert), traces to locate (which service/span), logs to explain (exact error).

**4. How does a trace follow a request across services?** Context propagation: caller injects W3C `traceparent` header (trace_id + parent span_id); callee extracts it and creates child spans with the same trace_id.

**5. What is the Collector and why use it?** A proxy pipeline (receivers → processors → exporters). Decouples apps from backends; centralizes batching, sampling, filtering, enrichment, retries; lets you change/multiplex backends without redeploying apps.

**6. Agent vs gateway Collector deployment?** Agent = one per host/pod for local collection and metadata. Gateway = central cluster for heavy processing, tail sampling, and exporting.

**7. Auto vs manual instrumentation?** Auto gives framework-level spans (HTTP, DB) with no code; manual adds business meaning (custom spans, attributes, metrics). Use both.

**8. What is a Resource?** Immutable attributes describing the entity producing telemetry (service.name, version, pod, region).

**9. Head vs tail sampling?** Head decides at trace start (cheap, random, can miss errors). Tail decides after the trace completes (can keep all errors/slow traces, needs Collector memory and all spans of a trace routed to one instance).

**10. What is OTLP?** The native OTel protocol over gRPC (4317) or HTTP/protobuf (4318).

**11. Why can high-cardinality labels be dangerous?** Every unique label combination is a new time series; user_id as a label can blow up memory and cost. Use span attributes instead.

**12. How do you correlate logs with traces?** Inject trace_id/span_id into log records (LoggingInstrumentor); backends link them.

**13. Does OTel replace Prometheus/Jaeger?** No. It produces and transports data; Prometheus/Jaeger/Tempo store and query it.

**14. A service shows high latency; walk me through it.** Alert on p95 → dashboard narrows the service → filter traces by duration → find the slowest span (e.g. DB query) → use its trace_id to read logs → fix → add alert.

**15. How do you keep telemetry from hurting performance?** Batch processors (async export), sampling, limit attribute size, memory_limiter in Collector, avoid sync exporters in the request path.

---


## Cleanup
```bash
docker-compose down
```
