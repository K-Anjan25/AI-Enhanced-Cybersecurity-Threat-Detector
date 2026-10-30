/**
 * The embedded assistant's wire shape and call (read-only, see docs/assistant.md).
 *
 * The question travels as a query parameter on a GET, so asking changes nothing on the
 * server and needs no write capability.
 */
import { getJson } from './client';

export const ASSISTANT_PATH = '/api/v1/assistant/ask';

export interface AssistantAnswer {
  answer: string;
  /** Which backend produced the text: `rules`, `openai`, or `guardrail` for a refusal. */
  backend: string;
  /** The read-only tools that supplied facts. Empty for a refusal, help, or unknown. */
  sources: string[];
}

export async function askAssistant(question: string, signal?: AbortSignal): Promise<AssistantAnswer> {
  return getJson<AssistantAnswer>(`${ASSISTANT_PATH}?question=${encodeURIComponent(question)}`, {
    signal,
  });
}
