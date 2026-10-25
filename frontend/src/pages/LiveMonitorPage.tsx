import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useToast } from '../context/ToastContext';
import { VideoCell } from '../components/streaming/VideoCell';
import type { CameraDef } from '../components/streaming/VideoCell';
import {
  Video,
  Grid2X2,
  Square,
  Grid3X3,
  LayoutGrid,
  Trash2,
  Search,
  Camera as CameraIcon,
} from 'lucide-react';

type GridLayout = '1x1' | '2x2' | '3x3' | '4x4';

interface CameraItemFromApi {
  id: string;
  name: string;
  channel_number: number;
  nvr_id: string;
  nvr_name?: string;
  is_ptz: boolean;
  status: string;
}

export const LiveMonitorPage: React.FC = () => {
  const { showToast } = useToast();

  const [layout, setLayout] = useState<GridLayout>('2x2');
  const [selectedSlot, setSelectedSlot] = useState<number>(0);
  const [cameras, setCameras] = useState<CameraItemFromApi[]>([]);
  const [loadingCams, setLoadingCams] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Assigned camera slots map: slotIndex -> CameraDef | null
  const [slotMap, setSlotMap] = useState<Record<number, CameraDef | null>>({});

  const totalSlots =
    layout === '1x1' ? 1 : layout === '2x2' ? 4 : layout === '3x3' ? 9 : 16;

  const fetchAvailableCameras = useCallback(async () => {
    try {
      setLoadingCams(true);
      // Fetch cameras from backend
      const data = await api.get<CameraItemFromApi[]>('/cameras').catch(async () => {
        // Fallback: list through NVRs if /cameras isn't a top-level route
        const nvrs = await api.get<Array<{ id: string; name: string }>>('/nvrs');
        const allCams: CameraItemFromApi[] = [];
        for (const n of nvrs) {
          const nvrCams = await api.get<CameraItemFromApi[]>(`/nvrs/${n.id}/cameras`);
          allCams.push(...nvrCams.map((c) => ({ ...c, nvr_name: n.name })));
        }
        return allCams;
      });
      setCameras(data);
    } catch {
      showToast('Failed to load camera channels', 'error');
    } finally {
      setLoadingCams(false);
    }
  }, [showToast]);

  useEffect(() => {
    fetchAvailableCameras();
  }, [fetchAvailableCameras]);

  const handleAssignCamera = (cam: CameraItemFromApi) => {
    setSlotMap((prev) => ({
      ...prev,
      [selectedSlot]: {
        id: cam.id,
        name: cam.name,
        channel_number: cam.channel_number,
        nvr_name: cam.nvr_name,
        is_ptz: cam.is_ptz,
      },
    }));

    showToast(`Assigned ${cam.name} to Slot ${selectedSlot + 1}`, 'info');

    // Auto-advance to next empty slot
    for (let i = 0; i < totalSlots; i++) {
      const nextIndex = (selectedSlot + 1 + i) % totalSlots;
      if (!slotMap[nextIndex]) {
        setSelectedSlot(nextIndex);
        break;
      }
    }
  };

  const handleRemoveCamera = (slotIndex: number) => {
    setSlotMap((prev) => {
      const next = { ...prev };
      delete next[slotIndex];
      return next;
    });
  };

  const handleClearAll = () => {
    setSlotMap({});
    showToast('All camera streams closed', 'info');
  };

  const filteredCameras = cameras.filter(
    (c) =>
      c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      String(c.channel_number).includes(searchQuery)
  );

  return (
    <div data-testid="live-monitor-page" style={{ height: 'calc(100vh - 112px)', display: 'flex', flexDirection: 'column' }}>
      {/* Top Controls Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              padding: '6px 10px',
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'var(--color-primary-light)',
              color: 'var(--color-primary)',
            }}
          >
            <Video size={18} />
          </div>
          <div>
            <h1 className="page-title" style={{ fontSize: '18px', margin: 0 }}>
              Live Monitor Grid
            </h1>
            <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              WebRTC low-latency streaming • Active slot: #{selectedSlot + 1}
            </p>
          </div>
        </div>

        {/* Layout Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              display: 'flex',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '2px',
            }}
          >
            <button
              onClick={() => setLayout('1x1')}
              className="btn"
              style={{
                padding: '6px 10px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: layout === '1x1' ? 'var(--color-primary)' : 'transparent',
                color: layout === '1x1' ? '#ffffff' : 'var(--text-secondary)',
              }}
              title="Single Camera (1x1)"
              data-testid="grid-1x1-btn"
            >
              <Square size={14} /> 1x1
            </button>

            <button
              onClick={() => setLayout('2x2')}
              className="btn"
              style={{
                padding: '6px 10px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: layout === '2x2' ? 'var(--color-primary)' : 'transparent',
                color: layout === '2x2' ? '#ffffff' : 'var(--text-secondary)',
              }}
              title="Quad View (2x2)"
              data-testid="grid-2x2-btn"
            >
              <Grid2X2 size={14} /> 2x2
            </button>

            <button
              onClick={() => setLayout('3x3')}
              className="btn"
              style={{
                padding: '6px 10px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: layout === '3x3' ? 'var(--color-primary)' : 'transparent',
                color: layout === '3x3' ? '#ffffff' : 'var(--text-secondary)',
              }}
              title="9 Cameras (3x3)"
              data-testid="grid-3x3-btn"
            >
              <Grid3X3 size={14} /> 3x3
            </button>

            <button
              onClick={() => setLayout('4x4')}
              className="btn"
              style={{
                padding: '6px 10px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: layout === '4x4' ? 'var(--color-primary)' : 'transparent',
                color: layout === '4x4' ? '#ffffff' : 'var(--text-secondary)',
              }}
              title="16 Cameras (4x4)"
              data-testid="grid-4x4-btn"
            >
              <LayoutGrid size={14} /> 4x4
            </button>
          </div>

          <button
            onClick={handleClearAll}
            className="btn btn-secondary"
            style={{ fontSize: '12px' }}
            title="Close all streams"
            data-testid="clear-all-streams-btn"
          >
            <Trash2 size={14} /> Clear All
          </button>
        </div>
      </div>

      {/* Main Split Layout: Camera Directory Left, Grid Right */}
      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '16px', flex: 1, minHeight: 0 }}>
        {/* Camera Selector Sidebar */}
        <div className="card" style={{ padding: '16px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ position: 'relative', marginBottom: '12px' }}>
            <Search
              size={14}
              color="var(--text-muted)"
              style={{ position: 'absolute', left: '10px', top: '10px' }}
            />
            <input
              type="text"
              placeholder="Filter cameras..."
              className="form-input"
              style={{ paddingLeft: '32px', fontSize: '12px' }}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              data-testid="camera-filter-input"
            />
          </div>

          <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '8px' }}>
            AVAILABLE CAMERAS ({cameras.length})
          </div>

          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {loadingCams ? (
              <p style={{ textAlign: 'center', padding: '20px', color: 'var(--text-muted)', fontSize: '12px' }}>
                Scanning devices...
              </p>
            ) : filteredCameras.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
                <CameraIcon size={24} style={{ margin: '0 auto 6px', opacity: 0.4 }} />
                <p style={{ fontSize: '12px' }}>No cameras found.</p>
              </div>
            ) : (
              filteredCameras.map((cam) => (
                <div
                  key={cam.id}
                  onClick={() => handleAssignCamera(cam)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 10px',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: 'var(--bg-surface-subtle)',
                    border: '1px solid var(--border-subtle)',
                    cursor: 'pointer',
                    transition: 'all var(--transition-fast)',
                  }}
                  data-testid={`cam-item-${cam.id}`}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div
                      style={{
                        width: '22px',
                        height: '22px',
                        borderRadius: 'var(--radius-sm)',
                        backgroundColor: 'var(--color-primary-light)',
                        color: 'var(--color-primary)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: 700,
                        fontSize: '11px',
                      }}
                    >
                      {cam.channel_number}
                    </div>
                    <div>
                      <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {cam.name}
                      </div>
                      <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                        CH {cam.channel_number} {cam.is_ptz ? '• PTZ' : ''}
                      </div>
                    </div>
                  </div>

                  <span className="badge badge-online" style={{ fontSize: '9px', padding: '2px 6px' }}>
                    READY
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Video Player Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns:
              layout === '1x1'
                ? '1fr'
                : layout === '2x2'
                  ? 'repeat(2, 1fr)'
                  : layout === '3x3'
                    ? 'repeat(3, 1fr)'
                    : 'repeat(4, 1fr)',
            gap: '12px',
            overflowY: 'auto',
            alignContent: 'start',
          }}
          data-testid="video-grid"
        >
          {Array.from({ length: totalSlots }).map((_, slotIndex) => (
            <VideoCell
              key={slotIndex}
              slotIndex={slotIndex}
              camera={slotMap[slotIndex] || null}
              onSelectSlot={(idx) => setSelectedSlot(idx)}
              onRemoveCamera={handleRemoveCamera}
              isSelected={selectedSlot === slotIndex}
            />
          ))}
        </div>
      </div>
    </div>
  );
};
