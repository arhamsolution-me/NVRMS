import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useToast } from '../context/ToastContext';
import { useAuth } from '../context/AuthContext';
import {
  MapPin,
  ChevronRight,
  ChevronDown,
  Plus,
  Trash2,
  Building,
  Layers,
  Map,
  Compass,
  Search,
} from 'lucide-react';

interface SiteNode {
  id: string;
  name: string;
  code?: string;
  address?: string;
}

interface AreaNode {
  id: string;
  name: string;
  code?: string;
  sites: SiteNode[];
}

interface CityNode {
  id: string;
  name: string;
  code?: string;
  areas: AreaNode[];
}

interface ProvinceNode {
  id: string;
  name: string;
  code?: string;
  cities: CityNode[];
}

export const LocationsPage: React.FC = () => {
  const { hasPermission } = useAuth();
  const { showToast } = useToast();

  const [tree, setTree] = useState<ProvinceNode[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<{
    type: 'province' | 'city' | 'area' | 'site';
    id: string;
    name: string;
    parentName?: string;
  } | null>(null);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalType, setModalType] = useState<'province' | 'city' | 'area' | 'site'>('province');
  const [formData, setFormData] = useState({
    name: '',
    code: '',
    address: '',
    parentId: '',
  });

  const fetchTree = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.get<ProvinceNode[]>('/locations/tree');
      setTree(data);
      // Automatically expand provinces, cities, and areas
      const initialExpanded = new Set<string>();
      data.forEach((p) => {
        initialExpanded.add(`prov-${p.id}`);
        p.cities?.forEach((c) => {
          initialExpanded.add(`city-${c.id}`);
          c.areas?.forEach((a) => {
            initialExpanded.add(`area-${a.id}`);
          });
        });
      });
      setExpandedNodes(initialExpanded);
    } catch {
      showToast('Failed to load location hierarchy', 'error');
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    fetchTree();
  }, [fetchTree]);

  const toggleNode = (nodeKey: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(nodeKey)) {
        next.delete(nodeKey);
      } else {
        next.add(nodeKey);
      }
      return next;
    });
  };

  const handleOpenAdd = (type: 'province' | 'city' | 'area' | 'site', parentId: string = '') => {
    setModalType(type);
    setFormData({ name: '', code: '', address: '', parentId });
    setIsModalOpen(true);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (modalType === 'province') {
        await api.post('/locations/provinces', {
          name: formData.name,
          code: formData.code || formData.name.substring(0, 3).toUpperCase(),
        });
      } else if (modalType === 'city') {
        await api.post('/locations/cities', {
          province_id: formData.parentId,
          name: formData.name,
          code: formData.code || formData.name.substring(0, 3).toUpperCase(),
        });
      } else if (modalType === 'area') {
        await api.post('/locations/areas', {
          city_id: formData.parentId,
          name: formData.name,
          code: formData.code || formData.name.substring(0, 3).toUpperCase(),
        });
      } else if (modalType === 'site') {
        await api.post('/locations/sites', {
          area_id: formData.parentId,
          name: formData.name,
          code: formData.code || formData.name.substring(0, 3).toUpperCase(),
          address: formData.address || undefined,
        });
      }

      showToast(`Created ${modalType} successfully`, 'success');
      setIsModalOpen(false);
      await fetchTree();
    } catch (err: unknown) {
      showToast((err as Error).message || 'Failed to create location', 'error');
    }
  };

  const handleDelete = async (type: string, id: string, name: string) => {
    if (!window.confirm(`Are you sure you want to delete ${type} "${name}"?`)) {
      return;
    }
    try {
      await api.delete(`/locations/${type}s/${id}`);
      showToast(`Deleted ${type} "${name}"`, 'success');
      if (selectedNode?.id === id) {
        setSelectedNode(null);
      }
      await fetchTree();
    } catch (err: unknown) {
      showToast((err as Error).message || `Failed to delete ${type}`, 'error');
    }
  };

  const matchesSearch = (name: string) => {
    if (!searchQuery) return true;
    return name.toLowerCase().includes(searchQuery.toLowerCase());
  };

  return (
    <div data-testid="locations-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Location Hierarchy</h1>
          <p className="page-description">
            4-Level Tree: Province &gt; City &gt; Area &gt; Site with strict multi-tenant scoping
          </p>
        </div>
        {hasPermission('locations:write') && (
          <button
            onClick={() => handleOpenAdd('province')}
            className="btn btn-primary"
            data-testid="add-province-btn"
          >
            <Plus size={16} /> Add Province
          </button>
        )}
      </div>

      {/* Main Grid: Tree View Left, Details / Actions Right */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 1fr) 1.2fr', gap: '20px' }}>
        {/* Left Tree Card */}
        <div className="card" style={{ padding: '20px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ position: 'relative', marginBottom: '16px' }}>
            <Search
              size={16}
              color="var(--text-muted)"
              style={{ position: 'absolute', left: '12px', top: '10px' }}
            />
            <input
              type="text"
              placeholder="Search locations..."
              className="form-input"
              style={{ paddingLeft: '36px' }}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              data-testid="location-search-input"
            />
          </div>

          <div style={{ flex: 1, overflowY: 'auto', minHeight: '380px' }} data-testid="location-tree-container">
            {loading ? (
              <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                Loading hierarchy...
              </div>
            ) : tree.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                <MapPin size={32} style={{ margin: '0 auto 8px', opacity: 0.4 }} />
                <p>No locations created yet.</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {tree.map((prov) => {
                  const provKey = `prov-${prov.id}`;
                  const isProvExpanded = expandedNodes.has(provKey) || searchQuery.length > 0;

                  return (
                    <div key={prov.id} style={{ marginLeft: '0px' }} data-testid={`province-node-${prov.id}`}>
                      {/* Province Row */}
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '6px 8px',
                          borderRadius: 'var(--radius-sm)',
                          backgroundColor:
                            selectedNode?.id === prov.id ? 'var(--color-primary-light)' : 'transparent',
                          cursor: 'pointer',
                        }}
                        onClick={() => setSelectedNode({ type: 'province', id: prov.id, name: prov.name })}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleNode(provKey);
                            }}
                            style={{ display: 'flex', alignItems: 'center', color: 'var(--text-muted)' }}
                          >
                            {isProvExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          </button>
                          <Compass size={16} color="var(--color-primary)" />
                          <span style={{ fontWeight: 600, fontSize: '13px' }}>{prov.name}</span>
                          {prov.code && (
                            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>({prov.code})</span>
                          )}
                        </div>

                        {hasPermission('locations:write') && (
                          <div style={{ display: 'flex', gap: '4px' }} onClick={(e) => e.stopPropagation()}>
                            <button
                              onClick={() => handleOpenAdd('city', prov.id)}
                              className="btn btn-secondary"
                              style={{ padding: '2px 6px', fontSize: '11px' }}
                              title="Add City to Province"
                              data-testid={`add-city-to-${prov.id}`}
                            >
                              + City
                            </button>
                            <button
                              onClick={() => handleDelete('province', prov.id, prov.name)}
                              style={{ color: 'var(--status-offline)', padding: '2px 4px' }}
                              title="Delete Province"
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        )}
                      </div>

                      {/* Cities */}
                      {isProvExpanded && prov.cities && (
                        <div style={{ marginLeft: '20px', borderLeft: '1px solid var(--border-subtle)', paddingLeft: '8px' }}>
                          {prov.cities.map((city) => {
                            const cityKey = `city-${city.id}`;
                            const isCityExpanded = expandedNodes.has(cityKey) || searchQuery.length > 0;

                            return (
                              <div key={city.id} data-testid={`city-node-${city.id}`}>
                                <div
                                  style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    padding: '5px 8px',
                                    borderRadius: 'var(--radius-sm)',
                                    backgroundColor:
                                      selectedNode?.id === city.id ? 'var(--color-primary-light)' : 'transparent',
                                    cursor: 'pointer',
                                  }}
                                  onClick={() =>
                                    setSelectedNode({
                                      type: 'city',
                                      id: city.id,
                                      name: city.name,
                                      parentName: prov.name,
                                    })
                                  }
                                >
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        toggleNode(cityKey);
                                      }}
                                      style={{ display: 'flex', alignItems: 'center', color: 'var(--text-muted)' }}
                                    >
                                      {isCityExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                    </button>
                                    <Map size={15} color="#0284c7" />
                                    <span style={{ fontWeight: 500, fontSize: '13px' }}>{city.name}</span>
                                  </div>

                                  {hasPermission('locations:write') && (
                                    <div style={{ display: 'flex', gap: '4px' }} onClick={(e) => e.stopPropagation()}>
                                      <button
                                        onClick={() => handleOpenAdd('area', city.id)}
                                        className="btn btn-secondary"
                                        style={{ padding: '2px 6px', fontSize: '11px' }}
                                        title="Add Area to City"
                                        data-testid={`add-area-to-${city.id}`}
                                      >
                                        + Area
                                      </button>
                                      <button
                                        onClick={() => handleDelete('city', city.id, city.name)}
                                        style={{ color: 'var(--status-offline)', padding: '2px 4px' }}
                                        title="Delete City"
                                      >
                                        <Trash2 size={13} />
                                      </button>
                                    </div>
                                  )}
                                </div>

                                {/* Areas */}
                                {isCityExpanded && city.areas && (
                                  <div style={{ marginLeft: '18px', borderLeft: '1px solid var(--border-subtle)', paddingLeft: '8px' }}>
                                    {city.areas.map((area) => {
                                      const areaKey = `area-${area.id}`;
                                      const isAreaExpanded = expandedNodes.has(areaKey) || searchQuery.length > 0;

                                      return (
                                        <div key={area.id} data-testid={`area-node-${area.id}`}>
                                          <div
                                            style={{
                                              display: 'flex',
                                              alignItems: 'center',
                                              justifyContent: 'space-between',
                                              padding: '5px 8px',
                                              borderRadius: 'var(--radius-sm)',
                                              backgroundColor:
                                                selectedNode?.id === area.id
                                                  ? 'var(--color-primary-light)'
                                                  : 'transparent',
                                              cursor: 'pointer',
                                            }}
                                            onClick={() =>
                                              setSelectedNode({
                                                type: 'area',
                                                id: area.id,
                                                name: area.name,
                                                parentName: `${prov.name} / ${city.name}`,
                                              })
                                            }
                                          >
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                              <button
                                                onClick={(e) => {
                                                  e.stopPropagation();
                                                  toggleNode(areaKey);
                                                }}
                                                style={{ display: 'flex', alignItems: 'center', color: 'var(--text-muted)' }}
                                              >
                                                {isAreaExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                              </button>
                                              <Layers size={14} color="#7c3aed" />
                                              <span style={{ fontSize: '13px' }}>{area.name}</span>
                                            </div>

                                            {hasPermission('locations:write') && (
                                              <div style={{ display: 'flex', gap: '4px' }} onClick={(e) => e.stopPropagation()}>
                                                <button
                                                  onClick={() => handleOpenAdd('site', area.id)}
                                                  className="btn btn-secondary"
                                                  style={{ padding: '2px 6px', fontSize: '11px' }}
                                                  title="Add Site to Area"
                                                  data-testid={`add-site-to-${area.id}`}
                                                >
                                                  + Site
                                                </button>
                                                <button
                                                  onClick={() => handleDelete('area', area.id, area.name)}
                                                  style={{ color: 'var(--status-offline)', padding: '2px 4px' }}
                                                  title="Delete Area"
                                                >
                                                  <Trash2 size={13} />
                                                </button>
                                              </div>
                                            )}
                                          </div>

                                          {/* Sites */}
                                          {isAreaExpanded && area.sites && (
                                            <div style={{ marginLeft: '18px', borderLeft: '1px solid var(--border-subtle)', paddingLeft: '8px' }}>
                                              {area.sites
                                                .filter((site) => matchesSearch(site.name))
                                                .map((site) => (
                                                  <div
                                                    key={site.id}
                                                    style={{
                                                      display: 'flex',
                                                      alignItems: 'center',
                                                      justifyContent: 'space-between',
                                                      padding: '4px 8px',
                                                      borderRadius: 'var(--radius-sm)',
                                                      backgroundColor:
                                                        selectedNode?.id === site.id
                                                          ? 'var(--color-primary-light)'
                                                          : 'transparent',
                                                      cursor: 'pointer',
                                                    }}
                                                    onClick={() =>
                                                      setSelectedNode({
                                                        type: 'site',
                                                        id: site.id,
                                                        name: site.name,
                                                        parentName: `${prov.name} / ${city.name} / ${area.name}`,
                                                      })
                                                    }
                                                    data-testid={`site-node-${site.id}`}
                                                  >
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                      <Building size={14} color="var(--status-online)" />
                                                      <span style={{ fontSize: '12px', fontWeight: 500 }}>
                                                        {site.name}
                                                      </span>
                                                    </div>

                                                    {hasPermission('locations:write') && (
                                                      <button
                                                        onClick={(e) => {
                                                          e.stopPropagation();
                                                          handleDelete('site', site.id, site.name);
                                                        }}
                                                        style={{ color: 'var(--status-offline)', padding: '2px 4px' }}
                                                        title="Delete Site"
                                                      >
                                                        <Trash2 size={12} />
                                                      </button>
                                                    )}
                                                  </div>
                                                ))}
                                            </div>
                                          )}
                                        </div>
                                      );
                                    })}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right Details Card */}
        <div className="card" style={{ padding: '24px' }}>
          {selectedNode ? (
            <div data-testid="location-details-pane">
              <span className="badge badge-info" style={{ textTransform: 'uppercase', marginBottom: '8px' }}>
                {selectedNode.type}
              </span>
              <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '8px 0 4px' }}>{selectedNode.name}</h2>
              {selectedNode.parentName && (
                <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
                  Path: {selectedNode.parentName} &gt; {selectedNode.name}
                </p>
              )}

              <div
                style={{
                  marginTop: '20px',
                  padding: '16px',
                  backgroundColor: 'var(--bg-surface-subtle)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '13px',
                }}
              >
                <p style={{ marginBottom: '6px' }}>
                  <strong>ID:</strong> <code style={{ fontFamily: 'var(--font-mono)' }}>{selectedNode.id}</code>
                </p>
                <p>
                  <strong>Access Policy:</strong> Scoped users assigned to this {selectedNode.type} will automatically
                  inherit visibility over nested assets.
                </p>
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-muted)' }}>
              <Layers size={40} style={{ margin: '0 auto 12px', opacity: 0.3 }} />
              <h3 style={{ fontSize: '16px', fontWeight: 600 }}>Select a Location Node</h3>
              <p style={{ fontSize: '13px', marginTop: '4px' }}>
                Click any Province, City, Area, or Site from the tree to view its hierarchy metadata and scope policy.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Modal for Creating Location */}
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
          data-testid="location-modal"
        >
          <div className="card" style={{ width: '400px', padding: '24px', backgroundColor: '#ffffff' }}>
            <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>
              Add {modalType.charAt(0).toUpperCase() + modalType.slice(1)}
            </h3>

            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label className="form-label" htmlFor="loc-name">
                  Name
                </label>
                <input
                  id="loc-name"
                  type="text"
                  required
                  className="form-input"
                  placeholder={`e.g. ${modalType === 'site' ? 'Branch #101' : 'Metro Region'}`}
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  data-testid="location-name-input"
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="loc-code">
                  Code
                </label>
                <input
                  id="loc-code"
                  type="text"
                  className="form-input"
                  placeholder="e.g. BR-101"
                  value={formData.code}
                  onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                  data-testid="location-code-input"
                />
              </div>

              {modalType === 'site' && (
                <div className="form-group">
                  <label className="form-label" htmlFor="loc-address">
                    Physical Address
                  </label>
                  <input
                    id="loc-address"
                    type="text"
                    className="form-input"
                    placeholder="e.g. 100 Main St, Suite 400"
                    value={formData.address}
                    onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                    data-testid="location-address-input"
                  />
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" data-testid="location-modal-submit">
                  Save Location
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
