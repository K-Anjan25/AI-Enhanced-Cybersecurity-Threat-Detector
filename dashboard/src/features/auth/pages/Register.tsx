import React from "react";
import { useFormik } from "formik";
import { useMutation } from "react-query";
import { useNavigate, Link } from "react-router-dom";
import Button from "../../../components/ui/Button";
import { Spinner } from "../../../components/ui";
import TextInput from "../../../components/common/TextInput";
import { registerSchema, initialRegisterValues } from "../../../validators/registerValidator";
import { registerUser } from "../../../api/userApi";
import { showSuccess } from "../../../utils/showSuccess";
import { showError } from "../../../utils/showError";
import { getApiError } from "../../../utils/getApiError";
import BrandLogo from "../../../components/BrandLogo";
import { BRAND_TAGLINE } from "../../../constants/brand";

export default function Register(): React.ReactElement {
  const navigate = useNavigate();

  const registerMutation = useMutation({
    mutationFn: registerUser,
    onSuccess: () => {
      showSuccess("Analyst account registered successfully. Please sign in.");
      navigate("/login");
    },
    onError: (err: any) => {
      showError(getApiError(err, "Registration failed"));
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
      <div className="w-full max-w-md bg-app-surface border border-line-subtle rounded-3xl shadow-card p-8 space-y-6 text-content-primary">
        <div className="flex flex-col items-center gap-3">
          <BrandLogo size={36} />
          <div className="text-center space-y-1">
            <h1 className="text-2xl font-bold tracking-tight">Create your analyst account</h1>
            <p className="text-xs tracking-[0.14em] text-content-tertiary uppercase">{BRAND_TAGLINE}</p>
          </div>
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
              <Spinner variant="light" className="mr-2" />
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