import * as Yup from "yup";
import { LoginForm } from "../types/user";

export const loginSchema = Yup.object({
  identifier: Yup.string().required("Email or Username is required"),
  password: Yup.string()
    .min(6, "Password must be at least 6 characters")
    .required("Password is required"),
});

export const initialValues: LoginForm = {
  identifier: "",
  password: "",
};

export default {
  loginSchema,
  initialValues,
};