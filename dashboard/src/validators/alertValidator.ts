import * as Yup from "yup";

export const createAlertSchema = Yup.object({
  ipAddress: Yup.string()
    .matches(
      /^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.){3}(25[0-5]|(2[0-4]|1\d|[1-9]|)\d)$/,
      "Invalid IP address"
    )
    .required("Source IP address is required"),
  threatType: Yup.string().required("Threat category is required"),
  severity: Yup.string().required("Severity level is required"),
  description: Yup.string().required("Threat summary/description is required"),
});

export type CreateAlertValues = Yup.InferType<typeof createAlertSchema>;

export const initialAlertValues: CreateAlertValues = {
  ipAddress: "",
  threatType: "DDoS Attack",
  severity: "HIGH",
  description: "",
};

export default {
  schema: createAlertSchema,
  initialValues: initialAlertValues,
};