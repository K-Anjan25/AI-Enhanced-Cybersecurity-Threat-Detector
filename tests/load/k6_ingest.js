// T-501: Load test — 5,000 flows/s + 10,000 logs/s for 30 minutes.
//
// Run:  k6 run tests/load/k6_ingest.js
// Or:  k6 run --vus 50 --duration 30m tests/load/k6_ingest.js
//
// NFR-02: sustained throughput with no error-rate increase.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate = new Rate('errors');
const ingestLatency = new Trend('ingest_latency_ms', true);

const BASE_URL = __ENV.AEGIS_BASE_URL || 'http://localhost:8000';
const API_KEY = __ENV.AEGIS_API_KEY || 'test-api-key';

export const options = {
  scenarios: {
    // Scenario 1: Flow ingestion at 5,000/s
    flow_ingest: {
      executor: 'constant-arrival-rate',
      rate: 5000,
      timeUnit: '1s',
      duration: '30m',
      preAllocatedVUs: 100,
      maxVUs: 200,
      exec: 'ingestFlows',
    },
    // Scenario 2: Log ingestion at 10,000/s
    log_ingest: {
      executor: 'constant-arrival-rate',
      rate: 10000,
      timeUnit: '1s',
      duration: '30m',
      preAllocatedVUs: 200,
      maxVUs: 400,
      exec: 'ingestLogs',
    },
  },
  thresholds: {
    // NFR-02: error rate must stay below 1% throughout
    errors: ['rate<0.01'],
    // NFR-01: ingest stage budget is 40ms p95
    ingest_latency_ms: ['p(95)<40'],
  },
};

function randomIP() {
  return `${10 + Math.floor(Math.random() * 240)}.${Math.floor(Math.random() * 256)}.${Math.floor(Math.random() * 256)}.${1 + Math.floor(Math.random() * 254)}`;
}

function randomPort() {
  const ports = [80, 443, 53, 22, 3389, 8080, 8443, 3306, 5432, 6379];
  return ports[Math.floor(Math.random() * ports.length)];
}

function randomProto() {
  return Math.random() < 0.7 ? 'tcp' : Math.random() < 0.9 ? 'udp' : 'icmp';
}

function generateFlow() {
  return {
    src_ip: randomIP(),
    dst_ip: randomIP(),
    src_port: 1024 + Math.floor(Math.random() * 64000),
    dst_port: randomPort(),
    proto: randomProto(),
    bytes_in: Math.floor(Math.random() * 1000000),
    bytes_out: Math.floor(Math.random() * 5000000),
    packets_in: Math.floor(Math.random() * 1000),
    packets_out: Math.floor(Math.random() * 5000),
    duration: Math.random() * 300,
    timestamp: new Date().toISOString(),
  };
}

function generateLog() {
  const levels = ['INFO', 'WARN', 'ERROR', 'DEBUG'];
  const sources = ['syslog', 'auth', 'firewall', 'ids', 'dns'];
  return {
    source: sources[Math.floor(Math.random() * sources.length)],
    level: levels[Math.floor(Math.random() * levels.length)],
    message: `Test log entry ${Math.random().toString(36).substring(7)}`,
    host: randomIP(),
    timestamp: new Date().toISOString(),
  };
}

export function ingestFlows() {
  const payload = JSON.stringify({
    modality: 'flow',
    records: Array.from({ length: 10 }, generateFlow),
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${API_KEY}`,
    },
    timeout: '10s',
  };

  const res = http.post(`${BASE_URL}/api/v1/ingest`, payload, params);

  const success = check(res, {
    'flow ingest status 2xx': (r) => r.status >= 200 && r.status < 300,
  });

  errorRate.add(!success);
  ingestLatency.add(res.timings.duration);
}

export function ingestLogs() {
  const payload = JSON.stringify({
    modality: 'log',
    records: Array.from({ length: 20 }, generateLog),
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${API_KEY}`,
    },
    timeout: '10s',
  };

  const res = http.post(`${BASE_URL}/api/v1/ingest`, payload, params);

  const success = check(res, {
    'log ingest status 2xx': (r) => r.status >= 200 && r.status < 300,
  });

  errorRate.add(!success);
  ingestLatency.add(res.timings.duration);
}
