import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { Spinner } from './Spinner';

describe('Spinner', () => {
  it('is decorative: the control it sits in already says what is happening', () => {
    // A spinner is never the only content. If it announced itself, every loading
    // button would be read out twice.
    const { container } = render(<Spinner />);

    const spinner = container.firstElementChild;
    expect(spinner).toHaveAttribute('aria-hidden', 'true');
    expect(spinner).not.toHaveAttribute('role');
  });

  it('rotates rather than carrying meaning in its rotation', async () => {
    const { container } = render(
      <button type="button" aria-busy="true">
        <Spinner />
        <span className="sr-only">Saving</span>
      </button>,
    );

    await expectAccessible(container as HTMLElement);
  });
});
