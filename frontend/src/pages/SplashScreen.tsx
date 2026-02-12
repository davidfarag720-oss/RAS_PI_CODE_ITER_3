import { useNavigate } from 'react-router-dom';

export function SplashScreen() {
  const navigate = useNavigate();

  const handleTap = () => {
    navigate('/select');
  };

  return (
    <div
      onClick={handleTap}
      className="min-h-screen bg-background flex flex-col items-center justify-center cursor-pointer select-none"
    >
      <h1 className="text-5xl font-bold text-text-primary mb-6">Ficio Prep</h1>
      <p className="text-text-secondary text-sm uppercase tracking-[0.3em] animate-pulse">
        TAP ANYWHERE TO BEGIN
      </p>
    </div>
  );
}
