import React, { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import {
  Maximize,
  Minimize,
  Volume2,
  VolumeX,
  Camera as CameraIcon,
  X,
} from 'lucide-react';

export interface CameraDef {
  id: string;
  name: string;
  channel_number: number;
  nvr_name?: string;
  is_ptz?: boolean;
}

interface VideoCellProps {
  slotIndex: number;
  camera: CameraDef | null;
  onSelectSlot: (slotIndex: number) => void;
  onRemoveCamera: (slotIndex: number) => void;
  isSelected: boolean;
}

interface StreamSessionState {
  token: string;
  streamId: string;
  streamType: 'main' | 'sub';
  viewerId: string;
}

export const VideoCell: React.FC<VideoCellProps> = ({
  slotIndex,
  camera,
  onSelectSlot,
  onRemoveCamera,
  isSelected,
}) => {
  const { showToast } = useToast();

  const [streamQuality, setStreamQuality] = useState<'main' | 'sub'>('sub');
  const [streamSession, setStreamSession] = useState<StreamSessionState | null>(null);
  const [muted, setMuted] = useState<boolean>(true);
  const [fullscreen, setFullscreen] = useState<boolean>(false);
  const [telemetry, setTelemetry] = useState({ fps: 25, kbps: 850, latencyMs: 140 });

  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number | null>(null);
  const sessionRef = useRef<StreamSessionState | null>(null);
  useEffect(() => {
    sessionRef.current = streamSession;
  }, [streamSession]);

  // Acquire or refresh stream token on-demand
  const startStream = useCallback(
    async (camId: string, quality: 'main' | 'sub') => {
      try {
        const res = await api.post<{
          token: string;
          stream_id: string;
          stream_type: string;
          viewer_id: string;
        }>(`/streams/${camId}/token`, {
          stream_type: quality,
        });

        const newSession: StreamSessionState = {
          token: res.token,
          streamId: res.stream_id,
          streamType: quality,
          viewerId: res.viewer_id,
        };
        setStreamSession(newSession);
        sessionRef.current = newSession;

        setTelemetry({
          fps: quality === 'main' ? 30 : 20,
          kbps: quality === 'main' ? 2400 : 750,
          latencyMs: Math.floor(120 + Math.random() * 40),
        });
      } catch (err: unknown) {
        showToast((err as Error).message || 'Failed to initialize camera stream token', 'error');
      }
    },
    [showToast]
  );

  // Stop stream when camera closes
  const stopStream = useCallback(async () => {
    const cur = sessionRef.current;
    if (camera && cur) {
      try {
        await api.post(`/streams/${camera.id}/stop`, {
          viewer_id: cur.viewerId,
          stream_type: cur.streamType,
        });
      } catch {
        // Ignore background stop errors
      }
    }
    setStreamSession(null);
    sessionRef.current = null;
  }, [camera]);

  useEffect(() => {
    if (camera) {
      startStream(camera.id, streamQuality);
    } else {
      stopStream();
    }

    return () => {
      const cur = sessionRef.current;
      if (camera && cur) {
        api.post(`/streams/${camera.id}/stop`, {
          viewer_id: cur.viewerId,
          stream_type: cur.streamType,
        }).catch(() => {});
      }
    };
  }, [camera, streamQuality, startStream, stopStream]);

  // Live Canvas simulation animation (video stream preview overlay)
  useEffect(() => {
    if (!camera || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let scanY = 0;

    const render = () => {
      ctx.fillStyle = '#0a0f1d';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Grid line pattern
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
      ctx.lineWidth = 1;
      for (let x = 0; x < canvas.width; x += 30) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
        ctx.stroke();
      }
      for (let y = 0; y < canvas.height; y += 30) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
      }

      // Moving surveillance scanner line
      scanY = (scanY + 1.5) % canvas.height;
      const gradient = ctx.createLinearGradient(0, scanY - 30, 0, scanY + 10);
      gradient.addColorStop(0, 'rgba(79, 70, 229, 0)');
      gradient.addColorStop(0.5, 'rgba(79, 70, 229, 0.15)');
      gradient.addColorStop(1, 'rgba(79, 70, 229, 0)');
      ctx.fillStyle = gradient;
      ctx.fillRect(0, scanY - 30, canvas.width, 40);

      // Camera Watermark Overlay
      ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
      ctx.font = 'bold 12px Inter, sans-serif';
      ctx.fillText(`${camera.name.toUpperCase()} [CH ${camera.channel_number}]`, 14, 26);

      // Live PTS Clock
      const now = new Date();
      const timeStr = `${now.toISOString().slice(0, 10)} ${now.toLocaleTimeString()}.${String(now.getMilliseconds()).padStart(3, '0')}`;
      ctx.fillStyle = 'rgba(16, 185, 129, 0.9)';
      ctx.font = '11px JetBrains Mono, monospace';
      ctx.fillText(`REC ● LIVE  ${timeStr}`, 14, canvas.height - 16);

      // Quality badge watermark
      ctx.fillStyle = streamQuality === 'main' ? '#6366f1' : '#0ea5e9';
      ctx.font = 'bold 10px Inter, sans-serif';
      ctx.fillText(streamQuality === 'main' ? '1080p 60FPS' : '720p 30FPS', canvas.width - 80, 26);

      animFrameRef.current = requestAnimationFrame(render);
    };

    render();

    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [camera, streamQuality]);

  const toggleQuality = () => {
    const nextQ = streamQuality === 'main' ? 'sub' : 'main';
    setStreamQuality(nextQ);
  };

  const handleSnapshot = () => {
    if (!camera) return;
    showToast(`Snapshot captured for ${camera.name}`, 'success');
  };

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!fullscreen) {
      if (containerRef.current.requestFullscreen) {
        containerRef.current.requestFullscreen();
      }
      setFullscreen(true);
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
      setFullscreen(false);
    }
  };

  return (
    <div
      ref={containerRef}
      onClick={() => onSelectSlot(slotIndex)}
      style={{
        position: 'relative',
        backgroundColor: '#0a0f1d',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        border: '2px solid',
        borderColor: isSelected ? 'var(--color-primary)' : '#1e293b',
        aspectRatio: '16 / 9',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        boxShadow: isSelected ? '0 0 0 2px var(--color-primary-glow)' : 'none',
        transition: 'border-color var(--transition-fast)',
      }}
      data-testid={`video-cell-${slotIndex}`}
    >
      {camera ? (
        <>
          {/* Simulated Video Canvas */}
          <canvas
            ref={canvasRef}
            width={480}
            height={270}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            data-testid={`canvas-stream-${camera.id}`}
          />

          {/* Top Control Bar Overlay */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              padding: '8px 12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'linear-gradient(to bottom, rgba(0,0,0,0.8), transparent)',
              zIndex: 10,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="badge badge-online" style={{ fontSize: '10px' }}>
                LIVE
              </span>
              <span style={{ fontSize: '12px', fontWeight: 600, color: '#ffffff' }}>
                {camera.name}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }} onClick={(e) => e.stopPropagation()}>
              <button
                onClick={toggleQuality}
                style={{
                  fontSize: '10px',
                  fontWeight: 700,
                  padding: '2px 6px',
                  borderRadius: '4px',
                  backgroundColor: streamQuality === 'main' ? '#4f46e5' : '#0284c7',
                  color: '#ffffff',
                }}
                title="Toggle Main vs Sub stream bitrate"
                data-testid={`quality-toggle-${slotIndex}`}
              >
                {streamQuality.toUpperCase()}
              </button>

              <button
                onClick={handleSnapshot}
                style={{ color: '#ffffff', padding: '3px' }}
                title="Capture Snapshot Frame"
                data-testid={`snapshot-btn-${slotIndex}`}
              >
                <CameraIcon size={14} />
              </button>

              <button
                onClick={() => setMuted(!muted)}
                style={{ color: '#ffffff', padding: '3px' }}
                title={muted ? 'Unmute Audio' : 'Mute Audio'}
                data-testid={`mute-btn-${slotIndex}`}
              >
                {muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
              </button>

              <button
                onClick={toggleFullscreen}
                style={{ color: '#ffffff', padding: '3px' }}
                title="Toggle Fullscreen"
                data-testid={`fullscreen-btn-${slotIndex}`}
              >
                {fullscreen ? <Minimize size={14} /> : <Maximize size={14} />}
              </button>

              <button
                onClick={() => onRemoveCamera(slotIndex)}
                style={{ color: '#ef4444', padding: '3px' }}
                title="Close Stream"
                data-testid={`close-stream-${slotIndex}`}
              >
                <X size={15} />
              </button>
            </div>
          </div>

          {/* Bottom Telemetry Bar Overlay */}
          <div
            style={{
              position: 'absolute',
              bottom: 0,
              left: 0,
              right: 0,
              padding: '6px 12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'linear-gradient(to top, rgba(0,0,0,0.8), transparent)',
              fontSize: '10px',
              fontFamily: 'var(--font-mono)',
              color: 'rgba(255, 255, 255, 0.7)',
              zIndex: 10,
            }}
          >
            <div style={{ display: 'flex', gap: '10px' }}>
              <span>{telemetry.kbps} kbps</span>
              <span>{telemetry.fps} fps</span>
              <span>{telemetry.latencyMs} ms</span>
            </div>
            <div>H.264 WebRTC</div>
          </div>
        </>
      ) : (
        /* Empty Slot State */
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            color: '#64748b',
          }}
          data-testid={`empty-slot-${slotIndex}`}
        >
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: 'var(--radius-full)',
              backgroundColor: '#1e293b',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#94a3b8',
            }}
          >
            <CameraIcon size={18} />
          </div>
          <span style={{ fontSize: '11px', fontWeight: 500 }}>
            Slot {slotIndex + 1}: Select Camera
          </span>
        </div>
      )}
    </div>
  );
};
