/**
 * The Prometheus text exposition format, parsed in the browser (T-403).
 *
 * The backend already publishes everything the pipeline strip needs at `/metrics`
 * — counters, a latency histogram and the Kafka lag gauge — and that endpoint is
 * deliberately unauthenticated and content-free (D-050). Reading it here rather
 * than adding a second endpoint keeps one source of truth for the numbers: the
 * strip shows what Prometheus would scrape, and there is no chance of the JSON
 * endpoint and the scrape drifting apart.
 *
 * What this module is not: a general Prometheus client. It parses the exposition
 * format our own process emits and nothing else, and it refuses a line it cannot
 * read instead of quietly dropping it — a silently skipped series would render as
 * "not measured", which is a fact about the system, not about a typo.
 */

export interface Sample {
  /** The metric name, with `_bucket`/`_total` suffixes as emitted. */
  name: string;
  labels: Readonly<Record<string, string>>;
  value: number;
}

/** A cumulative histogram bucket: everything at or below `le`. */
export interface Bucket {
  le: number;
  cumulative: number;
}

const SAMPLE = /^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{(.*)\})?\s+(\S+)(?:\s+\S+)?$/;

/** Label pairs, with the escapes the format defines. */
function parseLabels(body: string): Record<string, string> {
  const labels: Record<string, string> = {};
  const pair = /([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"/g;
  let match = pair.exec(body);
  while (match !== null) {
    const [, name, raw] = match;
    labels[name as string] = (raw as string).replace(/\\(.)/g, (_all, escaped: string) =>
      escaped === 'n' ? '\n' : escaped,
    );
    match = pair.exec(body);
  }
  return labels;
}

function parseValue(raw: string): number {
  if (raw === '+Inf') return Number.POSITIVE_INFINITY;
  if (raw === '-Inf') return Number.NEGATIVE_INFINITY;
  const value = Number(raw);
  if (Number.isNaN(value) && raw !== 'NaN') {
    throw new Error('metrics exposition contains a value that is not a number');
  }
  return value;
}

/**
 * Parse an exposition document into samples.
 *
 * Comments (`# HELP`, `# TYPE`, anything else starting with `#`) and blank lines
 * are skipped; every other line must be a sample.
 */
export function parseExposition(text: string): Sample[] {
  const samples: Sample[] = [];
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (line === '' || line.startsWith('#')) continue;
    const match = SAMPLE.exec(line);
    if (match === null) {
      throw new Error(`metrics exposition line is not a sample: ${line.slice(0, 40)}`);
    }
    const [, name, , labelBody, rawValue] = match;
    samples.push({
      name: name as string,
      labels: labelBody === undefined ? {} : parseLabels(labelBody),
      value: parseValue(rawValue as string),
    });
  }
  return samples;
}

/** Every sample of one metric name, optionally narrowed by labels. */
export function samplesNamed(
  samples: readonly Sample[],
  name: string,
  labels: Readonly<Record<string, string>> = {},
): Sample[] {
  return samples.filter(
    (sample) =>
      sample.name === name &&
      Object.entries(labels).every(([key, value]) => sample.labels[key] === value),
  );
}

/** The sum of a set of samples, or `null` when there are none. */
export function sumOf(samples: readonly Sample[]): number | null {
  if (samples.length === 0) return null;
  return samples.reduce((total, sample) => total + sample.value, 0);
}

/** The single value of a series, or `null` when it was never observed. */
export function valueOf(
  samples: readonly Sample[],
  name: string,
  labels: Readonly<Record<string, string>> = {},
): number | null {
  const found = samplesNamed(samples, name, labels);
  return found.length === 0 ? null : (found[0] as Sample).value;
}

/**
 * The cumulative buckets of one histogram, ordered by upper bound.
 *
 * A histogram with no `+Inf` bucket cannot be quantiled — the algorithm needs the
 * total — so that is a refusal rather than an approximation.
 */
export function histogramBuckets(
  samples: readonly Sample[],
  name: string,
  labels: Readonly<Record<string, string>> = {},
): Bucket[] {
  const buckets: Bucket[] = [];
  for (const sample of samplesNamed(samples, `${name}_bucket`, labels)) {
    const bound = sample.labels.le;
    // `+Inf` is the last bucket and must become `Infinity`, not `NaN`: a NaN bound
    // sorts to an arbitrary position, which would leave the running total wrong and
    // every quantile with it.
    const le = bound === '+Inf' ? Number.POSITIVE_INFINITY : Number(bound);
    if (Number.isNaN(le)) continue;
    buckets.push({ le, cumulative: sample.value });
  }
  buckets.sort((a, b) => a.le - b.le);
  return buckets;
}

/**
 * `histogram_quantile`, the same algorithm Prometheus uses.
 *
 * Linear interpolation inside the bucket that contains the rank, with the bucket
 * before it as the lower bound. Two edge cases are the ones that matter: a
 * histogram with no observations has no quantile (`null`, not `0` — reporting
 * `0 ms` for a stage nobody measured is the lie R-74 exists to prevent), and a
 * rank that falls in the `+Inf` bucket can only be bounded, so it returns the
 * last finite bound.
 */
export function histogramQuantile(buckets: readonly Bucket[], quantile: number): number | null {
  if (buckets.length === 0) return null;
  const total = (buckets.at(-1) as Bucket).cumulative;
  if (total <= 0) return null;
  const rank = quantile * total;

  let previousBound = 0;
  let previousCumulative = 0;
  for (const bucket of buckets) {
    if (bucket.cumulative >= rank) {
      const inBucket = bucket.cumulative - previousCumulative;
      if (!Number.isFinite(bucket.le)) return previousBound;
      if (inBucket <= 0) return bucket.le;
      return previousBound + (bucket.le - previousBound) * ((rank - previousCumulative) / inBucket);
    }
    previousBound = Number.isFinite(bucket.le) ? bucket.le : previousBound;
    previousCumulative = bucket.cumulative;
  }
  return previousBound;
}

/** The p95 of one histogram, in seconds, or `null` when nothing was observed. */
export function histogramP95Seconds(
  samples: readonly Sample[],
  name: string,
  labels: Readonly<Record<string, string>> = {},
): number | null {
  return histogramQuantile(histogramBuckets(samples, name, labels), 0.95);
}

/** One observation of a cumulative series, for a rate between two scrapes. */
export interface CounterSample {
  at: number;
  value: number;
}

/**
 * A per-second rate between two scrapes of a counter.
 *
 * `null` when there is no previous scrape, when no time passed, or when the
 * counter went backwards. A counter that resets (a restarted process) must not
 * render as a negative rate: a negative throughput on a health strip would read
 * as an incident. `Math.max(0, delta)` would hide a reset behind a spike to zero
 * instead, so it is reported as unmeasured for one interval.
 */
export function counterRate(previous: CounterSample | null, current: CounterSample): number | null {
  if (previous === null) return null;
  const elapsed = (current.at - previous.at) / 1_000;
  if (elapsed <= 0) return null;
  const delta = current.value - previous.value;
  if (delta < 0) return null;
  return delta / elapsed;
}
