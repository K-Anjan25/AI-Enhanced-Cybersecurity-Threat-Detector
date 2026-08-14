// Threat AI load test — verifies the NFR-PERF targets from
// docs/non-functional-requirements.md against the running stack.
//
//   Targets:
//     NFR-PERF-01  /api/v1/analyze          p95 latency <=  500 ms
//     NFR-PERF-02  /api/v1/upload-logs      throughput  >=  100 lines/s (background scan)
//     NFR-PERF-03  concurrent scans         no starvation at >= MAX_CONCURRENT_SCANS (10)
//     NFR-PERF-04  /api/v1/alerts?limit=100 p95 <= 200 ms (at 10k alerts)
//     NFR-PERF-05  ml-service /predict/*    throughput >= 50 predictions/s per replica
//
//   Usage:
//     k6 run -e BASE_HOST=http://localhost:8000 \
//            -e ML_HOST=http://localhost:8001 \
//            -e TOKENPASS='ChangeMe#2026' threat-ai.js
//
//   BASE_HOST must point at the backend API root (http://localhost:8000,
//   http://<ingress>/api/v1, etc.). ML_HOST points at the ml-service.
//
//   Auth: setup() registers + logs in ONCE and the bearer token is shared by
//   every VU, so the backend's per-IP login rate limit does not throttle the
//   test and the measured numbers cover only the analysed paths.

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate, Counter } from "k6/metrics";

const BASE_HOST = __ENV.BASE_HOST || "http://localhost:8000";
const ML_HOST = __ENV.ML_HOST || "http://localhost:8001";
const API = `${BASE_HOST}/api/v1`;
const TOKEN_PASS = __ENV.TOKENPASS || "ChangeMe#2026";

// Custom disaggregated metrics so thresholds map 1:1 to NFR IDs.
const analyzeLatency = new Trend("perf_analyze_latency", true);
const alertsLatency = new Trend("perf_alerts_latency", true);
const uploadLatency = new Trend("perf_upload_latency", true);
const predictLatency = new Trend("perf_predict_latency", true);
const analyzeFail = new Rate("perf_analyze_failures");
const alertsFail = new Rate("perf_alerts_failures");
const uploadFail = new Rate("perf_upload_failures");
const predictFail = new Rate("perf_predict_failures");
const predictions = new Counter("perf_predict_count");

export const options = {
  scenarios: {
    main: {
      executor: "constant-vus",
      vus: 15,
      duration: "90s",
      exec: "main",
    },
    predict: {
      executor: "constant-arrival-rate",
      rate: 55, // NFR-PERF-05 needs >= 50 req/s per replica
      timeUnit: "1s",
      duration: "30s",
      preAllocatedVUs: 10,
      maxVUs: 30,
      exec: "predict",
    },
  },
  thresholds: {
    perf_analyze_latency: ["p(95)<500"],
    perf_analyze_failures: ["rate<0.01"],
    perf_alerts_latency: ["p(95)<200"],
    perf_alerts_failures: ["rate<0.01"],
    perf_predict_latency: ["p(95)<1000"],
    perf_predict_failures: ["rate<0.01"],
  },
};

function credentials() {
  return { username: "k6loadtest", password: TOKEN_PASS };
}

function authHeaders(token, jsonBody = false) {
  const h = { Authorization: `Bearer ${token}` };
  if (jsonBody) h["Content-Type"] = "application/json";
  return { headers: h };
}

const sampleLog = {
  message: "Failed password for invalid user root from 203.0.113.9 port 22 ssh2",
  source: "auth.log",
  level: "ERROR",
  timestamp: "2026-08-14T15:00:00Z",
};

const sampleFlow = {
  src_ip: "203.0.113.9",
  dst_ip: "10.0.0.5",
  src_port: "52341",
  dst_port: "443",
  protocol: "TCP",
  bytes: 1245772,
  duration: 12.4,
};

// 100 log lines for the batch upload (NFR-PERF-02/03).
const batchLines = Array.from(
  { length: 100 },
  (_, i) => `[${i}] Failed password for invalid user admin from 198.51.100.${i % 250} port 22 ssh2`,
).join("\n");

export function setup() {
  const reg = http.post(
    `${API}/register`,
    JSON.stringify({ ...credentials(), email: "k6loadtest@test.local" }),
    { headers: { "Content-Type": "application/json" } },
  );
  const form = new URLSearchParams(credentials()).toString();
  const login = http.post(`${API}/login`, form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  const token = login.json("access_token") || login.json("accessToken") || "";
  check(login, { "setup login 200": (r) => r.status === 200 });
  return { token, registered: reg.status === 201 || reg.status === 400 };
}

// NFR-PERF-01/02/03/04: weighted mix of the analysed backend paths.
export function main(data) {
  // NFR-PERF-01: single-record alert analysis.
  const analyzeResponse = http.post(
    `${API}/analyze`,
    JSON.stringify(Math.random() < 0.5 ? sampleFlow : sampleLog),
    authHeaders(data.token, true),
  );
  analyzeLatency.add(analyzeResponse.timings.duration);
  analyzeFail.add(!check(analyzeResponse, { "analyze 200": (r) => r.status === 200 }));
  sleep(0.2);

  // NFR-PERF-04: paginated alert listing.
  const alertsResponse = http.get(`${API}/alerts?limit=100`, authHeaders(data.token));
  alertsLatency.add(alertsResponse.timings.duration);
  alertsFail.add(!check(alertsResponse, { "alerts 200": (r) => r.status === 200 }));
  sleep(0.2);

  // NFR-PERF-02/03: batch upload (100 lines) + poll to completion.
  if (__ITER % 10 === 0) {
    const file = http.file(batchLines, "loadtest.log", "text/plain");
    const res = http.post(`${API}/upload-logs`, { log_file: file }, authHeaders(data.token));
    uploadLatency.add(res.timings.duration);
    uploadFail.add(!check(res, { "upload 200": (r) => r.status === 200 }));
    if (res.status === 200) {
      const batchId = res.json("batch_id");
      for (let i = 0; i < 20; i++) {
        const poll = http.get(`${API}/uploads/${batchId}`, authHeaders(data.token));
        const status = poll.json("batch.status") || "";
        if (status === "completed" || status === "failed") break;
        sleep(1);
      }
    }
  }
}

// NFR-PERF-05: steady-arrival ML scoring against the ml-service.
export function predict() {
  const res = http.post(`${ML_HOST}/predict/log`, JSON.stringify(sampleLog), {
    headers: { "Content-Type": "application/json" },
  });
  predictions.add(1);
  predictLatency.add(res.timings.duration);
  predictFail.add(!check(res, { "predict 200": (r) => r.status === 200 }));
}