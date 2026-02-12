import { useNavigate } from 'react-router-dom';
import { Header, Button } from '../components/common';
import { VegetableGrid } from '../components/vegetables';
import { useApp } from '../store/AppContext';
import { VegetableConfig } from '../api/types';

export function VegetableSelect() {
  const navigate = useNavigate();
  const { state, hasActiveTasks } = useApp();

  const handleSelect = (vegetable: VegetableConfig) => {
    navigate(`/configure/${vegetable.id}`);
  };

  const handleReturnToProcessing = () => {
    navigate('/processing');
  };

  if (state.isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-text-secondary">Loading vegetables...</div>
      </div>
    );
  }

  if (state.error) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4">
        <div className="text-danger">{state.error}</div>
        <Button onClick={() => window.location.reload()}>Retry</Button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background pb-24">
      <Header title="Select Produce" subtitle="Choose an item to process" />

      <VegetableGrid vegetables={state.vegetables} onSelect={handleSelect} />

      {hasActiveTasks() && (
        <div className="fixed bottom-6 left-0 right-0 flex justify-center px-4">
          <Button
            onClick={handleReturnToProcessing}
            variant="secondary"
            size="lg"
            className="shadow-lg"
          >
            Return to Processing
          </Button>
        </div>
      )}
    </div>
  );
}
