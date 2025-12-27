"use client";

import React from "react";
import Link from "next/link";

type ButtonVariant = "primary" | "outline" | "sealPrimary";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    children: React.ReactNode;
    href?: string;
    asChild?: boolean;
    variant?: ButtonVariant;
}

const variantClasses: Record<ButtonVariant, string> = {
    primary: "bg-primary text-white hover:bg-primary/90",
    outline: "border border-gray-200 bg-white text-primary hover:bg-primary hover:text-white",
    sealPrimary: "bg-gradient-to-r from-primary to-secondary text-white shadow-lg hover:shadow-xl",
};

export const Button: React.FC<ButtonProps> = ({
    children,
    href,
    asChild = false,
    variant = "primary",
    className,
    onClick,
    ...rest
}) => {
    const baseClasses = "inline-flex items-center gap-2 px-6 py-2 rounded-lg font-medium transition-colors";
    const classes = `${baseClasses} ${variantClasses[variant] ?? variantClasses.primary} ${className ?? ""}`.trim();

    if (asChild && React.isValidElement(children)) {
        const childElement = children as React.ReactElement<{ className?: string }>;

        return React.cloneElement(childElement, {
            className: `${classes} ${childElement.props?.className ?? ""}`.trim(),
        });
    }

    if (href) {
        return (
            <Link href={href} className={classes}>
                {children}
            </Link>
        );
    }

    return (
        <button onClick={onClick} className={classes} {...rest}>
            {children}
        </button>
    );
};
