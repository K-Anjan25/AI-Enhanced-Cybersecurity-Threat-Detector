import React, { useState, useEffect } from "react";
import { useFormik } from "formik";
import { useSelector, useDispatch } from "react-redux";
import { useNavigate, Link } from "react-router-dom";
import TextInput from "../../../components/common/TextInput";
import { RootState } from "../../../store/store";
import ForgotPassword from "../components/ForgotPassword";
import loginForm from "../../../validators/loginValidator";
import showSuccess from "../../../utils/showSuccess";
import { login } from "../../../store/userActions";
import { AxiosError } from "axios";
import { UserError } from "../../../types/error";

export default function Login(): React.ReactElement {
  const dispatch = useDispatch<any>();
  const navigate = useNavigate();
const { user, loading, isLogedIn } = useSelector((state: RootState) => state.user);
  useEffect(() => {
    if (isLogedIn || user) {
      showSuccess("You have successfully logged in!");
      navigate("/alerts");
    }
  }, [isLogedIn, user, navigate]);

  const [isForgetPasswordOpen, setIsForgetPasswordOpen] = useState<boolean>(false);
  const [loginError, setLoginError] = useState<string>("");

  const form = useFormik({
    ...loginForm,
    onSubmit: async (values, { setSubmitting }) => {
      setLoginError("");
      try {
        await dispatch(login(values));
        navigate("/alerts");
      } catch (error) {
        const err = error as AxiosError<UserError>;
        setLoginError(
          err?.response?.data?.message ||
            err?.message ||
            "Authentication failed. Please check your credentials."
        );
      } finally {
        setSubmitting(false);
      }
    },
  });

  return (
    <div className="min-h-screen bg-app-bg flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-app-surface border border-line-subtle rounded-2xl shadow-2xl p-8 space-y-6">
        <div className="text-center space-y-2">
          <h2 className="text-2xl font-bold text-content-primary tracking-wide">
            SOC Console Login
          </h2>
          <p className="text-xs text-content-secondary">
            Access Threat AI Analytics & System Telemetry
          </p>
        </div>

        {loginError && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-xs p-3 rounded-lg text-center">
            {loginError}
          </div>
        )}

        <form onSubmit={form.handleSubmit} className="space-y-4">
          <TextInput
            form={form}
            name="identifier"
            label="Email or Username"
            type="text"
            placeholder="Enter your email or username"
          />

          <TextInput
            form={form}
            name="password"
            label="Password"
            type="password"
            placeholder="••••••••"
          />

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => setIsForgetPasswordOpen(true)}
              className="text-xs text-accent-primary hover:text-accent-glow hover:underline transition"
            >
              Forgot Password?
            </button>
          </div>

          <button
            type="submit"
            disabled={form.isSubmitting || loading}
            className="w-full py-2.5 bg-accent-primary hover:bg-accent-secondary disabled:bg-accent-secondary text-app-bg rounded-lg text-sm font-semibold transition duration-150 flex items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-glow/60"
          >
            {form.isSubmitting || loading ? (
              <>
                <span className="inline-block animate-spin rounded-full h-4 w-4 border-2 border-app-bg border-t-transparent mr-2" />
                Signing In...
              </>
            ) : (
              "Sign In"
            )}
          </button>
        </form>

        <div className="text-center pt-2 border-t border-line-subtle">
          <p className="text-xs text-content-secondary">
            Need analyst credentials?{" "}
            <Link to="/register" className="text-accent-primary hover:underline font-medium">
              Register here
            </Link>
          </p>
        </div>
      </div>

      {isForgetPasswordOpen && (
        <ForgotPassword onClose={() => setIsForgetPasswordOpen(false)} />
      )}
    </div>
  );
}