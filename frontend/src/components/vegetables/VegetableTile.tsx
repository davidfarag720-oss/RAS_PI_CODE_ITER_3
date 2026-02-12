import { Card } from '../common';
import { VegetableConfig } from '../../api/types';

interface VegetableTileProps {
  vegetable: VegetableConfig;
  onClick: () => void;
}

export function VegetableTile({ vegetable, onClick }: VegetableTileProps) {
  // image_url is already the full path from backend (e.g., "/assets/ui/cucumber.jpg")
  const imageUrl = vegetable.image_url || '/assets/ui/default.png';

  return (
    <Card onClick={onClick} interactive padding="lg" className="flex flex-col items-center">
      <div className="w-24 h-24 mb-3 flex items-center justify-center">
        <img
          src={imageUrl}
          alt={vegetable.name}
          className="max-w-full max-h-full object-contain"
          onError={(e) => {
            (e.target as HTMLImageElement).src = '/assets/ui/default.png';
          }}
        />
      </div>
      <span className="text-lg font-medium text-text-primary text-center">
        {vegetable.name}
      </span>
    </Card>
  );
}
