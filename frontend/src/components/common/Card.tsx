import React from 'react';

interface CardProps {
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  interactive?: boolean;
}

export function Card({
  children,
  onClick,
  className = '',
  padding = 'md',
  interactive = false,
}: CardProps) {
  const paddingStyles = {
    none: '',
    sm: 'p-3',
    md: 'p-4',
    lg: 'p-6',
  };

  const interactiveStyles = interactive
    ? 'cursor-pointer active:scale-[0.98] transition-transform duration-150'
    : '';

  const Component = onClick ? 'button' : 'div';

  return (
    <Component
      onClick={onClick}
      className={`
        bg-surface rounded-2xl shadow-sm
        ${paddingStyles[padding]}
        ${interactiveStyles}
        ${className}
      `}
    >
      {children}
    </Component>
  );
}
