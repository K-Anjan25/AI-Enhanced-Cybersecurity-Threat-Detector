import React from "react";
import { useFormik } from "formik";
import { useMutation } from "react-query";
import { useNavigate } from "react-router-dom";
import TextInput from "../../../components/common/TextInput";
import { PageHeader, Spinner } from "../../../components/ui";
import accountForm from "../../../validators/accountValidator";
import { UserApi } from "../../../api/userApi";
import { setToken } from "../../../utils/token";
import { showSuccess } from "../../../utils/showSuccess";
import { showError } from "../../../utils/showError";
import { getApiError } from "../../../utils/getApiError";

export default function Account(): React.ReactElement {
  const navigate = useNavigate();

  const updateMutation = useMutation(UserApi.updatePassword, {
    onSuccess: (res: any) => {
      setToken({
        accessToken: res.accessToken || res.access_token,
        refreshToken: res.refreshToken || res.refresh_token,
      });
      showSuccess("Your Password has been updated successfully");
      navigate("/");
    },
    onError: (err: any) => {
      showError(getApiError(err, "Failed to update password"));
    },
  });

  const form = useFormik({
    initialValues: accountForm.initialValues,
    validationSchema: accountForm.validationSchema,
    onSubmit: (values) => {
      updateMutation.mutate({
        current_password: (values as any).currentPassword,
        new_password: (values as any).newPassword,
      });
    },
  });

  return (
    <div className="max-w-md w-full mx-auto space-y-6">
      <PageHeader
        title="Change Password"
        backTo="/profile"
        description="Update your security credentials. You'll stay signed in with your new password."
      />
      <div className="p-6 bg-app-surface rounded-2xl border border-line-subtle shadow-card">

      <form onSubmit={form.handleSubmit} className="flex flex-col gap-4">
        <TextInput
          name="currentPassword"
          label="Current Password"
          type="password"
          value={form.values.currentPassword}
          onChange={form.handleChange}
          onBlur={form.handleBlur}
          error={
            form.touched.currentPassword &&
            (form.errors.currentPassword as string)
          }
        />

        <TextInput
          name="newPassword"
          label="New Password"
          type="password"
          value={form.values.newPassword}
          onChange={form.handleChange}
          onBlur={form.handleBlur}
          error={
            form.touched.newPassword && (form.errors.newPassword as string)
          }
        />

        <button
          type="submit"
          disabled={updateMutation.isLoading}
          className="w-full mt-2 py-2.5 px-4 bg-brand-gradient hover:opacity-90 disabled:opacity-60 disabled:cursor-not-allowed text-brand-ink font-medium rounded-full transition-colors flex items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
        >
          {updateMutation.isLoading ? (
            <Spinner variant="light" className="mr-2" />
          ) : null}
          {updateMutation.isLoading ? "Updating..." : "Change Password"}
        </button>
      </form>
      </div>
    </div>
  );
}