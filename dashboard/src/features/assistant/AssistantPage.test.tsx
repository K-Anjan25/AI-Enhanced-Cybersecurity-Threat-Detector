import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import * as assistantApi from '../../api/assistant';
import { testQueryClient } from '../../test/query';
import { AssistantPage } from './AssistantPage';

function renderPage() {
  return render(
    <QueryClientProvider client={testQueryClient()}>
      <AssistantPage />
    </QueryClientProvider>,
  );
}

describe('AssistantPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('asks, shows the answer with its source label and tools', async () => {
    const ask = vi.spyOn(assistantApi, 'askAssistant').mockResolvedValue({
      answer: 'There were 3 alerts in the last 24 hour(s).',
      backend: 'rules',
      sources: ['count_alerts'],
    });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText('Question'), 'how many alerts in the last 24 hours');
    await user.click(screen.getByRole('button', { name: 'Ask' }));

    expect(ask).toHaveBeenCalledWith('how many alerts in the last 24 hours');
    expect(await screen.findByText('There were 3 alerts in the last 24 hour(s).')).toBeInTheDocument();
    expect(screen.getByText('Computed from the data')).toBeInTheDocument();
    expect(screen.getByText(/Tools: count_alerts/)).toBeInTheDocument();
  });

  it('labels a refusal as a refusal', async () => {
    vi.spyOn(assistantApi, 'askAssistant').mockResolvedValue({
      answer: 'I can only read alerts and capture status.',
      backend: 'guardrail',
      sources: [],
    });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText('Question'), 'stop packet capture');
    await user.click(screen.getByRole('button', { name: 'Ask' }));
    expect(await screen.findByText('Refused')).toBeInTheDocument();
  });

  it('keeps the Ask button disabled for a blank question', async () => {
    renderPage();
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled();
  });

  it('says when the assistant could not answer', async () => {
    vi.spyOn(assistantApi, 'askAssistant').mockRejectedValue(new Error('timed out'));
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText('Question'), 'latest alerts');
    await user.click(screen.getByRole('button', { name: 'Ask' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('timed out');
  });
});
