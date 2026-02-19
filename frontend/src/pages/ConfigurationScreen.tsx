import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Header, Button, Card } from '../components/common';
import { CutTypeSelector, BaySelector } from '../components/configuration';
import { useApp } from '../store/AppContext';
import { createTask } from '../api';

export function ConfigurationScreen() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const { state, refreshData } = useApp();

  const [selectedCut, setSelectedCut] = useState<string | null>(null);
  const [selectedBay, setSelectedBay] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const vegetable = state.vegetables.find((v) => v.id === id);

  // Set default selections
  useEffect(() => {
    if (vegetable && vegetable.supported_cuts.length > 0 && !selectedCut) {
      setSelectedCut(vegetable.supported_cuts[0]);
    }
    const availableBays = state.systemStatus?.available_bays ?? [];
    if (availableBays.length > 0) {
      if (!selectedBay || !availableBays.includes(selectedBay)) {
        setSelectedBay(availableBays[0]);
      }
    } else {
      setSelectedBay(null);
    }
  }, [vegetable, state.systemStatus, selectedCut, selectedBay]);

  const handleBegin = async () => {
    if (!id || !selectedCut || !selectedBay) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await createTask({
        vegetable_id: id,
        cut_type: selectedCut,
        bay_id: selectedBay,
      });
      await refreshData();
      navigate('/processing');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create task');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!vegetable) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-text-secondary">Vegetable not found</div>
      </div>
    );
  }

  const isValid = selectedCut && selectedBay;
  const imageUrl = vegetable.image_url || '/assets/ui/default.png';

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Header title="Configure Task" showBack backPath="/select" />

      <div className="flex-1 px-6 pb-24 space-y-6">
        {/* Selected vegetable card */}
        <Card padding="lg" className="flex items-center gap-4">
          <img
            src={imageUrl}
            alt={vegetable.name}
            className="w-16 h-16 object-contain"
          />
          <div>
            <div className="text-xs text-text-secondary uppercase tracking-wide">
              SELECTED
            </div>
            <div className="text-xl font-bold text-text-primary">
              {vegetable.name}
            </div>
          </div>
        </Card>

        {/* Cut type selector */}
        <CutTypeSelector
          cutTypes={state.cutTypes}
          supportedCuts={vegetable.supported_cuts}
          selectedCut={selectedCut}
          onSelect={setSelectedCut}
        />

        {/* Bay selector */}
        {state.systemStatus && (
          <BaySelector
            availableBays={state.systemStatus.available_bays}
            totalBays={state.machineConfig?.num_hoppers || 1}
            selectedBay={selectedBay}
            onSelect={setSelectedBay}
          />
        )}

        {/* Error message */}
        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-danger text-sm">
            {error}
          </div>
        )}
      </div>

      {/* Begin button */}
      <div className="fixed bottom-6 right-6">
        <Button
          onClick={handleBegin}
          variant="primary"
          size="lg"
          disabled={!isValid || isSubmitting}
          icon={
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          }
        >
          {isSubmitting ? 'Starting...' : 'Begin'}
        </Button>
      </div>
    </div>
  );
}
