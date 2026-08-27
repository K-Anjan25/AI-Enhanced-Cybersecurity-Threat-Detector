import React from "react";
import { useFormik } from "formik";
import { useMutation } from "react-query";
import * as Yup from "yup";
import Button from "../../../components/ui/Button";
import BrandLogo from "../../../components/BrandLogo";
import TextInput from "../../../components/common/TextInput";
import { requestPasswordReset } from "../../../api/userApi";
import { showSuccess } from "../../../utils/showSuccess";
import { showError } from "../../../utils/showError";
import { getApiError } from "../../../utils/getApiError";

export interface ForgotPasswordProps {
  onClose: () => void;
}

const forgetPasswordSchema = Yup.object({
  email: Yup.string().email("Invalid email address").required("Email is required"),
});

export default function ForgotPassword({ onClose }: ForgotPasswordProps): React.ReactElement {
  const resetMutation = useMutation({
    mutationFn: (values: { email: string }) => requestPasswordReset(values.email),
    onSuccess: () => {
      showSuccess("Password reset instructions sent to your email.");
      onClose();
    },
    onError: (err: any) => {
      showError(getApiError(err, "Failed to process request"));
    },
  });

  const formik = useFormik({
    initialValues: { email: "" },
    validationSchema: forgetPasswordSchema,
    onSubmit: (values) => {
      resetMutation.mutate(values);
    },
  });

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-app-surface border border-line-subtle w-full max-w-sm rounded-3xl p-6 shadow-overlay space-y-4 text-content-primary">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <BrandLogo size={28} withWordmark={false} />
            <div>
              <h3 className="text-lg font-bold text-content-primary leading-tight">Reset Password</h3>
              <p className="text-[11px] font-mono uppercase tracking-[0.18em] text-content-tertiary mt-0.5">
                Night desk access
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="w-8 h-8 rounded-full flex items-center justify-center text-content-tertiary hover:text-content-primary hover:bg-app-subtle transition text-lg font-bold cursor-pointer"
          >
            &times;
          </button>
        </div>

        <p className="text-xs text-content-secondary">
          Enter your registered email address to receive a password reset link.
        </p>

        <form onSubmit={formik.handleSubmit} className="space-y-4">
          <TextInput form={formik} name="email" label="Email Address" type="email" />

          <div className="flex gap-3 pt-2">
            <Button
              type="button"
              variant="secondary"
              size="md"
              onClick={onClose}
              className="w-1/2"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={resetMutation.isLoading}
              className="w-1/2"
            >
              {resetMutation.isLoading ? "Sending..." : "Send Link"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}