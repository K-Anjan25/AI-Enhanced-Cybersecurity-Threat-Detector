import React from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

export interface BackButtonProps {
  /** Route to go back to; defaults to browser history back (-1). */
  to?: string | number;
  label?: string;
  className?: string;
}

/** Secondary "back" affordance for deep/detail views (replaces the tab trap). */
export const BackButton: React.FC<BackButtonProps> = ({ to, label = "Back", className }) => {
  const navigate = useNavigate();
  const goBack = () => {
    if (typeof to === "string") {
      navigate(to);
    } else {
      navigate(to ?? -1);
    }
  };
  return (
    <button
      type="button"
      onClick={goBack}
      className={`inline-flex items-center gap-1.5 text-sm font-medium text-content-secondary hover:text-content-primary transition px-2 -ml-2 py-1 rounded-md cursor-pointer ${className ?? ""}`}
      aria-label={label}
    >
      <ArrowLeft size={15} aria-hidden />
      {label}
    </button>
  );
};

export default BackButton;