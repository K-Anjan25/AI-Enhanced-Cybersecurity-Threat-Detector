import React, { useState, FormEvent } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { resetPassword } from "../../../api/userApi";
import { getApiError } from "../../../utils/getApiError";
import { Spinner } from "../../../components/ui";
import { ThemeToggle } from "../../../components/ThemeToggle";
import BrandLogo from "../../../components/BrandLogo";

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const navigate = useNavigate();

  const [newPassword, setNewPassword] = useState<string>("");
  const [message, setMessage] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setMessage("");
    setError("");
    setLoading(true);

    try {
      if (token) {
        const data: any = await resetPassword({ token, new_password: newPassword });
        setMessage(data.message || "Password updated successfully!");
        setTimeout(() => navigate("/login"), 3000);
      }
    } catch (err: any) {
      setError(
        getApiError(err, "Failed to reset password. Link may be expired.")
      );
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="relative min-h-screen bg-app-bg flex items-center justify-center p-4 text-content-primary">
        <ThemeToggle variant="pill" className="absolute top-4 right-4" />
        <div className="w-full max-w-sm p-6 bg-app-surface rounded-3xl shadow-card border border-line-subtle text-center space-y-3">
          <BrandLogo size={40} withWordmark={false} className="mx-auto" />
          <p className="text-sm text-content-secondary">
            Invalid or missing reset token link.
          </p>
          <button
            type="button"
            onClick={() => navigate("/login")}
            className="mt-1 w-full py-2.5 bg-brand-gradient hover:-translate-y-0.5 hover:shadow-signal hover:opacity-95 rounded-sm font-semibold text-brand-ink transition cursor-pointer text-sm"
          >
            Back to Sign In
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="relative min-h-screen bg-app-bg flex items-center justify-center p-4">
      <ThemeToggle variant="pill" className="absolute top-4 right-4" />
      <div className="w-full max-w-md bg-app-surface border border-line-subtle rounded-3xl shadow-card p-8 space-y-6 text-content-primary">
        <div className="flex flex-col items-center gap-3">
          <BrandLogo size={40} withWordmark={false} />
          <div className="text-center space-y-1.5">
            <h2 className="text-2xl font-bold tracking-tight">Set New Password</h2>
            <p className="text-xs tracking-[0.14em] text-content-tertiary uppercase">
              Your autonomous security analyst
            </p>
          </div>
        </div>

        {message && (
          <div className="bg-status-success/15 border border-status-success/30 text-status-success p-2.5 rounded-lg text-xs text-center">
            {message}
          </div>
        )}
        {error && (
          <div className="bg-status-critical/15 border border-status-critical/30 text-status-critical p-2.5 rounded-lg text-xs text-center">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="new-password" className="block text-xs font-semibold text-content-secondary mb-1.5">
              New Password
            </label>
            <input
              id="new-password"
              type="password"
              placeholder="Enter new password"
              className="w-full bg-app-bg border border-line-subtle rounded-lg px-3.5 py-2.5 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary transition"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-brand-gradient hover:-translate-y-0.5 hover:shadow-signal hover:opacity-95 rounded-sm font-semibold text-brand-ink transition disabled:opacity-50 cursor-pointer text-sm flex items-center justify-center shadow-float"
          >
            {loading ? (
              <>
                <Spinner variant="light" className="mr-2" />
                Updating...
              </>
            ) : (
              "Update Password"
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
