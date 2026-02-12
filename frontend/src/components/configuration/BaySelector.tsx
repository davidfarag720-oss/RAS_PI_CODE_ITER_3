import { useState, useRef, useEffect } from 'react';

interface BaySelectorProps {
  availableBays: number[];  // Bay IDs that are available
  totalBays: number;        // Total number of bays (e.g., 4)
  selectedBay: number | null;
  onSelect: (bayId: number) => void;
}

export function BaySelector({ availableBays, totalBays, selectedBay, onSelect }: BaySelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const isSelected = selectedBay !== null;

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Generate all bay IDs from 1 to totalBays
  const allBays = Array.from({ length: totalBays }, (_, i) => i + 1);

  return (
    <div className="space-y-2" ref={dropdownRef}>
      <label className="block text-sm font-medium text-text-secondary uppercase tracking-wide">
        Bay Number
      </label>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full bg-surface rounded-xl p-4 flex items-center justify-between text-left shadow-sm active:bg-gray-50"
      >
        <span className={isSelected ? 'text-text-primary font-medium' : 'text-text-secondary'}>
          {isSelected ? `Bay ${selectedBay}` : 'Select bay'}
        </span>
        <svg
          className={`w-5 h-5 text-text-secondary transition-transform ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="bg-surface rounded-xl shadow-lg overflow-hidden border border-gray-100">
          {allBays.map((bayId) => {
            const isAvailable = availableBays.includes(bayId);
            const isDisabled = !isAvailable;

            return (
              <button
                key={bayId}
                onClick={() => {
                  if (!isDisabled) {
                    onSelect(bayId);
                    setIsOpen(false);
                  }
                }}
                disabled={isDisabled}
                className={`w-full p-4 text-left flex items-center justify-between active:bg-gray-50 border-b border-gray-100 last:border-b-0 ${
                  selectedBay === bayId ? 'bg-green-50' : ''
                } ${isDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <span className="font-medium text-text-primary">Bay {bayId}</span>
                <span className={`text-sm ${isAvailable ? 'text-green-600' : 'text-red-600'}`}>
                  {isAvailable ? 'Available' : 'In Use'}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
