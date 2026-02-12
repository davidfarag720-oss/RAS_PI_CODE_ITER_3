import React from 'react';
import { useNavigate } from 'react-router-dom';

interface HeaderProps {
  title: string;
  subtitle?: string;
  showBack?: boolean;
  backPath?: string;
  rightElement?: React.ReactNode;
}

export function Header({
  title,
  subtitle,
  showBack = false,
  backPath,
  rightElement,
}: HeaderProps) {
  const navigate = useNavigate();

  const handleBack = () => {
    if (backPath) {
      navigate(backPath);
    } else {
      navigate(-1);
    }
  };

  return (
    <header className="flex items-center justify-between px-6 py-4">
      <div className="flex items-center gap-4">
        {showBack && (
          <button
            onClick={handleBack}
            className="w-10 h-10 flex items-center justify-center rounded-full active:bg-gray-200 transition-colors"
            aria-label="Go back"
          >
            <svg
              className="w-6 h-6 text-text-primary"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 19l-7-7 7-7"
              />
            </svg>
          </button>
        )}
        <div>
          <h1 className="text-2xl font-bold text-text-primary">{title}</h1>
          {subtitle && (
            <p className="text-text-secondary text-sm mt-0.5">{subtitle}</p>
          )}
        </div>
      </div>
      {rightElement && <div>{rightElement}</div>}
    </header>
  );
}
