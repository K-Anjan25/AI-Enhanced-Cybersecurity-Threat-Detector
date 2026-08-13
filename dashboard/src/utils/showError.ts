/**
 * Displays error feedback from network requests or form validation failures.
 * Renders through the shared non-blocking toast system.
 */
import { getApiError } from "./getApiError";
import { getToastPusher } from "../components/ui/Toast";

export const showError = (error: unknown): void => {
  const message = getApiError(error);
  console.error(`[SOC ERROR]: ${message}`);
  getToastPusher()(message, "error");
};

export default showError;