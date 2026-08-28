import React, { ButtonHTMLAttributes, ReactNode } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const buttonVariants = cva(
  "inline-flex items-center justify-center font-medium transition-all duration-150 focus:outline-none disabled:opacity-50 disabled:pointer-events-none active:scale-[0.98] cursor-pointer focus-visible:ring-2 focus-visible:ring-accent-primary/40",
  {
    variants: {
      variant: {
        // action-button (newfile): solid signal green, ink text, hover lift + glow.
        primary:
          "bg-accent-primary text-brand-ink font-bold hover:-translate-y-0.5 hover:shadow-signal border border-transparent",
        // secondary-button (newfile): hairline border, hover → signal border + text.
        secondary:
          "bg-transparent text-content-primary border border-line-bright hover:border-accent-primary hover:text-accent-primary",
        danger:
          "bg-status-critical/15 text-status-critical hover:bg-status-critical/25 border border-status-critical/30",
        ghost: "text-content-secondary hover:bg-app-subtle hover:text-content-primary",
      },
      size: {
        sm: "px-2.5 py-1 text-xs rounded-sm",
        md: "px-4 py-2 text-sm rounded-sm",
        lg: "px-5 py-2.5 text-base rounded-sm",
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