import { useState, useRef, useEffect } from 'react';
import { CutType } from '../../api/types';

interface CutTypeSelectorProps {
  cutTypes: CutType[];
  supportedCuts: string[];
  selectedCut: string | null;
  onSelect: (cutTypeId: string) => void;
}

export function CutTypeSelector({
  cutTypes,
  supportedCuts,
  selectedCut,
  onSelect,
}: CutTypeSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Filter to only show supported cut types
  const availableCuts = cutTypes.filter((cut) => supportedCuts.includes(cut.id));
  const selectedCutType = cutTypes.find((cut) => cut.id === selectedCut);

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

  return (
    <div className="space-y-2" ref={dropdownRef}>
      <label className="block text-sm font-medium text-text-secondary uppercase tracking-wide">
        Cut Type
      </label>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full bg-surface rounded-xl p-4 flex items-center justify-between text-left shadow-sm active:bg-gray-50"
      >
        <span className={selectedCutType ? 'text-text-primary font-medium' : 'text-text-secondary'}>
          {selectedCutType?.display_name || 'Select cut type'}
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
          {availableCuts.map((cut) => (
            <button
              key={cut.id}
              onClick={() => {
                onSelect(cut.id);
                setIsOpen(false);
              }}
              className={`w-full p-4 text-left flex flex-col active:bg-gray-50 border-b border-gray-100 last:border-b-0 ${
                selectedCut === cut.id ? 'bg-green-50' : ''
              }`}
            >
              <span className="font-medium text-text-primary">{cut.display_name}</span>
              <span className="text-sm text-text-secondary">{cut.description}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
