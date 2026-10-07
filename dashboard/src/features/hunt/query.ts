/**
 * The hunt console's query language (T-408, design.md §4.6).
 *
 * The console is a *structured* search over the alert read model: `field:value`
 * terms, whitespace-separated, AND-combined. Everything here is pure, so what a
 * hunt means can be tested without rendering one.
 *
 * Four decisions, and each of them is the difference between a console an analyst
 * can trust and a box that returns rows:
 *
 *   * **The vocabulary is the read model's own.** design.md §4.6 lists `src_ip`,
 *     `dst_port`, `template_id` and `family` as autocomplete suggestions, and only
 *     `family` exists in this build: flow records have no read API (T-418) and the
 *     hunt API queries alerts, not the log store (T-419) — whose reads are by window,
 *     host, level and cluster key, with no text search by design. Rather than
 *     accept a term it cannot answer, the console knows the fields the API actually
 *     filters on and names the missing ones on the screen — see `UNSEARCHABLE_TERMS`.
 *   * **An unknown field is refused, never ignored.** A hunt that silently dropped
 *     `src_ip:10.0.0.7` and returned the whole window would be the worst possible
 *     answer: the analyst believes they searched by source address and the rows say
 *     nothing about it.
 *   * **A field set twice is refused, not merged.** The API takes one value per
 *     filter; `severity:high severity:low` would be two intents collapsed into one
 *     silently. The error names the fix — `severity:high,low` — which is the same
 *     meaning written the way the API can express it.
 *   * **The echo is canonical.** The empty state shows the executed query and the
 *     window (design.md §4.6), so what it shows is what ran: the parsed terms
 *     re-serialised, not the analyst's original string with its typo fixed later.
 */
import type { AlertListParams } from '../../api/alerts';
import { SEVERITIES } from '../../components/ui/severity';

/** How a field compares, in words, for the operator hints §4.6 asks for. */
export type HuntOperator = 'any of' | 'at least' | 'exactly' | 'ordering' | 'row cap';

export interface HuntField {
  /** As typed, and as shown in the autocomplete. */
  name: string;
  /** The API parameter it sets. */
  param: keyof AlertListParams;
  /** The comparison, for the hint line. */
  operator: HuntOperator;
  /** A closed set of values, or `null` when the value is free text. */
  values: readonly string[] | null;
  /**
   * Values worth offering for a field whose value is *not* closed.
   *
   * `limit` is the case that needs this: the API takes any whole number from 1 to
   * 1,000, so a closed set would refuse `limit:750` — a legal hunt — while still
   * being the right thing to *suggest*. A closed field leaves this undefined; a
   * suggestion is never a restriction.
   */
  suggestions?: readonly string[];
  /** The suggestion the autocomplete shows beside the field. */
  hint: string;
  description: string;
}

/**
 * The alert read model's filterable fields, and only those.
 *
 * `order` and `limit` are here although they are not filters: they *are* part of the
 * query the API runs, the export and the audit entry both carry them, and an echo
 * that left them out would be an incomplete description of what was searched.
 */
export const HUNT_FIELDS: readonly HuntField[] = [
  {
    name: 'severity',
    param: 'severity',
    operator: 'any of',
    values: SEVERITIES,
    hint: 'severity:high,critical',
    description: 'The severity band the correlator assigned.',
  },
  {
    name: 'status',
    param: 'status',
    operator: 'any of',
    values: ['open', 'acknowledged', 'closed'],
    hint: 'status:open',
    description: 'The alert’s lifecycle state.',
  },
  {
    name: 'family',
    param: 'family',
    operator: 'exactly',
    values: null,
    hint: 'family:exfiltration',
    description:
      'The attack family the model named. Free text: the labels come from the datasets, not from a list this build owns.',
  },
  {
    name: 'entity',
    param: 'entityId',
    operator: 'exactly',
    values: null,
    hint: 'entity:42',
    description:
      'The alerting entity’s id. Host and user names are not available yet — the API returns ids.',
  },
  {
    name: 'min_score',
    param: 'minScore',
    operator: 'at least',
    values: null,
    hint: 'min_score:0.8',
    description: 'The model’s score, from 0 to 1, at or above this value.',
  },
  {
    name: 'order',
    param: 'order',
    operator: 'ordering',
    values: ['desc', 'asc'],
    hint: 'order:desc',
    description: 'Newest first (default) or oldest first.',
  },
  {
    name: 'limit',
    param: 'limit',
    operator: 'row cap',
    values: null,
    suggestions: ['100', '500', '1000'],
    hint: 'limit:500',
    description: 'How many rows one read returns, from 1 to 1,000.',
  },
];

/**
 * Terms design.md §4.6 suggests that this build cannot answer.
 *
 * Named on the screen rather than quietly missing from the autocomplete: the whole
 * value of a hunt is knowing what was searched, and a field that vanished from the
 * vocabulary without a reason reads like an oversight.
 */
export const UNSEARCHABLE_TERMS: readonly { name: string; reason: string }[] = [
  {
    name: 'src_ip',
    reason: 'raw flow records have no read API in this build (T-418)',
  },
  {
    name: 'dst_port',
    reason: 'raw flow records have no read API in this build (T-418)',
  },
  {
    name: 'template_id',
    reason: 'cluster keys are searched on the Logs screen; the hunt API reads alerts (T-419)',
  },
  {
    name: 'message',
    reason: 'log lines carry a message digest, not a searchable text field (T-419)',
  },
  {
    name: 'trace',
    reason: 'the alert query API filters on the window, not on a trace id',
  },
];

/** One parsed term, with the field it sets and the value(s) it names. */
export interface HuntTerm {
  field: HuntField;
  /** The value as typed, minus any normalisation. */
  raw: string;
  /** The values it names: one, or several after a comma. */
  values: readonly string[];
}

export interface HuntError {
  /** The token that could not be read, exactly as typed. */
  token: string;
  /** Why, in a sentence an analyst can act on. */
  reason: string;
}

export interface HuntParse {
  terms: HuntTerm[];
  errors: HuntError[];
}

const BY_NAME = new Map(HUNT_FIELDS.map((field) => [field.name, field] as const));

/** The fields, for a caller that wants to render the vocabulary. */
export function huntField(name: string): HuntField | undefined {
  return BY_NAME.get(name);
}

/**
 * Parse a hunt into terms and errors.
 *
 * Both halves matter: the errors are what let the Run button be disabled with a
 * reason rather than the request failing later, and a parse with errors still
 * carries the terms that *were* readable so the screen can show what it understood.
 */
export function parseHuntQuery(text: string): HuntParse {
  const terms: HuntTerm[] = [];
  const errors: HuntError[] = [];
  const seen = new Set<string>();

  for (const token of text
    .trim()
    .split(/\s+/)
    .filter((part) => part !== '')) {
    const colon = token.indexOf(':');
    if (colon === -1) {
      errors.push({ token, reason: 'every term is field:value — this one names no field' });
      continue;
    }
    const name = token.slice(0, colon).toLowerCase();
    const raw = token.slice(colon + 1);
    const field = BY_NAME.get(name);
    if (field === undefined) {
      errors.push({
        token,
        reason: `“${name}” is not a field this build can search. It filters on ${HUNT_FIELDS.map(
          (known) => known.name,
        ).join(', ')}`,
      });
      continue;
    }
    if (raw === '') {
      errors.push({ token, reason: `${name} needs a value, as in ${field.hint}` });
      continue;
    }
    if (seen.has(field.name)) {
      errors.push({
        token,
        reason: `${name} is set twice. Write ${name}:${raw},${
          terms.find((term) => term.field.name === name)?.raw ?? '…'
        } instead`,
      });
      continue;
    }
    const values = field.values === null ? [raw] : raw.split(',');
    // A closed vocabulary is checked case-insensitively and normalised to the
    // API's own spelling: `severity:High` is the same intent as `severity:high`,
    // and refusing it would be pedantry rather than safety.
    const normalised =
      field.values === null
        ? values
        : values
            .map((value) => value.toLowerCase())
            .map((value) => {
              if (!field.values?.includes(value)) {
                errors.push({
                  token,
                  reason: `${name} takes ${field.values?.join(', ')} — “${value}” is not one of them`,
                });
              }
              return value;
            });
    if (field.values !== null && normalised.some((value) => !field.values?.includes(value))) {
      continue;
    }
    const problem = validateValue(field, raw, normalised);
    if (problem !== null) {
      errors.push({ token, reason: problem });
      continue;
    }
    seen.add(field.name);
    terms.push({ field, raw, values: normalised });
  }

  return { terms, errors };
}

/** Field-specific value checks: numbers, ranges, one value where the API takes one. */
function validateValue(field: HuntField, raw: string, values: readonly string[]): string | null {
  if (values.length === 1 && (field.name === 'entity' || field.name === 'limit')) {
    const parsed = Number(values[0]);
    if (!Number.isInteger(parsed)) {
      return `${field.name} takes a whole number, as in ${field.hint}`;
    }
    if (field.name === 'limit' && (parsed < 1 || parsed > 1_000)) {
      return 'limit runs from 1 to 1,000: the API refuses a wider read';
    }
  }
  if (field.name === 'min_score') {
    const parsed = Number(values[0]);
    if (Number.isNaN(parsed)) {
      return `min_score takes a number from 0 to 1, as in ${field.hint}`;
    }
    if (parsed < 0 || parsed > 1) {
      return 'min_score runs from 0 to 1';
    }
  }
  if (field.values !== null && values.length === 0) {
    return `${field.name} needs a value, as in ${field.hint}`;
  }
  void raw;
  return null;
}

/** The default the API applies when a term is absent. */
export const HUNT_DEFAULTS = { order: 'desc', limit: 100 } as const;

export interface HuntWindow {
  start: Date;
  end: Date;
}

/** The window options the console offers. */
export interface HuntSpan {
  key: '24h' | '7d' | '30d' | '90d';
  label: string;
  spanMs: number;
}

/**
 * Four spans, none wider than the read the API will serve.
 *
 * The ceiling is the server's (`MAX_QUERY_SPAN_DAYS = 92`): ninety days is the
 * widest option here so the console cannot build a query the API refuses, which is
 * better than letting the analyst find the boundary by being rejected at it. A
 * ninety-day hunt is a *slow* question — that is what the row cap and the export are
 * for — but it is a legal one.
 */
export const HUNT_SPANS: readonly HuntSpan[] = [
  { key: '24h', label: 'Last 24 hours', spanMs: 86_400_000 },
  { key: '7d', label: 'Last 7 days', spanMs: 7 * 86_400_000 },
  { key: '30d', label: 'Last 30 days', spanMs: 30 * 86_400_000 },
  { key: '90d', label: 'Last 90 days (maximum)', spanMs: 90 * 86_400_000 },
];

/** The span a key names, falling back to the default rather than throwing. */
export function spanOf(key: HuntSpan['key']): HuntSpan {
  return HUNT_SPANS.find((span) => span.key === key) ?? (HUNT_SPANS[0] as HuntSpan);
}

/**
 * The window a hunt reads, given a clock and a span.
 *
 * Snapshotted at the moment the hunt runs rather than recomputed at render: the
 * echo on an empty result says which window was searched, and a window that kept
 * moving would make the sentence false by the time it was read.
 */
export function huntWindow(key: HuntSpan['key'], now: number): HuntWindow {
  const span = spanOf(key);
  return { start: new Date(now - span.spanMs), end: new Date(now) };
}

/**
 * The API parameters for a parse, or `null` when it cannot be turned into a query.
 *
 * `null` rather than a partial query on purpose: a caller that ran the readable
 * half of a hunt would be searching something the analyst did not ask for.
 */
export function buildHuntParams(parse: HuntParse, window: HuntWindow): AlertListParams | null {
  if (parse.errors.length > 0) return null;
  const params: AlertListParams = {
    start: window.start,
    end: window.end,
    order: HUNT_DEFAULTS.order,
    limit: HUNT_DEFAULTS.limit,
  };
  for (const term of parse.terms) {
    const value = term.values.join(',');
    switch (term.field.param) {
      case 'severity':
        params.severity = value;
        break;
      case 'status':
        params.status = value;
        break;
      case 'family':
        params.family = value;
        break;
      case 'entityId':
        params.entityId = Number(value);
        break;
      case 'minScore':
        params.minScore = Number(value);
        break;
      case 'order':
        params.order = value as 'asc' | 'desc';
        break;
      case 'limit':
        params.limit = Number(value);
        break;
      default:
        break;
    }
  }
  return params;
}

/**
 * The executed query in words: the canonical echo the empty state renders.
 *
 * Terms come back in the order they were written, spelled the way the API reads
 * them, and the row cap and ordering are always shown even when they were defaulted
 * — an analyst looking at an empty table is asking "what did I actually search",
 * and the answer includes the parts they did not type.
 */
export function describeHunt(parse: HuntParse): string {
  const shown = parse.terms.map((term) => `${term.field.name}:${term.values.join(',')}`);
  const order = parse.terms.find((term) => term.field.name === 'order');
  const limit = parse.terms.find((term) => term.field.name === 'limit');
  if (order === undefined) shown.push(`order:${HUNT_DEFAULTS.order}`);
  if (limit === undefined) shown.push(`limit:${String(HUNT_DEFAULTS.limit)}`);
  return shown.join(' ');
}

/** One autocomplete suggestion. */
export interface HuntSuggestion {
  /** What gets inserted. */
  value: string;
  /** The hint column: the operator, or what the field filters on. */
  detail: string;
  kind: 'field' | 'value' | 'unsearchable';
}

/**
 * Suggestions for the token the caret is in.
 *
 * The three kinds exist because the honest answer differs: a known field is
 * suggested, its closed values are suggested, and a field this build cannot search
 * is *still* suggested — as a refusal with the reason attached, so an analyst typing
 * `src_ip:` learns why nothing is offered instead of concluding the console is
 * broken.
 */
export function huntCompletions(text: string, caret: number): HuntSuggestion[] {
  const upToCaret = text.slice(0, caret);
  const tokenStart = upToCaret.lastIndexOf(' ') + 1;
  const token = upToCaret.slice(tokenStart);
  const colon = token.indexOf(':');

  if (colon === -1) {
    const prefix = token.toLowerCase();
    const fields = HUNT_FIELDS.filter((field) => field.name.startsWith(prefix)).map((field) => ({
      value: `${field.name}:`,
      detail: field.hint,
      kind: 'field' as const,
    }));
    const missing = UNSEARCHABLE_TERMS.filter(
      (term) => term.name.startsWith(prefix) && prefix !== '',
    ).map((term) => ({
      value: `${term.name}:`,
      detail: term.reason,
      kind: 'unsearchable' as const,
    }));
    return [...fields, ...missing];
  }

  const field = BY_NAME.get(token.slice(0, colon).toLowerCase());
  if (field === undefined) return [];
  // A closed vocabulary completes to its values; a free field completes to its
  // suggestions and *keeps* whatever was typed, so `limit:7` still completes to
  // `limit:750` if the analyst keeps going.
  const choices = field.values ?? field.suggestions ?? [];
  const typed = token.slice(colon + 1).toLowerCase();
  const already = field.values === null ? [] : typed.split(',').slice(0, -1);
  return choices
    .filter((value) => !already.includes(value))
    .filter((value) => value.startsWith(typed.split(',').at(-1) ?? ''))
    .map((value) => ({
      value: `${field.name}:${[...already, value].join(',')}`,
      detail: field.hint,
      kind: 'value' as const,
    }));
}
