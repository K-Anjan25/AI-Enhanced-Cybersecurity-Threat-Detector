import React, { useState, ChangeEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "react-query";
import { User } from "../../../types/user";
import { useFormik } from "formik";
import * as Yup from "yup";
import Button from "../../../components/ui/Button";
import TableWithAction from "../../../components/table/TableWithAction";
import TextInput from "../../../components/common/TextInput";
import {
  PageHeader,
  Modal,
  ConfirmDialog,
  Select,
  SkeletonTable,
} from "../../../components/ui";
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
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);

  const { data: users = [], isLoading } = useQuery<User[], Error>(
    ["adminUsers"],
    userapi.getUsers,
    {
      onError: (err: any) =>
        showError(err?.response?.data?.message || "Failed to load users"),
    }
  );

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

  const handleDelete = (user: User): void => {
    setDeleteTarget(user);
  };

  const confirmDelete = (): void => {
    if (!deleteTarget) return;
    deleteUserMutation.mutate(deleteTarget.id!);
    setDeleteTarget(null);
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 text-content-primary animate-fade-in">
      <PageHeader
        title="SOC Analyst Roster"
        description="Provision, assign tier credentials, and control platform access."
        actions={
          <Button
            type="button"
            variant="primary"
            size="md"
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-2"
          >
            <span>+</span> Add Analyst
          </Button>
        }
      />

      <div className="bg-app-surface border border-line-subtle rounded-xl shadow-card overflow-hidden">
        {isLoading ? (
          <SkeletonTable rows={5} cols={USER_COLUMNS.length + 1} />
        ) : (
          <TableWithAction
            columns={USER_COLUMNS}
            rows={users as any}
            loading={isLoading}
            onEdit={() => undefined}
            onDelete={(row) => handleDelete(row as User)}
          />
        )}
      </div>

      <Modal
        open={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Register New Analyst"
        description="Create an account with role-level access permissions."
        footer={
          <>
            <Button type="button" variant="ghost" size="md" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={createUserMutation.isLoading}
              onClick={() => formik.handleSubmit()}
            >
              {createUserMutation.isLoading ? "Creating…" : "Save Account"}
            </Button>
          </>
        }
      >
        <form onSubmit={formik.handleSubmit} className="space-y-4">
          <TextInput form={formik} name="username" label="Username" />
          <TextInput form={formik} name="email" label="Email Address" type="email" />
          <Select
            id="role"
            name="role"
            label="Access Role"
            value={formik.values.role}
            onChange={(e: ChangeEvent<HTMLSelectElement>) => formik.handleChange(e)}
            options={[
              { value: "ANALYST", label: "Tier 1 Analyst" },
              { value: "SENIOR_ANALYST", label: "Tier 2 Analyst" },
              { value: "ADMIN", label: "SOC Admin" },
              { value: "AUDITOR", label: "Auditor" },
            ]}
          />
          <TextInput form={formik} name="password" label="Temporary Password" type="password" />
        </form>
      </Modal>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Deactivate analyst"
        message={
          <>
            Deactivate access for <strong className="text-content-primary">{deleteTarget?.username}</strong>? They
            will no longer be able to sign in until re-enabled.
          </>
        }
        confirmLabel="Deactivate"
        cancelLabel="Cancel"
        loading={deleteUserMutation.isLoading}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}