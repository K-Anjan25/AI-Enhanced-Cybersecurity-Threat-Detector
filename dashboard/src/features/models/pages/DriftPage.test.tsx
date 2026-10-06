/**
 * The drift screen (T-409), through the page an operator opens.
 *
 * T-409's acceptance criterion is that the bars **mark the 0.25 threshold**, so that is
 * asserted where a reader meets it: the threshold line exists, its printed value is
 * 0.25, and a feature exactly on the line is drawn as stable while one just over it is
 * drawn as drifting — the strict `>` the drift computation uses.
 *
 * The other half of the suite is the honesty rule. The gauge is not observed by the
 * process serving `/metrics` on this build (T-421), so the page must say the series is
 * missing and name the task, not draw an empty axis that reads as "nothing is drifting".
 */
import { render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ToastProvider } from '../../../components/ui';
import { expectAccessible } from '../../../test/axe';
import { Providers, stubFetch, textResponse } from '../../../test/query';

import { DriftPage } from './DriftPage';

const METRICS_BODY = `# HELP aegis_alerts_created_total Alerts created.
# TYPE aegis_alerts_created_total counter
aegis_alerts_created_total 41
# HELP aegis_drift_psi Population stability index per feature.
# TYPE aegis_drift_psi gauge
aegis_drift_psi{feature="state"} 26.667
aegis_drift_psi{feature="service"} 0.25
aegis_drift_psi{feature="fin"} 0.051082562
`;

function renderPage() {
  return render(
    <ToastProvider>
      <Providers>
        <DriftPage />
      </Providers>
    </ToastProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the bars mark the threshold', () => {
  it('draws a threshold mark at 0.25 and a retrain badge only above it', async () => {
    stubFetch([{ match: '/metrics', respond: () => textResponse(METRICS_BODY) }]);
    renderPage();

    const table = await screen.findByRole('table', { name: /stability index per feature/i });
    // One mark per bar, because they share an axis: three features, three lines.
    const marks = screen.getAllByTestId('threshold-mark');
    expect(marks).toHaveLength(3);
    const mark = marks[0] as HTMLElement;
    // The mark carries the rule's own number, so a reader does not have to know it.
    expect(mark).toHaveAttribute('title', 'FR-32 threshold 0.25');

    // Spread across the bars' own domain: 0.25 is a *small* share of a domain set by
    // the 26.667 outlier, which is the point of deriving the domain rather than fixing it.
    expect(Number.parseFloat(mark.style.left)).toBeCloseTo(0.5, 1);

    const rows = within(table)
      .getAllByRole('rowheader')
      .map((header) => header.textContent);
    expect(rows).toEqual(['state', 'service', 'fin']);

    // Exactly 0.25 is not over the threshold (the computation is `value > threshold`),
    // so `service` carries neither the badge nor the drifting row state.
    const bodyRows = within(table).getAllByRole('row').slice(1);
    expect(within(bodyRows[1] as HTMLElement).queryByText(/retrain recommended/i)).toBeNull();
    expect(within(bodyRows[2] as HTMLElement).queryByText(/retrain recommended/i)).toBeNull();
    expect(
      within(bodyRows[0] as HTMLElement).getByText(/retrain recommended/i),
    ).toBeInTheDocument();
    // The count is outside the table, in the sentence above it.
    expect(screen.getByText(/1 over the threshold/)).toBeInTheDocument();
  });

  it('shows each value as text, not only as a bar', async () => {
    // NFR-10: the number is the message; the bar's fill is decoration. A reader who
    // cannot see the fill must still learn the value.
    stubFetch([{ match: '/metrics', respond: () => textResponse(METRICS_BODY) }]);
    renderPage();

    await screen.findByRole('table', { name: /stability index per feature/i });
    expect(screen.getByText('26.6670')).toBeInTheDocument();
    expect(screen.getByText('0.2500')).toBeInTheDocument();
    expect(screen.getByText('0.0511')).toBeInTheDocument();
    expect(screen.queryByText('26.667')).toBeNull(); // the psi is formatted, not raw
  });

  it('is accessibility-clean', async () => {
    stubFetch([{ match: '/metrics', respond: () => textResponse(METRICS_BODY) }]);
    const { container } = renderPage();
    await screen.findByRole('table', { name: /stability index per feature/i });
    await expectAccessible(container);
  });
});

describe('no series is said, not drawn', () => {
  it('names the absent gauge and the task that will produce it', async () => {
    stubFetch([
      {
        match: '/metrics',
        respond: () => textResponse('aegis_alerts_created_total 41\n'),
      },
    ]);
    renderPage();

    expect(await screen.findByText('No drift series in this scrape')).toBeInTheDocument();
    const note = screen.getByText(/T-421/);
    expect(note).toHaveTextContent('aegis_drift_psi');
    expect(screen.queryByRole('table', { name: /stability index per feature/i })).toBeNull();
    expect(screen.queryByTestId('threshold-mark')).toBeNull();
  });

  it('says the scrape failed rather than showing an empty chart', async () => {
    stubFetch([{ match: '/metrics', respond: () => textResponse('', 500) }]);
    renderPage();

    expect(await screen.findByText(/could not be read/i)).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: /stability index per feature/i })).toBeNull();
  });
});
