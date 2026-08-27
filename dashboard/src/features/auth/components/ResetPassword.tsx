import React, { useState, FormEvent } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { resetPassword } from "../../../api/userApi";
import { getApiError } from "../../../utils/getApiError";

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
      <div className="min-h-screen flex items-center justify-center bg-app-bg text-content-primary">
        <div className="p-6 bg-app-surface rounded-xl shadow-sm border border-line-subtle text-content-secondary text-sm">
          Invalid or missing reset token link.
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-app-bg">
      <div className="bg-app-surface p-8 rounded-2xl shadow-xl w-96 border border-line-subtle text-content-primary">
        <h2 className="text-2xl font-bold text-accent-primary text-center mb-6">
          Set New Password
        </h2>

        {message && (
          <div className="bg-status-success/15 border border-status-success/30 text-status-success p-2.5 rounded-lg mb-4 text-xs text-center">
            {message}
          </div>
        )}
        {error && (
          <div className="bg-status-critical/15 border border-status-critical/30 text-status-critical p-2.5 rounded-lg mb-4 text-xs text-center">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="password"
            placeholder="Enter new password"
            className="w-full bg-app-bg border border-line-subtle rounded-lg px-3.5 py-2.5 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary transition"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-accent-primary hover:opacity-90 py-2.5 rounded-lg font-semibold text-app-bg transition disabled:opacity-50 cursor-pointer text-sm"
          >
            {loading ? "Updating..." : "Update Password"}
          </button>
        </form>
      </div>
    </div>
  );
}