/**
 * The query box's own interaction.
 *
 * The cases here are the ones an analyst would feel: Enter runs the hunt when the
 * list is closed but *accepts a suggestion* when it is open (the alternative —
 * Enter meaning both — is how a half-written query gets submitted), a term that
 * cannot be read keeps Run disabled and shows the reason, and a field this build
 * cannot search is still offered, as a refusal with its reason.
 */
import { render, screen } from '@testing-library/react';
import { useState } from 'react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { parseHuntQuery } from '../query';
import { QueryInput } from './QueryInput';

/** A stateful box, because a controlled input that refuses its own edits is not one. */
function Harness({
  initial = '',
  onRun = vi.fn(),
  onChange = vi.fn(),
}: {
  initial?: string;
  onRun?: () => void;
  onChange?: (next: string) => void;
}) {
  const [value, setValue] = useState(initial);
  return (
    <QueryInput
      value={value}
      onChange={(next) => {
        onChange(next);
        setValue(next);
      }}
      onRun={onRun}
      errors={parseHuntQuery(value).errors}
    />
  );
}

describe('QueryInput', () => {
  it('is a combobox that names what it is for', () => {
    render(<Harness />);
    expect(screen.getByRole('combobox', { name: 'Query' })).toBeInTheDocument();
  });

  it('shows a term it cannot read, before anything is sent', () => {
    render(<Harness initial="src_ip:10.0.0.7" />);
    expect(screen.getByText(/not a field this build can search/)).toBeInTheDocument();
  });

  it('offers a field it cannot search, with the reason attached', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('combobox', { name: 'Query' }));
    await user.keyboard('src');

    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent('src_ip:');
    expect(options[0]).toHaveTextContent('raw flow records have no read API in this build (T-418)');
  });

  it('runs the hunt on Enter, because nothing is highlighted until an arrow key', async () => {
    // Enter belongs to the analyst's own query: an autocomplete that hijacked it
    // whenever a suggestion existed would search, or edit, something else.
    const onRun = vi.fn();
    const user = userEvent.setup();
    render(<Harness onRun={onRun} />);

    await user.type(screen.getByRole('combobox', { name: 'Query' }), 'severity:high');
    await user.keyboard('{Enter}');

    expect(onRun).toHaveBeenCalledTimes(1);
  });

  it('accepts a suggestion with ArrowDown and Enter rather than running', async () => {
    // The state an analyst is in while completing a value: a readable term, then a
    // half-written one. Arrowing into the list is what makes Enter mean "take that
    // suggestion" — and it inserts the whole value, with a space to carry on from.
    const onRun = vi.fn();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial="severity:high limit:" onRun={onRun} onChange={onChange} />);

    await user.click(screen.getByRole('combobox', { name: 'Query' }));
    await user.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('option')[0]).toHaveTextContent('limit:100');
    await user.keyboard('{Enter}');

    expect(onRun).not.toHaveBeenCalled();
    expect(onChange).toHaveBeenCalledWith('severity:high limit:100 ');
  });

  it('closes the list on Escape without touching the text', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial="sev" onChange={onChange} />);

    const box = screen.getByRole('combobox', { name: 'Query' });
    await user.click(box);
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    await user.keyboard('{Escape}');

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('completes a value inside the token the caret is in', async () => {
    const user = userEvent.setup();
    render(<Harness initial="status:open severity:h" />);

    await user.click(screen.getByRole('combobox', { name: 'Query' }));
    await user.keyboard('{ArrowDown}');

    const options = screen.getAllByRole('option');
    expect(options[0]).toHaveTextContent('severity:high');
  });
});
