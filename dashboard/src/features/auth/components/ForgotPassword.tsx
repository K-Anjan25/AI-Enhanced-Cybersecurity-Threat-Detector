import React from "react";
import { useFormik } from "formik";
import { useMutation } from "react-query";
import * as Yup from "yup";
import Button from "../../../components/ui/Button";
import TextInput from "../../../components/common/TextInput";
import { requestPasswordReset } from "../../../api/userApi";
import { showSuccess } from "../../../utils/showSuccess";
import { showError } from "../../../utils/showError";

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
      showError(err?.response?.data?.message || "Failed to process request");
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
      <div className="bg-app-surface border border-line-subtle w-full max-w-sm rounded-xl p-6 shadow-2xl space-y-4 text-content-primary">
        <div className="flex justify-between items-center border-b border-line-subtle pb-3">
          <h3 className="text-lg font-bold text-content-primary">Reset Password</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-content-tertiary hover:text-content-primary text-lg font-bold cursor-pointer"
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