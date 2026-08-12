import * as Yup from "yup";

export const registerSchema = Yup.object({
  username: Yup.string()
    .min(3, "Username must be at least 3 characters")
    .required("Username is required"),
  email: Yup.string()
    .email("Invalid email address")
    .required("Email is required"),
  role: Yup.string().required("Role selection is required"),
  password: Yup.string()
    .min(8, "Password must be at least 8 characters")
    .required("Password is required"),
  confirmPassword: Yup.string()
    .oneOf([Yup.ref("password")], "Passwords must match")
    .required("Confirm Password is required"),
});

export type RegisterValues = Yup.InferType<typeof registerSchema>;

export const initialRegisterValues: RegisterValues = {
  username: "",
  email: "",
  role: "USER",
  password: "",
  confirmPassword: "",
};

export default {
  schema: registerSchema,
  initialValues: initialRegisterValues,
};