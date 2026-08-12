/**
 * Displays error feedback from network requests or form validation failures.
 */
import { getApiError } from "./getApiError";

export const showError = (error: unknown): void => {
  const message = getApiError(error);
  console.error(`[SOC ERROR]: ${message}`);
  alert(`Error: ${message}`);
};

export default showError;