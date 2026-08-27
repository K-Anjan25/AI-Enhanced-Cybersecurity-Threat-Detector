import React, { useState } from "react";
import { useFormik } from "formik";
import { useSelector, useDispatch } from "react-redux";
import { useNavigate, Link } from "react-router-dom";
import TextInput from "../../../components/common/TextInput";
import { Spinner } from "../../../components/ui";
import { RootState } from "../../../store/store";
import ForgotPassword from "../components/ForgotPassword";
import loginForm from "../../../validators/loginValidator";
import showSuccess from "../../../utils/showSuccess";
import { login } from "../../../store/userActions";
import { getToken } from "../../../utils/token";
import { UserError } from "../../../types/error";
import BrandLogo from "../../../components/BrandLogo";
import { BRAND_TAGLINE } from "../../../constants/brand";

export default function Login(): React.ReactElement {
  const dispatch = useDispatch<any>();
  const navigate = useNavigate();
  // Loading state gates the button while a request is in flight.
  const { loading } = useSelector((state: RootState) => state.user);

  const [isForgetPasswordOpen, setIsForgetPasswordOpen] = useState<boolean>(false);
  const [loginError, setLoginError] = useState<string>("");

  const form = useFormik({
    ...loginForm,
    onSubmit: async (values, { setSubmitting }) => {
      setLoginError("");
      try {
        await dispatch(login(values));
        // The auth flag is only set after a successful /login, so navigating
        // off is safe only when the session was actually established.
        if (getToken()) {
          showSuccess("You have successfully logged in!");
          navigate("/");
        } else {
          setLoginError(
            "Authentication failed. Please check your credentials."
          );
        }
      } catch (error) {
        const err = error as UserError;
        setLoginError(
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
      <div className="w-full max-w-md bg-app-surface border border-line-subtle rounded-3xl shadow-card p-8 space-y-6">
        <div className="flex flex-col items-center gap-3">
          <BrandLogo size={36} />
          <div className="text-center space-y-1">
            <h2 className="text-2xl font-bold text-content-primary tracking-tight">Welcome back</h2>
            <p className="text-xs tracking-[0.14em] text-content-tertiary uppercase">{BRAND_TAGLINE}</p>
          </div>
        </div>

        {loginError && (
          <div className="bg-status-critical/10 border border-status-critical/30 text-status-critical text-xs p-3 rounded-lg text-center">
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
              className="text-xs text-accent-primary hover:text-accent-secondary hover:underline transition"
            >
              Forgot Password?
            </button>
          </div>

          <button
            type="submit"
            disabled={form.isSubmitting || loading}
            className="w-full py-3 bg-brand-gradient hover:opacity-90 disabled:opacity-60 text-brand-ink rounded-full text-sm font-semibold transition duration-150 flex items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40 shadow-float"
          >
            {form.isSubmitting || loading ? (
              <>
                <Spinner variant="light" className="mr-2" />
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