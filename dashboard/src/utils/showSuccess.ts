/**
 * Triggers a success notification for completed actions or forms.
 */
export const showSuccess = (message: string): void => {
  console.log(`[SOC SUCCESS]: ${message}`);
  alert(`Success: ${message}`);
};

export default showSuccess;