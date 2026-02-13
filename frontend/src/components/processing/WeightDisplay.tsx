interface WeightDisplayProps {
  weight: number;
  targetWeight?: number;
  itemCount: number;
  vegetableName: string;
}

export function WeightDisplay({ weight, targetWeight, itemCount, vegetableName }: WeightDisplayProps) {
  const progress = targetWeight ? Math.min((weight / targetWeight) * 100, 100) : 0;

  // Pluralize vegetable name
  const itemLabel = itemCount === 1 ? vegetableName : `${vegetableName}s`;

  return (
    <div className="bg-surface rounded-2xl p-6 shadow-sm flex-1">
      <div className="text-sm text-text-secondary uppercase tracking-wide mb-2">
        Weight Processed
      </div>
      <div className="text-5xl font-bold text-text-primary mb-2">
        {weight.toFixed(2)} <span className="text-2xl font-normal">kg</span>
      </div>
      <div className="text-lg text-text-secondary mb-4">
        {itemCount} {itemLabel} processed
      </div>

      {targetWeight && (
        <div className="space-y-2">
          <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="text-sm text-text-secondary text-right">
            {progress.toFixed(0)}% of {targetWeight} kg target
          </div>
        </div>
      )}
    </div>
  );
}
