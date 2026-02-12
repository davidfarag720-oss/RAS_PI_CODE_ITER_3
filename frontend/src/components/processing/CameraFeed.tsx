import { useCameraFeed } from '../../hooks';

interface CameraFeedProps {
  bayId: number;
  vegetableName: string;
  cutType: string;
}

export function CameraFeed({ bayId, vegetableName, cutType }: CameraFeedProps) {
  const { imageUrl, isConnected, fps } = useCameraFeed();

  const timestamp = new Date().toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  return (
    <div className="relative bg-gray-900 rounded-2xl overflow-hidden aspect-video">
      {/* Camera feed or placeholder */}
      {imageUrl ? (
        <img
          src={imageUrl}
          alt="Camera feed"
          className="w-full h-full object-cover"
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center">
          <span className="text-gray-500">
            {isConnected ? 'Waiting for camera...' : 'Camera disconnected'}
          </span>
        </div>
      )}

      {/* Top overlay bar */}
      <div className="absolute top-0 left-0 right-0 p-3 flex justify-between items-start">
        <div className="text-white text-xs font-mono bg-black/50 px-2 py-1 rounded">
          <span>CAM_01</span>
          <span className="mx-2">•</span>
          <span className="text-red-500">REC</span>
          <span className="mx-2">•</span>
          <span>{timestamp}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-white text-xs bg-black/50 px-2 py-1 rounded">
            {fps} FPS
          </span>
          <div className="flex items-center gap-1 text-red-500">
            <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
            <span className="text-xs font-semibold">LIVE</span>
          </div>
        </div>
      </div>

      {/* Bottom overlay bar */}
      <div className="absolute bottom-0 left-0 right-0 p-3">
        <div className="flex justify-between">
          <div className="text-white text-xs bg-black/50 px-2 py-1 rounded">
            <div>AI DETECTION: ACTIVE</div>
            <div>THROUGHPUT: OPTIMAL</div>
          </div>
          <div className="text-white text-xs bg-black/50 px-2 py-1 rounded text-right">
            <div>Bay {bayId}</div>
            <div>{vegetableName} ({cutType})</div>
          </div>
        </div>
      </div>
    </div>
  );
}
