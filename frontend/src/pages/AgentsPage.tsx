import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useToast } from '../context/ToastContext';
import { useAuth } from '../context/AuthContext';
import {
  Cpu,
  Plus,
  Activity,
  CheckCircle,
  XCircle,
  Clock,
  HardDrive,
  Copy,
  Terminal,
  Trash2,
  Search,
} from 'lucide-react';

interface AgentItem {
  id: string;
  name: string;
  status: 'connected' | 'disconnected' | 'degraded';
  version: string;
  last_heartbeat?: string;
  site_id?: string;
  site_name?: string;
  ip_address?: string;
}

interface EnrolTokenResponse {
  code: string;
  expires_at: string;
  name: string;
}

interface DiagnosticsData {
  timestamp: string;
  agent_version: string;
  system: {
    os: string;
    release: string;
    machine: string;
    python_version: string;
    cpu_count: number;
  };
  disk: {
    total_bytes: number;
    used_bytes: number;
    free_bytes: number;
    percent_used: number;
  };
  time_sync: {
    is_skewed: boolean;
    skew_seconds: number;
    last_sync?: string;
  };
  active_streams: Array<{ stream_id: string; camera_id: string }>;
  config: {
    hub_url: string;
    heartbeat_interval: number;
    log_level: string;
  };
}

export const AgentsPage: React.FC = () => {
  const { hasPermission } = useAuth();
  const { showToast } = useToast();

  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Enrol Modal
  const [isEnrolModalOpen, setIsEnrolModalOpen] = useState(false);
  const [enrolName, setEnrolName] = useState('');
  const [generatedToken, setGeneratedToken] = useState<EnrolTokenResponse | null>(null);
  const [enrolling, setEnrolling] = useState(false);

  // Diagnostics Modal
  const [isDiagModalOpen, setIsDiagModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<AgentItem | null>(null);
  const [diagnostics, setDiagnostics] = useState<DiagnosticsData | null>(null);
  const [loadingDiag, setLoadingDiag] = useState(false);

  const fetchAgents = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.get<AgentItem[]>('/agents');
      setAgents(data);
    } catch {
      showToast('Failed to load edge agent fleet', 'error');
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const handleGenerateEnrol = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnrolling(true);
    try {
      const res = await api.post<EnrolTokenResponse>('/agents/enrol-token', {
        name: enrolName,
      });
      setGeneratedToken(res);
      showToast('Generated single-use enrolment token', 'success');
    } catch (err: unknown) {
      showToast((err as Error).message || 'Failed to generate token', 'error');
    } finally {
      setEnrolling(false);
    }
  };

  const handleCopyCode = () => {
    if (generatedToken?.code) {
      navigator.clipboard.writeText(generatedToken.code);
      showToast('Enrolment code copied to clipboard', 'info');
    }
  };

  const handleOpenDiagnostics = async (agent: AgentItem) => {
    setSelectedAgent(agent);
    setIsDiagModalOpen(true);
    setDiagnostics(null);
    setLoadingDiag(true);

    try {
      const res = await api.post<{ result: DiagnosticsData }>(`/agents/${agent.id}/command`, {
        command: 'get_diagnostics',
        payload: {},
      });
      setDiagnostics(res.result);
    } catch (err: unknown) {
      showToast((err as Error).message || 'Failed to retrieve diagnostics', 'error');
    } finally {
      setLoadingDiag(false);
    }
  };

  const handleRevoke = async (agent: AgentItem) => {
    if (!window.confirm(`Revoke credentials and disconnect Agent "${agent.name}"?`)) return;

    try {
      await api.delete(`/agents/${agent.id}`);
      showToast(`Agent "${agent.name}" revoked`, 'success');
      await fetchAgents();
    } catch (err: unknown) {
      showToast((err as Error).message || 'Failed to revoke agent', 'error');
    }
  };

  const filteredAgents = agents.filter(
    (a) =>
      a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div data-testid="agents-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Edge Agent Fleet</h1>
          <p className="page-description">
            Single-use cryptographic enrolment, outbound WSS telemetry, and real-time fleet diagnostics
          </p>
        </div>
        {hasPermission('agents:enrol') && (
          <button
            onClick={() => {
              setGeneratedToken(null);
              setEnrolName('');
              setIsEnrolModalOpen(true);
            }}
            className="btn btn-primary"
            data-testid="enrol-agent-btn"
          >
            <Plus size={16} /> Enrol New Edge Agent
          </button>
        )}
      </div>

      {/* Filter and Stats */}
      <div className="card" style={{ padding: '16px', marginBottom: '20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ position: 'relative', width: '320px' }}>
          <Search
            size={16}
            color="var(--text-muted)"
            style={{ position: 'absolute', left: '12px', top: '10px' }}
          />
          <input
            type="text"
            placeholder="Search agents by name or ID..."
            className="form-input"
            style={{ paddingLeft: '36px' }}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            data-testid="agent-search-input"
          />
        </div>

        <div style={{ display: 'flex', gap: '16px', fontSize: '12px', color: 'var(--text-secondary)' }}>
          <span>Total Fleet: <strong>{agents.length}</strong></span>
          <span>Online: <strong>{agents.filter((a) => a.status === 'connected').length}</strong></span>
        </div>
      </div>

      {/* Agents Table */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>AGENT IDENTITY</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>STATUS</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>VERSION</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>LAST HEARTBEAT</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)', textAlign: 'right' }}>
                ACTIONS
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                  Loading fleet data...
                </td>
              </tr>
            ) : filteredAgents.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                  <Cpu size={32} style={{ margin: '0 auto 8px', opacity: 0.4 }} />
                  <p>No edge agents enrolled.</p>
                </td>
              </tr>
            ) : (
              filteredAgents.map((agent) => (
                <tr
                  key={agent.id}
                  style={{ borderBottom: '1px solid var(--border-subtle)' }}
                  data-testid={`agent-row-${agent.id}`}
                >
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <Cpu size={18} color="var(--color-primary)" />
                      <div>
                        <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{agent.name}</div>
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          ID: <code style={{ fontFamily: 'var(--font-mono)' }}>{agent.id.substring(0, 13)}...</code>
                        </div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    {agent.status === 'connected' ? (
                      <span className="badge badge-online">
                        <CheckCircle size={12} /> Connected
                      </span>
                    ) : agent.status === 'degraded' ? (
                      <span className="badge badge-warning">
                        <Activity size={12} /> Degraded
                      </span>
                    ) : (
                      <span className="badge badge-offline">
                        <XCircle size={12} /> Disconnected
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                      v{agent.version || '0.1.0'}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-secondary)' }}>
                      <Clock size={13} color="var(--text-muted)" />
                      <span>{agent.last_heartbeat ? new Date(agent.last_heartbeat).toLocaleTimeString() : 'Never'}</span>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                      <button
                        onClick={() => handleOpenDiagnostics(agent)}
                        className="btn btn-secondary"
                        style={{ padding: '4px 10px', fontSize: '12px' }}
                        title="View System Diagnostics"
                        data-testid={`diag-btn-${agent.id}`}
                      >
                        <Terminal size={13} /> Diagnostics
                      </button>

                      {hasPermission('agents:revoke') && (
                        <button
                          onClick={() => handleRevoke(agent)}
                          className="btn"
                          style={{
                            padding: '4px 8px',
                            fontSize: '12px',
                            color: 'var(--status-offline)',
                            backgroundColor: 'var(--status-offline-bg)',
                          }}
                          title="Revoke Agent"
                          data-testid={`revoke-btn-${agent.id}`}
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Enrol Agent Modal */}
      {isEnrolModalOpen && (
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
          data-testid="enrol-modal"
        >
          <div className="card" style={{ width: '460px', padding: '28px', backgroundColor: '#ffffff' }}>
            <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>
              Enrol New Edge Agent
            </h3>

            {!generatedToken ? (
              <form onSubmit={handleGenerateEnrol}>
                <div className="form-group">
                  <label className="form-label" htmlFor="enrol-name">
                    Agent Friendly Name
                  </label>
                  <input
                    id="enrol-name"
                    type="text"
                    required
                    className="form-input"
                    placeholder="e.g. Toronto Branch Edge Box"
                    value={enrolName}
                    onChange={(e) => setEnrolName(e.target.value)}
                    data-testid="enrol-name-input"
                  />
                  <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Generating this code creates a single-use 15-minute token for the physical edge hardware.
                  </p>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setIsEnrolModalOpen(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={enrolling}
                    className="btn btn-primary"
                    data-testid="generate-token-submit"
                  >
                    {enrolling ? 'Generating...' : 'Generate Enrolment Code'}
                  </button>
                </div>
              </form>
            ) : (
              <div>
                <div
                  style={{
                    padding: '16px',
                    backgroundColor: 'var(--bg-surface-subtle)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border-subtle)',
                    textAlign: 'center',
                    marginBottom: '16px',
                  }}
                >
                  <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    SINGLE-USE ENROLMENT CODE
                  </div>
                  <div
                    style={{
                      fontSize: '22px',
                      fontWeight: 800,
                      color: 'var(--color-primary)',
                      fontFamily: 'var(--font-mono)',
                      letterSpacing: '0.05em',
                      marginTop: '8px',
                    }}
                    data-testid="enrolment-code-display"
                  >
                    {generatedToken.code}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--status-warning)', marginTop: '8px' }}>
                    Expires in 15 minutes • Single-use only
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '10px', justifyContent: 'center' }}>
                  <button
                    type="button"
                    onClick={handleCopyCode}
                    className="btn btn-secondary"
                    data-testid="copy-enrolment-code-btn"
                  >
                    <Copy size={14} /> Copy Code
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setIsEnrolModalOpen(false);
                      fetchAgents();
                    }}
                    className="btn btn-primary"
                  >
                    Done
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Diagnostics Modal */}
      {isDiagModalOpen && selectedAgent && (
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
          data-testid="diagnostics-modal"
        >
          <div
            className="card"
            style={{ width: '560px', maxHeight: '85vh', overflowY: 'auto', padding: '28px', backgroundColor: '#ffffff' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div>
                <h3 style={{ fontSize: '18px', fontWeight: 700, margin: 0 }}>
                  Agent Diagnostics: {selectedAgent.name}
                </h3>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  ID: {selectedAgent.id}
                </span>
              </div>
              <span className="badge badge-online">Sanitized</span>
            </div>

            {loadingDiag ? (
              <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                Retrieving live diagnostics bundle from edge device...
              </div>
            ) : diagnostics ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }} data-testid="diagnostics-content">
                {/* System Specs */}
                <div style={{ padding: '12px 14px', backgroundColor: 'var(--bg-surface-subtle)', borderRadius: 'var(--radius-md)' }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '6px' }}>
                    HOST SYSTEM
                  </div>
                  <div style={{ fontSize: '13px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px' }}>
                    <div>OS: <strong>{diagnostics.system?.os} ({diagnostics.system?.machine})</strong></div>
                    <div>CPU Cores: <strong>{diagnostics.system?.cpu_count}</strong></div>
                    <div>Python: <strong>{diagnostics.system?.python_version}</strong></div>
                    <div>Version: <strong>v{diagnostics.agent_version}</strong></div>
                  </div>
                </div>

                {/* Storage & Clock Drift */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div style={{ padding: '12px', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 600 }}>
                      <HardDrive size={15} color="var(--color-primary)" /> Disk Usage
                    </div>
                    <div style={{ fontSize: '18px', fontWeight: 700, marginTop: '4px' }}>
                      {diagnostics.disk?.percent_used || 0}%
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      Free: {Math.round((diagnostics.disk?.free_bytes || 0) / 1024 / 1024 / 1024)} GB
                    </div>
                  </div>

                  <div style={{ padding: '12px', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 600 }}>
                      <Clock size={15} color="var(--status-online)" /> Clock Drift
                    </div>
                    <div style={{ fontSize: '18px', fontWeight: 700, marginTop: '4px' }}>
                      {diagnostics.time_sync?.skew_seconds || 0}s
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--status-online)' }}>
                      {diagnostics.time_sync?.is_skewed ? 'Skew Compensated' : 'Clock Synchronized'}
                    </div>
                  </div>
                </div>

                {/* Active Streams */}
                <div style={{ padding: '12px 14px', backgroundColor: 'var(--bg-surface-subtle)', borderRadius: 'var(--radius-md)' }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '4px' }}>
                    ACTIVE PIPELINES ({diagnostics.active_streams?.length || 0})
                  </div>
                  <div style={{ fontSize: '12px' }}>
                    {diagnostics.active_streams?.length ? (
                      diagnostics.active_streams.map((s) => (
                        <div key={s.stream_id} style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                          Stream {s.stream_id.substring(0, 8)}... (Camera {s.camera_id.substring(0, 8)}...)
                        </div>
                      ))
                    ) : (
                      <span style={{ color: 'var(--text-muted)' }}>No on-demand streams active currently</span>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <p style={{ color: 'var(--status-offline)' }}>Failed to load diagnostics from agent.</p>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '20px' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setIsDiagModalOpen(false)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
