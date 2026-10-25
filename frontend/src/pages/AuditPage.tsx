import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useToast } from '../context/ToastContext';
import {
  FileText,
  Search,
  Filter,
  Clock,
  User as UserIcon,
  Globe,
  RefreshCw,
  Code,
  X,
} from 'lucide-react';

interface AuditItem {
  id: string;
  tenant_id: string;
  user_id?: string;
  user_email?: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  ip_address?: string;
  timestamp: string;
  details?: Record<string, unknown>;
}

export const AuditPage: React.FC = () => {
  const { showToast } = useToast();

  const [logs, setLogs] = useState<AuditItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [actionFilter, setActionFilter] = useState('ALL');
  const [selectedDetails, setSelectedDetails] = useState<Record<string, unknown> | null>(null);

  const fetchAuditLogs = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.get<AuditItem[]>('/audit?limit=100');
      setLogs(data);
    } catch {
      showToast('Failed to load audit logs', 'error');
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    fetchAuditLogs();
  }, [fetchAuditLogs]);

  const filteredLogs = logs.filter((log) => {
    const matchesAction = actionFilter === 'ALL' || log.action === actionFilter;
    const q = searchQuery.toLowerCase();
    const matchesSearch =
      !q ||
      log.action.toLowerCase().includes(q) ||
      log.resource_type.toLowerCase().includes(q) ||
      (log.user_email && log.user_email.toLowerCase().includes(q)) ||
      (log.ip_address && log.ip_address.includes(q));

    return matchesAction && matchesSearch;
  });

  const uniqueActions = Array.from(new Set(logs.map((l) => l.action)));

  return (
    <div data-testid="audit-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Security &amp; Audit Trail</h1>
          <p className="page-description">
            Cryptographically sealed and immutable audit trail of system events, authentication, and stream access
          </p>
        </div>
        <button
          onClick={fetchAuditLogs}
          className="btn btn-secondary"
          data-testid="refresh-audit-btn"
        >
          <RefreshCw size={14} /> Refresh Logs
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div
        className="card"
        style={{
          padding: '16px',
          marginBottom: '20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
          <div style={{ position: 'relative', width: '320px' }}>
            <Search
              size={15}
              color="var(--text-muted)"
              style={{ position: 'absolute', left: '12px', top: '10px' }}
            />
            <input
              type="text"
              placeholder="Search by action, email, IP..."
              className="form-input"
              style={{ paddingLeft: '36px' }}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              data-testid="audit-search-input"
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Filter size={15} color="var(--text-muted)" />
            <select
              className="form-input"
              style={{ width: '200px' }}
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              data-testid="audit-action-filter"
            >
              <option value="ALL">All Event Types ({logs.length})</option>
              {uniqueActions.map((act) => (
                <option key={act} value={act}>
                  {act}
                </option>
              ))}
            </select>
          </div>
        </div>

        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          Showing <strong>{filteredLogs.length}</strong> events
        </span>
      </div>

      {/* Audit Log Table */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>TIMESTAMP</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>ACTION</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>RESOURCE</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>ACTOR</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>CLIENT IP</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)', textAlign: 'right' }}>
                PAYLOAD
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                  Loading security records...
                </td>
              </tr>
            ) : filteredLogs.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                  <FileText size={32} style={{ margin: '0 auto 8px', opacity: 0.4 }} />
                  <p>No audit events match the filter criteria.</p>
                </td>
              </tr>
            ) : (
              filteredLogs.map((log) => (
                <tr
                  key={log.id}
                  style={{ borderBottom: '1px solid var(--border-subtle)' }}
                  data-testid={`audit-row-${log.id}`}
                >
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Clock size={13} color="var(--text-muted)" />
                      {new Date(log.timestamp).toLocaleString()}
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span
                      className={`badge ${
                        log.action.includes('FAIL') || log.action.includes('LOCKOUT')
                          ? 'badge-offline'
                          : log.action.includes('SUCCESS') || log.action.includes('CREATE')
                            ? 'badge-online'
                            : 'badge-info'
                      }`}
                      style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}
                    >
                      {log.action}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                      {log.resource_type}
                    </div>
                    {log.resource_id && (
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        ID: {log.resource_id.substring(0, 12)}...
                      </div>
                    )}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <UserIcon size={14} color="var(--text-muted)" />
                      <span>{log.user_email || 'System'}</span>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Globe size={13} color="var(--text-muted)" />
                      <span>{log.ip_address || '127.0.0.1'}</span>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                    {log.details && Object.keys(log.details).length > 0 ? (
                      <button
                        onClick={() => setSelectedDetails(log.details || null)}
                        className="btn btn-secondary"
                        style={{ padding: '4px 8px', fontSize: '11px' }}
                        data-testid={`view-details-${log.id}`}
                      >
                        <Code size={12} /> View Details
                      </button>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>-</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Details Modal */}
      {selectedDetails && (
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
          data-testid="details-modal"
        >
          <div className="card" style={{ width: '500px', maxHeight: '80vh', padding: '24px', backgroundColor: '#ffffff', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: 700, margin: 0 }}>Event Payload Details</h3>
              <button onClick={() => setSelectedDetails(null)} style={{ color: 'var(--text-muted)' }}>
                <X size={16} />
              </button>
            </div>
            <pre
              style={{
                flex: 1,
                overflowY: 'auto',
                backgroundColor: 'var(--bg-sidebar)',
                color: 'var(--text-on-dark)',
                padding: '16px',
                borderRadius: 'var(--radius-md)',
                fontSize: '12px',
                fontFamily: 'var(--font-mono)',
              }}
              data-testid="details-json-view"
            >
              {JSON.stringify(selectedDetails, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
};
