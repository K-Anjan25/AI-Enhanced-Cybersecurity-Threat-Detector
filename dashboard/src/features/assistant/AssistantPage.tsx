/**
 * The embedded assistant. The operator asks a question; the page shows the answer, where
 * it came from, and the tools that supplied the facts. Nothing here writes.
 */
import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';

import { askAssistant, type AssistantAnswer } from '../../api/assistant';
import { Badge, Button, Card } from '../../components/ui';
import { ASSISTANT_SCOPE_NOTE, answerLabel, canAsk } from './assistant';

interface Exchange {
  question: string;
  reply: AssistantAnswer;
}

export function AssistantPage() {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState<Exchange[]>([]);
  const ask = useMutation({
    mutationFn: (text: string) => askAssistant(text),
    onSuccess: (reply, text) => setHistory((past) => [{ question: text, reply }, ...past]),
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canAsk(question)) return;
    ask.mutate(question.trim());
    setQuestion('');
  };

  return (
    <Card title="Assistant">
      <form onSubmit={submit} aria-label="Ask the assistant">
        <label htmlFor="assistant-question">Question</label>{' '}
        <input
          id="assistant-question"
          type="text"
          value={question}
          maxLength={500}
          placeholder="e.g. How many alerts in the last 3 days?"
          onChange={(event) => setQuestion(event.target.value)}
        />{' '}
        <Button type="submit" disabled={!canAsk(question) || ask.isPending}>
          Ask
        </Button>
      </form>
      <p>{ASSISTANT_SCOPE_NOTE}</p>
      {ask.isError ? <p role="alert">The assistant could not answer: {ask.error.message}</p> : null}
      <ol aria-label="Answers" style={{ listStyle: 'none', padding: 0 }}>
        {history.map((exchange, index) => (
          <li key={`${String(history.length - index)}-${exchange.question}`}>
            <p>
              <strong>{exchange.question}</strong>
            </p>
            <p>{exchange.reply.answer}</p>
            <p>
              <Badge tone="neutral">{answerLabel(exchange.reply.backend)}</Badge>
              {exchange.reply.sources.length > 0 ? (
                <span> Tools: {exchange.reply.sources.join(', ')}</span>
              ) : null}
            </p>
          </li>
        ))}
      </ol>
    </Card>
  );
}
