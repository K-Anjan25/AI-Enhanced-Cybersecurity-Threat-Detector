/**
 * Non-blocking success notification (auto-dismissing toast, no modal/alert).
 * Routes through the shared toast system.
 */
import { getToastPusher } from "../components/ui/Toast";

export const showSuccess = (message: string): void => {
  console.log(`[SOC SUCCESS]: ${message}`);
  getToastPusher()(message, "success");
};

export default showSuccess;