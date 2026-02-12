import { VegetableTile } from './VegetableTile';
import { VegetableConfig } from '../../api/types';

interface VegetableGridProps {
  vegetables: VegetableConfig[];
  onSelect: (vegetable: VegetableConfig) => void;
}

export function VegetableGrid({ vegetables, onSelect }: VegetableGridProps) {
  return (
    <div className="grid grid-cols-2 gap-4 p-4">
      {vegetables.map((vegetable) => (
        <VegetableTile
          key={vegetable.id}
          vegetable={vegetable}
          onClick={() => onSelect(vegetable)}
        />
      ))}
    </div>
  );
}
