import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { Button } from './Button';

describe('Button', () => {
  it('is a real button, and does not submit a form by accident', () => {
    render(<Button>Run hunt</Button>);

    const button = screen.getByRole('button', { name: 'Run hunt' });
    expect(button).toHaveAttribute('type', 'button');
  });

  it('keeps its name while loading, and says so', () => {
    // The contract: `loading` swaps the *label* for a spinner. The accessible name
    // must survive the swap, or a screen-reader user loses the control's identity
    // exactly when it stops responding to clicks.
    render(<Button loading>Saving verdict</Button>);

    const button = screen.getByRole('button', { name: 'Saving verdict' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
  });

  it('does not fire while loading', () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Saving verdict
      </Button>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Saving verdict' }));

    expect(onClick).not.toHaveBeenCalled();
  });

  it('calls back when it is enabled', () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Refresh</Button>);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('uses the near-black text pair on the danger fill, per the badge rule', () => {
    // §5.3: light text on the severity fills fails (3.91 on critical). The danger
    // button wears the critical fill, so it inherits the same rule.
    render(<Button variant="danger">Delete hunt</Button>);

    const button = screen.getByRole('button', { name: 'Delete hunt' });
    expect(button.className).toContain('bg-severity-critical');
    expect(button.className).toContain('text-onSeverity');
  });

  it.each([
    ['primary', 'Run hunt'],
    ['secondary', 'Save'],
    ['ghost', 'Dismiss'],
    ['danger', 'Delete hunt'],
  ] as const)('renders the %s variant with an accessible name', (variant, label) => {
    render(<Button variant={variant}>{label}</Button>);

    expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
  });

  it('has no serious accessibility violations in any state', async () => {
    const { container } = render(
      <div>
        <Button>Run hunt</Button>
        <Button variant="secondary">Save</Button>
        <Button variant="ghost">Dismiss</Button>
        <Button variant="danger">Delete hunt</Button>
        <Button loading>Saving verdict</Button>
        <Button disabled>Export</Button>
      </div>,
    );

    await expectAccessible(container as HTMLElement);
  });
});
