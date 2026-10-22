/**
 * Marketing copy and data, kept apart from the components so the wording can be
 * reviewed without reading layout code. Figures are product defaults taken from the
 * code (50-record windows, four roles, 30-day raw retention, one-step rollback), not
 * customer metrics. Prices and plan limits are placeholders until pricing is signed off.
 */

export type RoutePath = '/' | '/features' | '/pricing' | '/contact';

export interface NavItem {
  to: RoutePath;
  label: string;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { to: '/', label: 'Home' },
  { to: '/features', label: 'Features' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/contact', label: 'Contact' },
];

export const SALES_EMAIL = 'hello@aegis.example';
export const SECURITY_EMAIL = 'security@aegis.example';

export interface Office {
  city: string;
  country: string;
  /** Latitude and longitude, used to place the pin on the dot map. */
  lat: number;
  lon: number;
  note: string;
}

export const OFFICES: readonly Office[] = [
  {
    city: 'Hyderabad',
    country: 'India',
    lat: 17.385,
    lon: 78.4867,
    note: 'Engineering and detection research',
  },
  {
    city: 'London',
    country: 'United Kingdom',
    lat: 51.5072,
    lon: -0.1276,
    note: 'EMEA sales and customer success',
  },
  {
    city: 'Singapore',
    country: 'Singapore',
    lat: 1.3521,
    lon: 103.8198,
    note: 'APAC support operations',
  },
  {
    city: 'Austin',
    country: 'United States',
    lat: 30.2672,
    lon: -97.7431,
    note: 'Headquarters and public sector team',
  },
];

export interface Feature {
  title: string;
  body: string;
}

export const FEATURE_CARDS: readonly Feature[] = [
  {
    title: 'Anomaly detection',
    body: 'Models score flow windows and log streams against learned baselines.',
  },
  {
    title: 'Alert grouping',
    body: 'Related events merge into one alert with a count and a timeline.',
  },
  {
    title: 'Threat hunting',
    body: 'Saved queries across flows and logs, with results you can share.',
  },
  {
    title: 'Model lifecycle',
    body: 'Promote, compare and roll back model versions with a full history.',
  },
  {
    title: 'Integrations',
    body: 'Webhooks signed with HMAC, plus a versioned REST API with scoped keys.',
  },
  {
    title: 'Access control',
    body: 'Four roles and single sign-on, so each person sees only their work.',
  },
];

export interface SplitSection {
  id?: string;
  eyebrow: string;
  title: string;
  body: string;
  points: ReadonlyArray<readonly [string, string]>;
  image: string;
  alt: string;
}

/** Placeholder imagery from placehold.co. Swap for product screenshots before launch. */
/** Brand-palette placeholders: Electric Cyan on Midnight, or Slate on Midnight. */
const PLACEHOLDER_TONES = {
  cyan: '00f0ff/0b132b',
  slate: '6c757d/0b132b',
} as const;

const placeholder = (
  w: number,
  h: number,
  text: string,
  tone: keyof typeof PLACEHOLDER_TONES,
): string =>
  `https://placehold.co/${w}x${h}/${PLACEHOLDER_TONES[tone]}?text=${encodeURIComponent(text)}`;

export const HOME_SECTIONS: readonly SplitSection[] = [
  {
    eyebrow: 'Detect',
    title: 'Scoring that adapts to your traffic',
    body: 'AEGIS groups flow records into fixed windows and scores each window against learned baselines. You see the pattern, not one noisy packet.',
    points: [
      ['Flow and log models.', 'Separate models cover network flows and system logs.'],
      ['Explainable scores.', 'Every alert shows the features that drove the score.'],
      ['Tunable thresholds.', 'Change sensitivity per model, with each change in the audit trail.'],
    ],
    image: placeholder(960, 600, 'Detection engine', 'cyan'),
    alt: 'Placeholder for the detection engine scoring view',
  },
  {
    eyebrow: 'Triage',
    title: 'Alerts ranked by risk, grouped by story',
    body: 'Related events merge into one alert, so an analyst reviews a story rather than hundreds of rows. Each verdict is recorded once and cannot be silently rewritten.',
    points: [
      ['Grouped alerts.', 'Repeated events collapse into one counted incident.'],
      ['Immutable verdicts.', 'Analyst decisions are stored as a permanent record.'],
      ['Priority queue.', 'Severity and score decide what appears first.'],
    ],
    image: placeholder(960, 600, 'Triage queue', 'slate'),
    alt: 'Placeholder for the alert triage queue',
  },
  {
    eyebrow: 'Investigate',
    title: 'Search, hunt and export without leaving the console',
    body: 'Pivot from an alert to the flows, logs and entities behind it. Every export is logged with the person who requested it.',
    points: [
      ['Threat hunting.', 'Query flows and logs with saved, reusable searches.'],
      ['Audited exports.', 'CSV exports are logged with the requesting user.'],
      ['Role-based access.', 'Viewers, analysts, responders and admins see only what they need.'],
    ],
    image: placeholder(960, 600, 'Investigation console', 'cyan'),
    alt: 'Placeholder for the investigation console',
  },
];

export const FEATURE_SECTIONS: readonly SplitSection[] = [
  {
    eyebrow: 'Detection',
    title: 'Two model families, one place to review them',
    body: 'Flow models look for unusual conversations between hosts. Log models look for unusual sequences of events. Both feed the same alert queue, so a suspicious login and a suspicious connection appear together.',
    points: [
      [
        'Windowed scoring.',
        'Records are scored in fixed 50-record windows, so results are repeatable.',
      ],
      [
        'Per-model thresholds.',
        'Each model has its own threshold, changed only with an audit entry.',
      ],
      [
        'Baseline drift checks.',
        'The console shows when current traffic has moved away from the baseline.',
      ],
    ],
    image: placeholder(960, 600, 'Model scores', 'cyan'),
    alt: 'Placeholder for model score charts',
  },
  {
    id: 'governance',
    eyebrow: 'Governance',
    title: 'Built for audits: who did what, and when',
    body: 'Every sign-in, export, verdict and configuration change is written to an append-only audit trail. Each retention run lists what was removed and what was kept on purpose.',
    points: [
      [
        'Append-only audit trail.',
        'Entries are added, never edited, so the record stays trustworthy.',
      ],
      ['Scoped API keys.', 'Each key has explicit scopes and can be revoked immediately.'],
      ['Retention reports.', 'Each run lists what was swept and why some data is kept.'],
    ],
    image: placeholder(960, 600, 'Audit trail', 'slate'),
    alt: 'Placeholder for the audit trail view',
  },
  {
    eyebrow: 'Operations',
    title: 'Roll back a bad model in one step',
    body: 'If a new model version performs worse, AEGIS reverses the most recent promotion and restores the previous version. Un-reversed promotions stay available as rollback targets.',
    points: [
      ['One-step rollback.', 'Reverts the latest promotion to the version before it.'],
      ['Full version history.', 'Every promotion records who promoted it and when.'],
      ['Deployment-ready.', 'Runs on Docker Compose or Kubernetes with the same services.'],
    ],
    image: placeholder(960, 600, 'Model versions', 'cyan'),
    alt: 'Placeholder for model version history',
  },
];

export interface Stat {
  to: number;
  suffix?: string;
  label: string;
}

export const STATS: readonly Stat[] = [
  { to: 50, label: 'flow records scored together in each detection window' },
  { to: 4, label: 'analyst roles, from read-only viewer to full administrator' },
  { to: 30, suffix: ' days', label: 'default retention for raw records, set by you per data type' },
  { to: 1, suffix: ' step', label: 'to roll a model back to its previous promoted version' },
];

export const PIPELINE_STEPS: ReadonlyArray<readonly [string, string]> = [
  [
    'Connect a source',
    'Point flow exporters and log shippers at AEGIS. Start with one network segment.',
  ],
  [
    'Learn the baseline',
    'Models learn normal traffic for your environment before alerting at full sensitivity.',
  ],
  [
    'Tune and review',
    'Adjust thresholds and mute known-good patterns, with every change recorded.',
  ],
  [
    'Hand off to response',
    'Send prioritised alerts to your ticketing tool through webhooks signed with HMAC.',
  ],
];

export const ARCHITECTURE_STEPS: ReadonlyArray<readonly [string, string]> = [
  ['Capture', 'Flow sensors and log shippers stream records into the ingest service.'],
  ['Score', 'Models assign anomaly scores to each window and each log sequence.'],
  ['Alert', 'Scores above threshold become grouped alerts, ranked by severity.'],
  ['Decide', 'Analysts record a verdict, which is kept permanently and can be exported.'],
];

export interface FaqItem {
  q: string;
  a: string;
}

export const HOME_FAQ: readonly FaqItem[] = [
  {
    q: 'Does our traffic or log data leave our network?',
    a: 'No. AEGIS is deployed inside your environment. Raw flow records and logs stay in your own PostgreSQL and Kafka, and the models run on your infrastructure.',
  },
  {
    q: 'Is it only machine learning, or are there rules as well?',
    a: 'Both. Machine-learning models score behaviour against learned baselines, and rule-based checks catch known-bad patterns directly. Each alert records which of the two produced it.',
  },
  {
    q: 'How do you handle false positives?',
    a: 'Analysts review every alert and record a verdict. Thresholds are tunable per model, and changes are logged. Verdicts are permanent, so the history of a decision can always be reconstructed.',
  },
  {
    q: 'Can we sign in with our existing identity provider?',
    a: 'Yes. AEGIS supports single sign-on through OpenID Connect with PKCE. The server verifies the issuer, audience, signature and nonce on every login.',
  },
  {
    q: 'How long is data kept?',
    a: 'Raw records default to 30 days and can be set per data type. Retention runs on a schedule, and each run is recorded in the audit trail.',
  },
];

export const PRICING_FAQ: readonly FaqItem[] = [
  {
    q: 'Can I change plans later?',
    a: 'Yes. Upgrades take effect immediately and are prorated. Downgrades apply at the next billing date. Your data is not deleted when you change plans.',
  },
  {
    q: 'What counts as a seat?',
    a: 'A seat is a person with a console login. Service accounts that only use API keys do not count toward the seat limit.',
  },
  {
    q: 'Is there a discount for annual billing?',
    a: 'Annual billing saves about 13% on the Team plan. Enterprise pricing is agreed in the contract, including any multi-year terms.',
  },
  {
    q: 'Can I trial the Enterprise features?',
    a: 'Yes. Enterprise trials run for 30 days in a sandbox deployment. Ask the sales team to set one up.',
  },
  {
    q: 'What happens to our data if we cancel?',
    a: 'You export your data and decommission the deployment. AEGIS holds nothing you have not shared with us, so there is no separate copy to delete.',
  },
];

export interface Tier {
  name: string;
  description: string;
  /** null means "talk to sales" rather than a price. */
  monthly: number | null;
  annual: number | null;
  cta: string;
  featured?: boolean;
  included: readonly string[];
  excluded: readonly string[];
}

export const TIERS: readonly Tier[] = [
  {
    name: 'Community',
    description: 'Self-hosted detection for a single team evaluating AEGIS.',
    monthly: 0,
    annual: 0,
    cta: 'Start free',
    included: [
      'Flow and log models',
      'Up to 3 analyst seats',
      'Community support forum',
      '30-day raw retention',
    ],
    excluded: ['Single sign-on', 'Priority response times'],
  },
  {
    name: 'Team',
    description: 'For security teams running AEGIS across several networks.',
    monthly: 149,
    annual: 129,
    cta: 'Start free trial',
    featured: true,
    included: [
      'Everything in Community',
      'Up to 25 analyst seats',
      'Webhooks with HMAC signing',
      'Scoped API keys',
      'Email support, one business day',
    ],
    excluded: ['Single sign-on'],
  },
  {
    name: 'Enterprise',
    description: 'Deployment support, governance and response-time commitments.',
    monthly: null,
    annual: null,
    cta: 'Talk to sales',
    included: [
      'Everything in Team',
      'Unlimited analyst seats',
      'OIDC single sign-on',
      'Custom retention policies',
      'Named success engineer, 4-hour critical SLA',
    ],
    excluded: [],
  },
];

export const COMPARISON: ReadonlyArray<readonly [string, boolean, boolean, boolean]> = [
  ['Flow and log models', true, true, true],
  ['Grouped alert triage', true, true, true],
  ['Threat hunting and saved searches', true, true, true],
  ['Webhooks with HMAC signing', false, true, true],
  ['Scoped API keys', false, true, true],
  ['Single sign-on (OIDC)', false, false, true],
  ['Custom retention policies', false, false, true],
  ['Response-time SLA', false, false, true],
];

export interface FooterColumn {
  title: string;
  links: ReadonlyArray<readonly [string, string]>;
}

/* TODO: point the legal and documentation links at real pages before launch. */
export const FOOTER_COLUMNS: readonly FooterColumn[] = [
  {
    title: 'Product',
    links: [
      ['Features', '/features'],
      ['Pricing', '/pricing'],
      ['Security overview', '/features#governance'],
      ['Release notes', '/contact'],
    ],
  },
  {
    title: 'Company',
    links: [
      ['About AEGIS', '/contact'],
      ['Careers', '/contact'],
      ['Partners', '/contact'],
      ['Contact sales', '/contact'],
    ],
  },
  {
    title: 'Resources',
    links: [
      ['Documentation', '/features'],
      ['API reference', '/features'],
      ['System status', '/contact'],
      ['Support', '/contact'],
    ],
  },
  {
    title: 'Legal',
    links: [
      ['Privacy policy', '/contact'],
      ['Terms of service', '/contact'],
      ['Security disclosure', '/contact'],
      ['Cookie settings', '/contact'],
    ],
  },
];

/* TODO: replace these profile URLs with the organisation's real accounts. */
export const SOCIAL_LINKS: ReadonlyArray<{
  label: string;
  href: string;
  icon: 'github' | 'x' | 'youtube';
}> = [
  { label: 'AEGIS on GitHub', href: 'https://github.com/', icon: 'github' },
  { label: 'AEGIS on X', href: 'https://x.com/', icon: 'x' },
  { label: 'AEGIS on YouTube', href: 'https://www.youtube.com/', icon: 'youtube' },
];
