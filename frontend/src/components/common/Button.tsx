import React from 'react';

interface ButtonProps {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  fullWidth?: boolean;
  disabled?: boolean;
  icon?: React.ReactNode;
  className?: string;
}

export function Button({
  children,
  onClick,
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  disabled = false,
  icon,
  className = '',
}: ButtonProps) {
  const baseStyles = 'inline-flex items-center justify-center font-semibold transition-all duration-150 select-none';

  const variantStyles = {
    primary: 'bg-primary text-white active:bg-green-600',
    secondary: 'bg-secondary text-white active:bg-blue-600',
    danger: 'bg-danger text-white active:bg-red-600',
    ghost: 'bg-transparent text-text-primary active:bg-gray-100',
  };

  const sizeStyles = {
    sm: 'px-4 py-2 text-sm rounded-lg min-h-[36px]',
    md: 'px-6 py-3 text-base rounded-xl min-h-[48px]',
    lg: 'px-8 py-4 text-lg rounded-2xl min-h-[56px]',
  };

  const disabledStyles = disabled ? 'opacity-50 cursor-not-allowed' : 'active:scale-95';

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`
        ${baseStyles}
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        ${disabledStyles}
        ${fullWidth ? 'w-full' : ''}
        ${className}
      `}
    >
      {icon && <span className="mr-2">{icon}</span>}
      {children}
    </button>
  );
}
