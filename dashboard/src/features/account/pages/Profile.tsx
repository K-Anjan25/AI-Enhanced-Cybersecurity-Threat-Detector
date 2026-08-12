import React, { useState } from "react";
import { useFormik } from "formik";
import { useQuery, useMutation, useQueryClient } from "react-query";
import Button from "../../../components/ui/Button";
import TextInput from "../../../components/common/TextInput";
import { profileSchema, initialProfileValues } from "../../../validators/profileValidator";
import userApi from "../../../api/userApi";
import { showSuccess } from "../../../utils/showSuccess";
import { showError } from "../../../utils/showError";

export interface UserProfile {
  email?: string;
  Name: string;
  profileImageURL?: string;
}

export default function Profile(): React.ReactElement {
  const queryClient = useQueryClient();

  const [passwords, setPasswords] = useState({
    currentPassword: "",
    newPassword: "",
    confirmPassword: "",
  });
  const [passwordLoading, setPasswordLoading] = useState(false);

  // Fetch profile via UserApi matching backend endpoint GET /user/profile
  const { isLoading } = useQuery({
    queryKey: ["userProfile"],
    queryFn: userApi.getProfile,
    meta: {
      onSuccess: (data: any) => {
        if (data) {
          formik.setValues({
            email: data.email || "analyst@threatdetector.local",
            Name: data.username || data.Name || localStorage.getItem("username") || "User",
            profileImageURL: data.profileImageURL || "",
          });
        }
      },
      onError: (err: any) => {
        showError(err?.response?.data?.message || "Failed to load profile details");
      },
    },
  });

  // Mutation to update profile via PUT /user/profile
  const updateProfileMutation = useMutation({
    mutationFn: (values: UserProfile) =>
      userApi.updateProfile({
        username: values.Name,
        profileImageURL: values.profileImageURL,
      }),
    onSuccess: () => {
      showSuccess("Profile details updated successfully");
      queryClient.invalidateQueries({ queryKey: ["userProfile"] });
    },
    onError: (err: any) => {
      showError(err?.response?.data?.message || "Failed to update profile");
    },
  });

  const formik = useFormik<UserProfile>({
    initialValues: initialProfileValues,
    validationSchema: profileSchema,
    onSubmit: (values) => {
      updateProfileMutation.mutate(values);
    },
  });

  // Password update handler using PUT /user/updatePassword
  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();

    if (passwords.newPassword !== passwords.confirmPassword) {
      showError("New passwords do not match.");
      return;
    }

    if (passwords.newPassword.length < 6) {
      showError("Password must be at least 6 characters long.");
      return;
    }

    setPasswordLoading(true);
    try {
      await userApi.updatePassword({
        current_password: passwords.currentPassword,
        new_password: passwords.newPassword,
      });

      showSuccess("Password updated successfully!");
      setPasswords({ currentPassword: "", newPassword: "", confirmPassword: "" });
    } catch (err: any) {
      showError(err?.response?.data?.message || "Failed to update password.");
    } finally {
      setPasswordLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="p-6 max-w-2xl mx-auto text-content-secondary text-center">
        Loading analyst profile...
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6 text-content-primary">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Analyst Profile</h1>
        <p className="text-content-secondary text-sm mt-1">
          Update your personal details, profile settings, and security credentials.
        </p>
      </div>

      {/* Profile Details Form */}
      <div className="bg-app-surface border border-line-subtle rounded-xl p-6 shadow-sm space-y-6">
        <div className="flex items-center gap-4 border-b border-line-subtle pb-6">
          <div className="w-16 h-16 rounded-full bg-app-subtle border-2 border-accent-primary flex items-center justify-center overflow-hidden">
            {formik.values.profileImageURL ? (
              <img
                src={formik.values.profileImageURL}
                alt="Profile Avatar"
                className="w-full h-full object-cover"
              />
            ) : (
              <span className="text-xl font-bold text-content-primary">
                {formik.values.Name ? formik.values.Name[0] : "A"}
              </span>
            )}
          </div>
          <div>
            <h3 className="text-base font-semibold text-content-primary">
              {formik.values.Name}
            </h3>
            <span className="text-xs text-content-secondary block">{formik.values.email}</span>
          </div>
        </div>

        <form onSubmit={formik.handleSubmit} className="space-y-4">
          <TextInput form={formik} name="Name" label="Name" />
          <TextInput form={formik} name="email" label="Email Address" type="email" />
          <TextInput form={formik} name="profileImageURL" label="Profile Avatar URL" />

          <div className="flex justify-end pt-4">
            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={updateProfileMutation.isLoading}
            >
              {updateProfileMutation.isLoading ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </form>
      </div>

      {/* Security Settings & Password Update */}
      <div className="bg-app-surface border border-line-subtle rounded-xl p-6 shadow-sm space-y-4 max-w-lg">
        <h2 className="text-lg font-semibold text-content-primary mb-2">Security Settings</h2>
        
        <form onSubmit={handlePasswordChange} className="space-y-4">
          <div>
            <label className="block text-xs text-content-secondary uppercase font-semibold mb-1">Current Password</label>
            <input
              type="password"
              value={passwords.currentPassword}
              onChange={(e) => setPasswords({ ...passwords, currentPassword: e.target.value })}
              required
              className="w-full bg-app-bg text-sm text-content-primary px-4 py-2.5 rounded-lg border border-line-subtle focus:outline-none focus:border-accent-primary transition"
              placeholder="••••••••"
            />
          </div>

          <div>
            <label className="block text-xs text-content-secondary uppercase font-semibold mb-1">New Password</label>
            <input
              type="password"
              value={passwords.newPassword}
              onChange={(e) => setPasswords({ ...passwords, newPassword: e.target.value })}
              required
              className="w-full bg-app-bg text-sm text-content-primary px-4 py-2.5 rounded-lg border border-line-subtle focus:outline-none focus:border-accent-primary transition"
              placeholder="••••••••"
            />
          </div>

          <div>
            <label className="block text-xs text-content-secondary uppercase font-semibold mb-1">Confirm New Password</label>
            <input
              type="password"
              value={passwords.confirmPassword}
              onChange={(e) => setPasswords({ ...passwords, confirmPassword: e.target.value })}
              required
              className="w-full bg-app-bg text-sm text-content-primary px-4 py-2.5 rounded-lg border border-line-subtle focus:outline-none focus:border-accent-primary transition"
              placeholder="••••••••"
            />
          </div>

          <div className="flex justify-end pt-2">
            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={passwordLoading}
            >
              {passwordLoading ? "Updating..." : "Update Password"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}