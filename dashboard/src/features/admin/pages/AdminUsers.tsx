import React, { useState, ChangeEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "react-query";
import { User } from "../../../types/user";
import { useFormik } from "formik";
import * as Yup from "yup";
import Button from "../../../components/ui/Button";
import TableWithAction from "../../../components/table/TableWithAction";
import TextInput from "../../../components/common/TextInput";
import { USER_COLUMNS } from "../../../constants/tableColumns";
import userapi from "../../../api/userApi";
import { showSuccess } from "../../../utils/showSuccess";
import { showError } from "../../../utils/showError";

export interface NewUserPayload {
  username: string;
  email: string;
  role: string;
  password?: string;
}

const registerSchema = Yup.object({
  username: Yup.string().min(3, "Min 3 characters").required("Username required"),
  email: Yup.string().email("Invalid email").required("Email required"),
  role: Yup.string().required("Role required"),
  password: Yup.string().min(6, "Min 6 characters").required("Password required"),
});

export default function AdminUsers(): React.ReactElement {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);

  // Fetch users list
  const { data: users = [], isLoading } = useQuery<User[], Error>(
    ["adminUsers"],
    userapi.getUsers,
    {
      onError: (err: any) =>
        showError(err?.response?.data?.message || "Failed to load users"),
    }
  );

  // Create User Mutation
  const createUserMutation = useMutation<User, Error, NewUserPayload>(
    userapi.createUser,
    {
      onSuccess: () => {
        showSuccess("Analyst account created successfully");
        queryClient.invalidateQueries(["adminUsers"]);
        setIsModalOpen(false);
        formik.resetForm();
      },
      onError: (err: any) => {
        showError(err?.response?.data?.message || "Failed to create account");
      },
    }
  );

  // Delete/Deactivate User Mutation
  const deleteUserMutation = useMutation<{ success: boolean }, Error, string | number>(
    userapi.deleteUser,
    {
      onSuccess: () => {
        showSuccess("User account status updated");
        queryClient.invalidateQueries(["adminUsers"]);
      },
      onError: (err: any) => {
        showError(err?.response?.data?.message || "Failed to update user");
      },
    }
  );

  const formik = useFormik<NewUserPayload>({
    initialValues: {
      username: "",
      email: "",
      role: "USER",
      password: "",
    },
    validationSchema: registerSchema,
    onSubmit: (values) => {
      createUserMutation.mutate(values);
    },
  });

  const handleEdit = (user: User): void => {
    // Navigate to user edit page or open edit modal
  };

  const handleDelete = (user: User): void => {
    if (window.confirm(`Deactivate access for analyst ${user.username}?`)) {
      deleteUserMutation.mutate(user.id!);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 text-content-primary">
      {/* Header & Add User Action */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            SOC Analyst Roster
          </h1>
          <p className="text-content-secondary text-sm mt-1">
            Provision, assign tier credentials, and control platform access.
          </p>
        </div>
        <Button
          type="button"
          variant="primary"
          size="md"
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2"
        >
          <span>+</span> Add Analyst
        </Button>
      </div>

      {/* Users Table */}
      <div className="bg-app-surface border border-line-subtle rounded-xl shadow-sm overflow-hidden">
        <TableWithAction
          columns={USER_COLUMNS}
          rows={users as any}
          loading={isLoading}
          onEdit={(row) => handleEdit(row as User)}
          onDelete={(row) => handleDelete(row as User)}
        />
      </div>

      {/* Add User Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-app-surface border border-line-subtle w-full max-w-md rounded-xl p-6 shadow-2xl space-y-4">
            <div className="flex justify-between items-center border-b border-line-subtle pb-3">
              <h3 className="text-lg font-bold text-content-primary">Register New Analyst</h3>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="text-content-tertiary hover:text-content-primary text-lg font-bold cursor-pointer"
              >
                &times;
              </button>
            </div>

            <form onSubmit={formik.handleSubmit} className="space-y-4">
              <TextInput form={formik} name="username" label="Username" />
              <TextInput
                form={formik}
                name="email"
                label="Email Address"
                type="email"
              />

              <div className="flex flex-col gap-1">
                <label
                  htmlFor="role"
                  className="text-xs font-semibold text-content-secondary"
                >
                  Access Role
                </label>
                <select
                  id="role"
                  name="role"
                  value={formik.values.role}
                  onChange={(e: ChangeEvent<HTMLSelectElement>) =>
                    formik.handleChange(e)
                  }
                  className="bg-app-bg border border-line-subtle text-content-primary rounded-lg p-2.5 text-sm focus:outline-none focus:border-accent-primary transition cursor-pointer"
                >
                  <option value="ANALYST">Tier 1 Analyst</option>
                  <option value="SENIOR_ANALYST">Tier 2 Analyst</option>
                  <option value="ADMIN">SOC Admin</option>
                  <option value="AUDITOR">Auditor</option>
                </select>
              </div>

              <TextInput
                form={formik}
                name="password"
                label="Temporary Password"
                type="password"
              />

              <div className="flex gap-3 pt-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="md"
                  onClick={() => setIsModalOpen(false)}
                  className="w-1/2"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="md"
                  disabled={createUserMutation.isLoading}
                  className="w-1/2"
                >
                  {createUserMutation.isLoading ? "Creating..." : "Save Account"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}