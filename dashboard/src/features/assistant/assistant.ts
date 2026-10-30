/**
 * The assistant page's rules: how a reply is labelled, and what the page promises.
 *
 * The label says where an answer came from, so a reader can tell a model's words from
 * a count the system computed. A refusal is labelled as one.
 */
const LABELS: Readonly<Record<string, string>> = {
  rules: 'Computed from the data',
  openai: 'Written by the local model',
  guardrail: 'Refused',
};

/** The label for a backend value. An unknown value is shown as-is, never hidden. */
export function answerLabel(backend: string): string {
  return LABELS[backend] ?? `Source: ${backend}`;
}

/** The sentence under the input, which states the boundary of this page. */
export const ASSISTANT_SCOPE_NOTE =
  'Read-only. It can count and list alerts and report capture status. It cannot change anything, and it will not reveal passwords or keys.';

/** A question is sent only when it has text after trimming. */
export function canAsk(question: string): boolean {
  return question.trim().length > 0 && question.trim().length <= 500;
}
