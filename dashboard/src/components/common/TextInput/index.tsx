import React, { InputHTMLAttributes } from "react";

export interface TextInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "form"> {
  form?: any;
  name: string;
  label?: string;
  error?: string | boolean;
}

export default function TextInput({
  form,
  label,
  name,
  type = "text",
  value,
  onChange,
  onBlur,
  placeholder,
  error,
  ...props
}: TextInputProps) {
  const inputValue = value ?? form?.values?.[name] ?? "";
  const inputError = error ?? (form?.touched?.[name] && form?.errors?.[name]);

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {label && (
        <label htmlFor={name} className="text-xs font-semibold text-content-secondary">
          {label}
        </label>
      )}
      <input
        id={name}
        name={name}
        type={type}
        value={inputValue}
        onChange={onChange || form?.handleChange}
        onBlur={onBlur || form?.handleBlur}
        placeholder={placeholder}
        className={`w-full bg-app-bg border rounded-lg px-3.5 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none transition ${
          inputError
            ? "border-status-critical focus:border-status-critical"
            : "border-line-subtle focus:border-accent-primary"
        }`}
        {...props}
      />
      {typeof inputError === "string" && inputError && (
        <span className="text-xs text-status-critical mt-0.5">{inputError}</span>
      )}
    </div>
  );
}