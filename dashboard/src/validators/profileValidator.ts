import * as Yup from "yup";

export const profileSchema = Yup.object({
  email: Yup.string().email("Invalid email address"),
  Name: Yup.string().required("Name is required"),
  profileImageURL: Yup.string().url("Must be a valid URL"),
});

export type ProfileValues = Yup.InferType<typeof profileSchema>;

export const initialProfileValues: ProfileValues = {
  email: "",
  Name: "",
  profileImageURL: "",
};

export default {
  schema: profileSchema,
  initialValues: initialProfileValues,
};