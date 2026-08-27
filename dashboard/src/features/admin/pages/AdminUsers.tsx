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
import AdminApi, { OrgInfo, AdminRosterMember } from "../../../api/adminApi";
import { showSuccess } from "../../../utils/showSuccess";
import { showError } from "../../../utils/showError";
import { getApiError } from "../../../utils/getApiError";

export interface NewUserPayload {
  username: string;
  email: string;
  role: string;
  password?: string;
  org_id?: number | string;
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
  const [orgFilter, setOrgFilter] = useState<string>("");
  const [editTarget, setEditTarget] = useState<AdminRosterMember | null>(null);
  const [editRole, setEditRole] = useState("USER");
  const [editActive, setEditActive] = useState(true);

  const { data: orgs = { data: [] as OrgInfo[] } } = useQuery<{ data: OrgInfo[] }>(["adminOrgs"], AdminApi.fetchOrgs, {
    onError: () => showError("Failed to load tenants"),
  });

  const { data: users = [], isLoading } = useQuery<AdminRosterMember[], Error>(
    ["adminUsers", orgFilter],
    () => AdminApi.fetchRoster(orgFilter ? { org_id: orgFilter } : {}),
    {
      onError: (err: any) =>
        showError(err?.response?.data?.detail || "Failed to load users"),
    }
  );

  const createUserMutation = useMutation<AdminRosterMember, Error, NewUserPayload>(
    AdminApi.createRosterUser,
    {
      onSuccess: () => {
        showSuccess("Analyst account created successfully");
        queryClient.invalidateQueries(["adminUsers"]);
        setIsModalOpen(false);
        formik.resetForm();
      },
      onError: (err: any) => {
        showError(getApiError(err, "Failed to create account"));
      },
    }
  );

  const deleteUserMutation = useMutation<{ success: boolean }, Error, string | number>(
    async (id) => AdminApi.deleteRosterUser(Number(id)),
    {
      onSuccess: () => {
        showSuccess("User account deleted");
        queryClient.invalidateQueries(["adminUsers"]);
      },
      onError: (err: any) => {
        showError(getApiError(err, "Failed to delete user"));
      },
    }
  );

  const updateUserMutation = useMutation<
    Record<string, any>,
    Error,
    { id: number; role: string; is_active: boolean }
  >(
    ({ id, role, is_active }) => AdminApi.updateRosterUser(id, { role, is_active }),
    {
      onSuccess: () => {
        showSuccess("User account updated");
        queryClient.invalidateQueries(["adminUsers"]);
        setEditTarget(null);
      },
      onError: (err: any) => {
        showError(getApiError(err, "Failed to update user"));
      },
    }
  );

  const formik = useFormik<NewUserPayload>({
    initialValues: {
      username: "",
      email: "",
      role: "USER",
      password: "",
      org_id: "",
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

  const openEdit = (user: AdminRosterMember): void => {
    setEditTarget(user);
    setEditRole(user.role || "USER");
    setEditActive(user.is_active !== false);
  };

  const confirmEdit = (): void => {
    if (!editTarget) return;
    updateUserMutation.mutate({
      id: editTarget.id,
      role: editRole,
      is_active: editActive,
    });
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 text-content-primary animate-fade-in">
      <PageHeader
        title="SOC Analyst Roster"
        description="Provision, assign tier credentials, and control platform access."
        backTo="/admin"
        crumbs={[{ label: "Admin", to: "/admin" }, { label: "Analyst Roster" }]}
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

      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="w-full sm:w-64">
          <Select
            id="org-filter"
            aria-label="Filter by tenant"
            value={orgFilter}
            onChange={(e) => setOrgFilter(e.target.value)}
            options={[
              { value: "", label: "All tenants" },
              ...orgs.data.map((o) => ({ value: String(o.id), label: o.name })),
            ]}
          />
        </div>
        <p className="text-xs text-content-tertiary">
          {users.length} user{users.length === 1 ? "" : "s"} · {orgFilter ? "filtered view" : "cross-tenant roster"}
        </p>
      </div>

      <div className="bg-app-surface border border-line-subtle rounded-2xl shadow-card overflow-hidden">
        {isLoading ? (
          <SkeletonTable rows={5} cols={USER_COLUMNS.length + 2} bare />
        ) : (
          <TableWithAction
            columns={[
              ...USER_COLUMNS,
              { id: "org_name", label: "Tenant" },
            ]}
            rows={(users as any).map((u: AdminRosterMember) => ({
              ...u,
              status: u.is_blocked ? "Blocked" : u.is_active ? "Active" : "Inactive",
            }))}
            loading={isLoading}
            onEdit={(row) => openEdit(row as AdminRosterMember)}
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
            id="org_id"
            name="org_id"
            label="Tenant"
            value={formik.values.org_id}
            onChange={(e: ChangeEvent<HTMLSelectElement>) => formik.handleChange(e)}
            options={[
              { value: "", label: "Current organization (default)" },
              ...orgs.data.map((o) => ({ value: String(o.id), label: o.name })),
            ]}
          />
          <Select
            id="role"
            name="role"
            label="Access Role"
            value={formik.values.role}
            onChange={(e: ChangeEvent<HTMLSelectElement>) => formik.handleChange(e)}
            options={[
              { value: "USER", label: "Observer (USER)" },
              { value: "ANALYST", label: "Tier 1 Analyst (ANALYST)" },
              { value: "ADMIN", label: "SOC Admin (ADMIN)" },
            ]}
          />
          <TextInput form={formik} name="password" label="Temporary Password" type="password" />
        </form>
      </Modal>

      <Modal
        open={editTarget !== null}
        onClose={() => setEditTarget(null)}
        title="Edit Analyst"
        description={`Update access for ${editTarget?.username ?? ""}. Role and active state are persisted; the account is never touched.`}
        footer={
          <>
            <Button type="button" variant="ghost" size="md" onClick={() => setEditTarget(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              variant="primary"
              size="md"
              disabled={updateUserMutation.isLoading}
              onClick={confirmEdit}
            >
              {updateUserMutation.isLoading ? "Saving…" : "Save Changes"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-content-secondary mb-1">Username</label>
              <input
                type="text"
                value={editTarget?.username ?? ""}
                readOnly
                className="w-full bg-app-bg border border-line-subtle rounded-lg px-3.5 py-2 text-sm text-content-tertiary"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-content-secondary mb-1">Email</label>
              <input
                type="text"
                value={editTarget?.email ?? ""}
                readOnly
                className="w-full bg-app-bg border border-line-subtle rounded-lg px-3.5 py-2 text-sm text-content-tertiary"
              />
            </div>
          </div>
          <Select
            id="edit-role"
            label="Access Role"
            value={editRole}
            onChange={(e: ChangeEvent<HTMLSelectElement>) => setEditRole(e.target.value)}
            options={[
              { value: "USER", label: "Observer (USER)" },
              { value: "ANALYST", label: "Tier 1 Analyst (ANALYST)" },
              { value: "ADMIN", label: "SOC Admin (ADMIN)" },
            ]}
          />
          <label className="flex items-center justify-between cursor-pointer pt-1">
            <span className="text-sm text-content-primary">Account active</span>
            <input
              type="checkbox"
              checked={editActive}
              onChange={(e) => setEditActive(e.target.checked)}
              className="w-4 h-4 rounded border-line-subtle bg-app-bg text-accent-primary focus:ring-0"
            />
          </label>
          <p className="text-xs text-content-tertiary">
            Changing the role updates the ABAC clearance and permissions immediately. To block sign-in
            entirely, delete the account or set active off.
          </p>
        </div>
      </Modal>

      <ConfirmDialog
        open={deleteTarget !== null}
        tone="danger"
        title="Delete analyst"
        message={
          <>
            Permanently delete the account for{" "}
            <strong className="text-content-primary">{deleteTarget?.username}</strong>? This removes the user and
            their alert history links. Use Block instead to keep the account but revoke sign-in.
          </>
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        loading={deleteUserMutation.isLoading}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}