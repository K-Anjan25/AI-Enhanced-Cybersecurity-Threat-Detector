/**
 * Extract a human-readable message from an API error object.
 * Handles FastAPI's `detail` field as well as generic `message` errors.
 */
export const getApiError = (error: unknown, fallback = "Something went wrong"): string => {
  if (typeof error === "string") return error;

  const err = error as {
    detail?: unknown;
    message?: string;
    response?: { data?: { message?: string; detail?: string } };
  };

  const nestedDetail = err.response?.data?.detail;
  const nestedMessage = err.response?.data?.message;

  if (typeof nestedDetail === "string") return nestedDetail;
  if (typeof nestedMessage === "string") return nestedMessage;
  if (typeof err.detail === "string") return err.detail;
  return err.message || fallback;
};

export default getApiError;
