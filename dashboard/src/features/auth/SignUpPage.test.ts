import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/client';
import { signUpErrorMessage } from './SignUpPage';

describe('sign-up error messages', () => {
  it('says sign-up is off when the deployment has it disabled', () => {
    expect(signUpErrorMessage(new ApiError('status', 404, 'not found'))).toBe(
      'Sign-up is turned off on this deployment.',
    );
  });

  it('asks the user to wait when throttled', () => {
    expect(signUpErrorMessage(new ApiError('status', 429, 'slow down'))).toBe(
      'Too many attempts. Wait a few minutes and try again.',
    );
  });

  it('states the password rule on a validation failure', () => {
    expect(signUpErrorMessage(new ApiError('status', 422, 'bad'))).toBe(
      'Check the email address and use a password of at least 12 characters.',
    );
  });

  it('reports an unreachable service rather than a refusal', () => {
    expect(signUpErrorMessage(new ApiError('unreachable', null, 'down'))).toBe(
      'Authentication service unreachable.',
    );
  });

  it('falls back to the status for anything else', () => {
    expect(signUpErrorMessage(new ApiError('status', 500, 'boom'))).toBe(
      'Sign-up was refused (HTTP 500).',
    );
  });
});
