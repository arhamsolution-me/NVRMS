import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useToast } from '../context/ToastContext';
import { useAuth } from '../context/AuthContext';
import {
  Camera as CameraIcon,
  Plus,
  Radio,
  Trash2,
  Search,
  CheckCircle,
  XCircle,
  Video,
  Server,
  Layers,
  Sparkles,
} from 'lucide-react';

interface NVRItem {
  id: string;
  name: string;
  ip_address: string;
  vendor: string;
  web_port: number;
  rtsp_port: number;
  onvif_port: number;
  status: 'online' | 'offline' | 'degraded';
  channel_count?: number;
  agent_id: string;
  site_id: string;
}

interface CameraItem {
  id: string;
  nvr_id: string;
  channel_number: number;
  name: string;
  main_stream_url?: string;
  sub_stream_url?: string;
  is_ptz: boolean;
  status: string;
}

interface AgentOption {
  id: string;
  name: string;
  status: string;
}

interface SiteOption {
  id: string;
  name: string;
}

export const DevicesPage: React.FC = () => {
  const { hasPermission } = useAuth();
  const { showToast } = useToast();

  const [nvrs, setNvrs] = useState<NVRItem[]>([]);
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [sites, setSites] = useState<SiteOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Selected NVR for cameras view
  const [selectedNvr, setSelectedNvr] = useState<NVRItem | null>(null);
  const [cameras, setCameras] = useState<CameraItem[]>([]);
  const [loadingCameras, setLoadingCameras] = useState(false);

  // Add NVR Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<{
    reachable: boolean;
    channels?: Array<{ channel: number; name: string }>;
  } | null>(null);

  const [formData, setFormData] = useState({
    name: '',
    ip_address: '',
    vendor: 'hikvision',
    rtsp_port: 554,
    web_port: 80,
    onvif_port: 8000,
    username: 'admin',
    password: '',
    agent_id: '',
    site_id: '',
  });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [nvrData, agentData, siteData] = await Promise.all([
        api.get<NVRItem[]>('/nvrs'),
        api.get<AgentOption[]>('/agents').catch(() => []),
        api.get<SiteOption[]>('/locations/sites').catch(() => []),
      ]);
      setNvrs(nvrData);
      setAgents(agentData);
      setSites(siteData);
    } catch {
      showToast('Failed to load device list', 'error');
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const fetchCameras = useCallback(
    async (nvrId: string) => {
      try {
        setLoadingCameras(true);
        const data = await api.get<CameraItem[]>(`/nvrs/${nvrId}/cameras`);
        setCameras(data);
      } catch {
        showToast('Failed to load camera channels', 'error');
      } finally {
        setLoadingCameras(false);
      }
    },
    [showToast]
  );

  const handleSelectNvr = (nvr: NVRItem) => {
    setSelectedNvr(nvr);
    fetchCameras(nvr.id);
  };

  const handleOpenAdd = () => {
    setProbeResult(null);
    setFormData({
      name: '',
      ip_address: '',
      vendor: 'hikvision',
      rtsp_port: 554,
      web_port: 80,
      onvif_port: 8000,
      username: 'admin',
      password: '',
      agent_id: agents[0]?.id || '',
      site_id: sites[0]?.id || '',
    });
    setIsModalOpen(true);
  };

  const handleProbe = async () => {
    if (!formData.ip_address || !formData.agent_id) {
      showToast('Please specify target IP address and Edge Agent first', 'warning');
      return;
    }

    setProbing(true);
    setProbeResult(null);

    try {
      const res = await api.post<{
        reachable: boolean;
        channels?: Array<{ channel: number; name: string }>;
      }>('/nvrs/probe', {
        agent_id: formData.agent_id,
        ip_address: formData.ip_address,
        vendor: formData.vendor,
        rtsp_port: Number(formData.rtsp_port),
        web_port: Number(formData.web_port),
        username: formData.username,
        password: formData.password,
      });

      setProbeResult(res);
      if (res.reachable) {
        showToast(`NVR Reachable! Discovered ${res.channels?.length || 0} camera channels`, 'success');
      } else {
        showToast('NVR Host unreachable on specified IP/port', 'error');
      }
    } catch (err: unknown) {
      showToast((err as Error).message || 'Probe request failed', 'error');
    } finally {
      setProbing(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.post('/nvrs', {
        name: formData.name,
        ip_address: formData.ip_address,
        vendor: formData.vendor,
        rtsp_port: Number(formData.rtsp_port),
        web_port: Number(formData.web_port),
        onvif_port: Number(formData.onvif_port),
        username: formData.username,
        password: formData.password,
        agent_id: formData.agent_id,
        site_id: formData.site_id,
      });

      showToast(`NVR "${formData.name}" onboarded successfully`, 'success');
      setIsModalOpen(false);
      await fetchData();
    } catch (err: unknown) {
      showToast((err as Error).message || 'Failed to onboard NVR', 'error');
    }
  };

  const handleDeleteNvr = async (nvr: NVRItem) => {
    if (!window.confirm(`Delete NVR "${nvr.name}" and all associated cameras?`)) return;

    try {
      await api.delete(`/nvrs/${nvr.id}`);
      showToast(`NVR "${nvr.name}" deleted`, 'success');
      if (selectedNvr?.id === nvr.id) {
        setSelectedNvr(null);
        setCameras([]);
      }
      await fetchData();
    } catch (err: unknown) {
      showToast((err as Error).message || 'Failed to delete NVR', 'error');
    }
  };

  const filteredNvrs = nvrs.filter(
    (n) =>
      n.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      n.ip_address.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div data-testid="devices-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">NVR & Camera Inventory</h1>
          <p className="page-description">
            Edge NVR onboarding by IP, active reachability probes, and channel stream mapping
          </p>
        </div>
        {hasPermission('nvrs:write') && (
          <button onClick={handleOpenAdd} className="btn btn-primary" data-testid="onboard-nvr-btn">
            <Plus size={16} /> Onboard NVR by IP
          </button>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '20px' }}>
        {/* NVRs List */}
        <div className="card" style={{ padding: '20px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <div style={{ position: 'relative', width: '280px' }}>
              <Search
                size={16}
                color="var(--text-muted)"
                style={{ position: 'absolute', left: '12px', top: '10px' }}
              />
              <input
                type="text"
                placeholder="Search NVR by name or IP..."
                className="form-input"
                style={{ paddingLeft: '36px' }}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="nvr-search-input"
              />
            </div>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Total: {nvrs.length} NVRs
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {loading ? (
              <p style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
                Loading NVR fleet...
              </p>
            ) : filteredNvrs.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                <Server size={32} style={{ margin: '0 auto 8px', opacity: 0.4 }} />
                <p>No NVRs onboarded yet.</p>
              </div>
            ) : (
              filteredNvrs.map((nvr) => (
                <div
                  key={nvr.id}
                  onClick={() => handleSelectNvr(nvr)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '14px 16px',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid',
                    borderColor:
                      selectedNvr?.id === nvr.id ? 'var(--color-primary)' : 'var(--border-subtle)',
                    backgroundColor:
                      selectedNvr?.id === nvr.id ? 'var(--color-primary-light)' : 'var(--bg-surface)',
                    cursor: 'pointer',
                    transition: 'all var(--transition-fast)',
                  }}
                  data-testid={`nvr-item-${nvr.id}`}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <Server
                      size={20}
                      color={selectedNvr?.id === nvr.id ? 'var(--color-primary)' : 'var(--text-secondary)'}
                    />
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>
                          {nvr.name}
                        </span>
                        <span className="badge badge-info" style={{ fontSize: '10px', textTransform: 'uppercase' }}>
                          {nvr.vendor}
                        </span>
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                        IP: <code style={{ fontFamily: 'var(--font-mono)' }}>{nvr.ip_address}</code> | RTSP: {nvr.rtsp_port}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{ textAlign: 'right' }}>
                      <span className={`badge ${nvr.status === 'online' ? 'badge-online' : 'badge-warning'}`}>
                        {nvr.status}
                      </span>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                        {nvr.channel_count || 0} Channels
                      </div>
                    </div>

                    {hasPermission('nvrs:write') && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteNvr(nvr);
                        }}
                        style={{ color: 'var(--status-offline)', padding: '4px' }}
                        title="Delete NVR"
                        data-testid={`delete-nvr-${nvr.id}`}
                      >
                        <Trash2 size={15} />
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Camera Channels Drawer */}
        <div className="card" style={{ padding: '24px', display: 'flex', flexDirection: 'column' }}>
          {selectedNvr ? (
            <>
              <div
                style={{
                  borderBottom: '1px solid var(--border-subtle)',
                  paddingBottom: '14px',
                  marginBottom: '16px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <h3 style={{ fontSize: '16px', fontWeight: 700, margin: 0 }}>
                    Cameras for {selectedNvr.name}
                  </h3>
                  <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                    IP: {selectedNvr.ip_address} ({selectedNvr.vendor})
                  </p>
                </div>
                <span className="badge badge-online">
                  <Radio size={12} /> {cameras.length} Active Channels
                </span>
              </div>

              {loadingCameras ? (
                <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                  Loading cameras...
                </div>
              ) : cameras.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                  <CameraIcon size={32} style={{ margin: '0 auto 8px', opacity: 0.4 }} />
                  <p>No camera channels mapped for this NVR.</p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', overflowY: 'auto' }}>
                  {cameras.map((cam) => (
                    <div
                      key={cam.id}
                      style={{
                        padding: '12px 14px',
                        borderRadius: 'var(--radius-md)',
                        backgroundColor: 'var(--bg-surface-subtle)',
                        border: '1px solid var(--border-subtle)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                      data-testid={`camera-channel-${cam.channel_number}`}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div
                          style={{
                            width: '28px',
                            height: '28px',
                            borderRadius: 'var(--radius-sm)',
                            backgroundColor: 'var(--color-primary-light)',
                            color: 'var(--color-primary)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontWeight: 700,
                            fontSize: '12px',
                          }}
                        >
                          {cam.channel_number}
                        </div>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: '13px' }}>{cam.name}</div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            Channel {cam.channel_number} {cam.is_ptz ? '• PTZ Supported' : ''}
                          </div>
                        </div>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span className="badge badge-online" style={{ fontSize: '11px' }}>
                          <Video size={11} /> 1080p
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-muted)' }}>
              <Layers size={40} style={{ margin: '0 auto 12px', opacity: 0.3 }} />
              <h3 style={{ fontSize: '16px', fontWeight: 600 }}>Select an NVR</h3>
              <p style={{ fontSize: '13px', marginTop: '4px' }}>
                Select an NVR from the inventory list to view its mapped video channels and stream endpoints.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Onboard NVR Modal */}
      {isModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 999,
          }}
          data-testid="onboard-nvr-modal"
        >
          <div className="card" style={{ width: '500px', maxHeight: '90vh', overflowY: 'auto', padding: '28px', backgroundColor: '#ffffff' }}>
            <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>
              Onboard Edge NVR by IP
            </h3>

            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label" htmlFor="nvr-name">
                  NVR Device Name
                </label>
                <input
                  id="nvr-name"
                  type="text"
                  required
                  className="form-input"
                  placeholder="e.g. Branch Main NVR #1"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  data-testid="nvr-name-input"
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '12px' }}>
                <div className="form-group">
                  <label className="form-label" htmlFor="nvr-ip">
                    Local IP Address (SSRF Guarded)
                  </label>
                  <input
                    id="nvr-ip"
                    type="text"
                    required
                    className="form-input"
                    placeholder="192.168.1.100"
                    value={formData.ip_address}
                    onChange={(e) => setFormData({ ...formData, ip_address: e.target.value })}
                    data-testid="nvr-ip-input"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="nvr-vendor">
                    Hardware Vendor
                  </label>
                  <select
                    id="nvr-vendor"
                    className="form-input"
                    value={formData.vendor}
                    onChange={(e) => setFormData({ ...formData, vendor: e.target.value })}
                    data-testid="nvr-vendor-select"
                  >
                    <option value="hikvision">Hikvision</option>
                    <option value="dahua">Dahua</option>
                    <option value="uniview">Uniview</option>
                    <option value="generic">Generic RTSP</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div className="form-group">
                  <label className="form-label" htmlFor="nvr-user">
                    NVR Username
                  </label>
                  <input
                    id="nvr-user"
                    type="text"
                    required
                    className="form-input"
                    value={formData.username}
                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                    data-testid="nvr-username-input"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="nvr-pass">
                    NVR Password
                  </label>
                  <input
                    id="nvr-pass"
                    type="password"
                    required
                    className="form-input"
                    placeholder="••••••••"
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    data-testid="nvr-password-input"
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div className="form-group">
                  <label className="form-label" htmlFor="nvr-agent">
                    Assigned Edge Agent
                  </label>
                  <select
                    id="nvr-agent"
                    required
                    className="form-input"
                    value={formData.agent_id}
                    onChange={(e) => setFormData({ ...formData, agent_id: e.target.value })}
                    data-testid="nvr-agent-select"
                  >
                    <option value="" disabled>
                      Select Connected Agent...
                    </option>
                    {agents.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} ({a.status})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="nvr-site">
                    Physical Site
                  </label>
                  <select
                    id="nvr-site"
                    required
                    className="form-input"
                    value={formData.site_id}
                    onChange={(e) => setFormData({ ...formData, site_id: e.target.value })}
                    data-testid="nvr-site-select"
                  >
                    <option value="" disabled>
                      Select Site Location...
                    </option>
                    {sites.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Probe Test Box */}
              <div
                style={{
                  marginTop: '12px',
                  padding: '12px 14px',
                  backgroundColor: 'var(--bg-surface-subtle)',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '12px' }}>Discovery Probe</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    Validate IP reachability and enumerate channels before onboarding
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleProbe}
                  disabled={probing}
                  className="btn btn-secondary"
                  style={{ fontSize: '11px', padding: '6px 12px' }}
                  data-testid="probe-nvr-btn"
                >
                  <Sparkles size={13} color="var(--color-primary)" />
                  {probing ? 'Probing...' : 'Probe NVR'}
                </button>
              </div>

              {probeResult && (
                <div
                  style={{
                    marginTop: '10px',
                    padding: '10px 12px',
                    borderRadius: 'var(--radius-md)',
                    backgroundColor: probeResult.reachable
                      ? 'var(--status-online-bg)'
                      : 'var(--status-offline-bg)',
                    border: '1px solid',
                    borderColor: probeResult.reachable
                      ? 'rgba(16, 185, 129, 0.25)'
                      : 'rgba(239, 68, 68, 0.25)',
                    fontSize: '12px',
                  }}
                  data-testid="probe-result-box"
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                    {probeResult.reachable ? (
                      <>
                        <CheckCircle size={14} color="var(--status-online)" />
                        <span style={{ color: 'var(--status-online)' }}>
                          Probe Succeeded: {probeResult.channels?.length || 0} channels detected
                        </span>
                      </>
                    ) : (
                      <>
                        <XCircle size={14} color="var(--status-offline)" />
                        <span style={{ color: 'var(--status-offline)' }}>
                          Host Unreachable on specified IP/port
                        </span>
                      </>
                    )}
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '24px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" data-testid="save-nvr-submit">
                  Save &amp; Onboard
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
