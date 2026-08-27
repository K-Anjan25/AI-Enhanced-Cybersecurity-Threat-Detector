import React, { ButtonHTMLAttributes, ReactNode } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const buttonVariants = cva(
  "inline-flex items-center justify-center font-medium transition-all duration-150 focus:outline-none disabled:opacity-50 active:scale-[0.98] cursor-pointer focus-visible:ring-2 focus-visible:ring-accent-primary/40",
  {
    variants: {
      variant: {
        primary:
          "bg-accent-primary text-brand-ink hover:opacity-90 border border-transparent",
        secondary: "bg-app-subtle text-content-primary hover:bg-line-bright border border-line-subtle",
        danger: "bg-status-critical/15 text-status-critical hover:bg-status-critical/25 border border-status-critical/30",
        ghost: "text-content-secondary hover:bg-app-subtle hover:text-content-primary",
      },
      size: {
        sm: "px-2.5 py-1 text-xs rounded-md",
        md: "px-4 py-2 text-sm rounded-lg",
        lg: "px-5 py-2.5 text-base rounded-xl",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  children?: ReactNode;
}

export default function Button({
  variant,
  size,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    >
      {children}
    </button>
  );
}