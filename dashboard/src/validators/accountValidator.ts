import * as yup from "yup";
import { AccountForm } from "../types/account";

const accountValidationSchema = yup.object({
  currentPassword: yup.string().required("Current password is required"),
  newPassword: yup.string().required("New password is required"),
});

const accountInitialValues: AccountForm = {
  currentPassword: "",
  newPassword: "",
};

export default {
  validationSchema: accountValidationSchema,
  initialValues: accountInitialValues,
};