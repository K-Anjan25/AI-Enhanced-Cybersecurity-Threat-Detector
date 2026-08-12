import React from "react";
import { useFormik } from "formik";
import { useMutation } from "react-query";
import { useNavigate, Link } from "react-router-dom";
import Button from "../../../components/ui/Button";
import TextInput from "../../../components/common/TextInput";
import { registerSchema, initialRegisterValues } from "../../../validators/registerValidator";
import { registerUser } from "../../../api/userApi";
import { showSuccess } from "../../../utils/showSuccess";
import { showError } from "../../../utils/showError";

export default function Register(): React.ReactElement {
  const navigate = useNavigate();

  const registerMutation = useMutation({
    mutationFn: registerUser,
    onSuccess: () => {
      showSuccess("Analyst account registered successfully. Please sign in.");
      navigate("/login");
    },
    onError: (err: any) => {
      showError(err?.response?.data?.message || "Registration failed");
    },
  });

  const formik = useFormik({
    initialValues: initialRegisterValues,
    validationSchema: registerSchema,
    onSubmit: (values) => {
      const { confirmPassword, ...payload } = values;
      registerMutation.mutate({ ...payload, role: payload.role || "ANALYST" });
    },
  });

  return (
    <div className="min-h-screen bg-app-bg flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-app-surface border border-line-subtle rounded-xl shadow-2xl p-8 space-y-6 text-content-primary">
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">SOC Analyst Onboarding</h1>
          <p className="text-xs text-content-secondary">Register for Threat AI Incident Portal Access</p>
        </div>

        <form onSubmit={formik.handleSubmit} className="space-y-4">
          <TextInput form={formik} name="username" label="Username" />
          <TextInput form={formik} name="email" label="Email Address" type="email" />
          <TextInput form={formik} name="password" label="Password" type="password" />
          <TextInput
            form={formik}
            name="confirmPassword"
            label="Confirm Password"
            type="password"
          />

          <Button
            type="submit"
            variant="primary"
            size="md"
            disabled={registerMutation.isLoading}
            className="w-full mt-2"
          >
            {registerMutation.isLoading ? (
              <span className="inline-block animate-spin rounded-full h-4 w-4 border-2 border-app-bg border-t-transparent mr-2" />
            ) : null}
            {registerMutation.isLoading ? "Creating Account..." : "Create Account"}
          </Button>
        </form>

        <div className="text-center pt-2 border-t border-line-subtle">
          <p className="text-xs text-content-secondary">
            Already have an account?{" "}
            <Link to="/login" className="text-accent-primary hover:underline font-medium">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}