import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { Card } from './Card';

describe('Card', () => {
  it('is a labelled region with a real heading and an actions slot', () => {
    render(
      <Card title="Top entities" actions={<button type="button">Last 24 h</button>}>
        <p>acme-dc-01 \u00b7 42 alerts</p>
      </Card>,
    );

    expect(screen.getByRole('heading', { level: 2, name: 'Top entities' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Last 24 h' })).toBeInTheDocument();
    expect(screen.getByText(/42 alerts/)).toBeInTheDocument();
  });

  it('cannot render blank while loading: it draws skeletons that name the panel', () => {
    render(
      <Card title="Severity over time" state="loading" loadingLines={5}>
        <p>chart</p>
      </Card>,
    );

    expect(screen.getByRole('status')).toHaveTextContent('Severity over time is loading');
    expect(screen.getAllByTestId('skeleton-bar')).toHaveLength(5);
    expect(screen.queryByText('chart')).not.toBeInTheDocument();
  });

  it('says what is empty rather than showing an empty frame', () => {
    render(
      <Card
        title="Open alerts"
        state="empty"
        empty={{ title: 'No open critical alerts in the last 24 h.', description: 'Widen to 7 d' }}
      >
        <p>table</p>
      </Card>,
    );

    expect(screen.getByRole('status')).toHaveTextContent(
      'No open critical alerts in the last 24 h.',
    );
    expect(screen.queryByText('table')).not.toBeInTheDocument();
  });

  it('falls back to a plain sentence when the caller says nothing about empty', () => {
    render(<Card title="Open alerts" state="empty" />);

    expect(screen.getByRole('status')).toHaveTextContent('Nothing to show');
  });

  it('names the failure and offers a retry', () => {
    render(
      <Card
        title="Pipeline health"
        state="error"
        error={{
          message: 'The pipeline status could not be loaded',
          detail: 'Showing the last successful load',
          action: <button type="button">Retry</button>,
        }}
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('The pipeline status could not be loaded');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('defaults to ready, so a caller that says nothing gets its children', () => {
    render(
      <Card title="Model drift">
        <p>drift chart</p>
      </Card>,
    );

    expect(screen.getByText('drift chart')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('has no serious accessibility violations in any of its four states', async () => {
    const { container } = render(
      <div>
        <Card title="Ready">
          <p>content</p>
        </Card>
        <Card title="Loading" state="loading" />
        <Card title="Empty" state="empty" />
        <Card title="Error" state="error" />
      </div>,
    );

    await expectAccessible(container as HTMLElement);
  });
});
