import React, { useEffect, useState } from 'react';
import { X, Search } from 'lucide-react';

export default function CanonicalInspector({ documentId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('sections');

  useEffect(() => {
    if (documentId) {
      setLoading(true);
      fetch(`http://localhost:8080/api/v1/canonical-summary/${encodeURIComponent(documentId)}`)
        .then(res => {
          if (!res.ok) throw new Error('Failed to load canonical document summary');
          return res.json();
        })
        .then(json => {
          setData(json);
          setLoading(false);
        })
        .catch(err => {
          setError(err.message);
          setLoading(false);
        });
    }
  }, [documentId]);

  return (
    <>
      <div className="dds-modal-overlay show" onClick={onClose}></div>
      <div className="dds-modal" style={{ position: 'fixed', top: '5vh', left: '50%', transform: 'translateX(-50%)', width: '85%', height: '85vh', display: 'flex', flexDirection: 'column', backgroundColor: '#ffffff' }}>
        <div className="dds-modal__header" style={{ borderBottom: '1px solid var(--cool-gray-2)', padding: '16px 24px' }}>
          <div>
            <h2 className="dds-modal__title" style={{ margin: 0 }}>Canonical Document Inspector</h2>
            <span style={{ fontSize: '12px', color: 'var(--cool-gray-9)' }}>Document ID: {documentId}</span>
          </div>
          <button className="dds-modal__close" onClick={onClose}><X /></button>
        </div>

        <div className="dds-modal__body" style={{ flex: 1, padding: '24px', overflowY: 'auto' }}>
          {loading ? (
            <div style={{ padding: '48px', textAlign: 'center', color: 'var(--cool-gray-9)' }}>Loading Canonical Document Structure...</div>
          ) : error ? (
            <div style={{ padding: '24px', color: 'var(--red)', backgroundColor: '#fff5f5', borderRadius: '4px' }}>{error}</div>
          ) : (
            <div>
              {/* Summary Metrics */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '24px' }}>
                <div style={{ padding: '16px', border: '1px solid var(--cool-gray-2)', borderRadius: '4px', backgroundColor: '#f8f9fa' }}>
                  <div style={{ fontSize: '20px', fontWeight: 600, color: 'var(--accessible-blue)' }}>{data.summary_stats?.total_pages || 0}</div>
                  <div style={{ fontSize: '11px', color: 'var(--cool-gray-9)', textTransform: 'uppercase' }}>Total Pages</div>
                </div>
                <div style={{ padding: '16px', border: '1px solid var(--cool-gray-2)', borderRadius: '4px', backgroundColor: '#f8f9fa' }}>
                  <div style={{ fontSize: '20px', fontWeight: 600, color: 'var(--accessible-blue)' }}>{data.summary_stats?.total_sections || 0}</div>
                  <div style={{ fontSize: '11px', color: 'var(--cool-gray-9)', textTransform: 'uppercase' }}>Detected Sections</div>
                </div>
                <div style={{ padding: '16px', border: '1px solid var(--cool-gray-2)', borderRadius: '4px', backgroundColor: '#f8f9fa' }}>
                  <div style={{ fontSize: '20px', fontWeight: 600, color: 'var(--accessible-blue)' }}>{data.summary_stats?.total_tables || 0}</div>
                  <div style={{ fontSize: '11px', color: 'var(--cool-gray-9)', textTransform: 'uppercase' }}>Extracted Canonical Tables</div>
                </div>
              </div>

              {/* Tabs */}
              <div className="dds-flex" style={{ gap: '12px', borderBottom: '2px solid var(--cool-gray-2)', marginBottom: '16px' }}>
                <button 
                  onClick={() => setActiveTab('sections')}
                  style={{ padding: '8px 16px', border: 'none', background: 'none', borderBottom: activeTab === 'sections' ? '3px solid var(--accessible-blue)' : 'none', fontWeight: activeTab === 'sections' ? 600 : 400, cursor: 'pointer' }}
                >
                  Document Sections ({data.sections?.length || 0})
                </button>
                <button 
                  onClick={() => setActiveTab('tables')}
                  style={{ padding: '8px 16px', border: 'none', background: 'none', borderBottom: activeTab === 'tables' ? '3px solid var(--accessible-blue)' : 'none', fontWeight: activeTab === 'tables' ? 600 : 400, cursor: 'pointer' }}
                >
                  Canonical Tables ({data.tables?.length || 0})
                </button>
              </div>

              {/* Tab Content: Sections */}
              {activeTab === 'sections' && (
                <table className="dds-data-table">
                  <thead>
                    <tr>
                      <th className="dds-data-table__header-cell">Section Title</th>
                      <th className="dds-data-table__header-cell">Category / Type</th>
                      <th className="dds-data-table__header-cell">Page Range</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.sections?.map((sec, idx) => (
                      <tr key={idx} className="dds-data-table__row">
                        <td className="dds-data-table__cell"><strong>{sec.title || 'Untitled Section'}</strong></td>
                        <td className="dds-data-table__cell"><span className="dds-status-tag dds-status-tag_gray">{sec.category || 'general'}</span></td>
                        <td className="dds-data-table__cell">{sec.pages}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {/* Tab Content: Tables */}
              {activeTab === 'tables' && (
                <div className="dds-flex dds-flex_column" style={{ gap: '24px' }}>
                  {data.tables?.map((tbl, idx) => (
                    <div key={idx} style={{ border: '1px solid var(--cool-gray-2)', borderRadius: '4px', padding: '16px' }}>
                      <div className="dds-flex" style={{ justifyContent: 'space-between', marginBottom: '12px' }}>
                        <strong style={{ color: 'var(--accessible-blue)' }}>Table #{tbl.table_id}</strong>
                        <span style={{ fontSize: '12px', color: 'var(--cool-gray-9)' }}>Pages: {tbl.pages?.join(', ')} | Grid: {tbl.dimensions}</span>
                      </div>
                      <div style={{ overflowX: 'auto', maxHeight: '250px' }}>
                        <table className="dds-data-table" style={{ fontSize: '11px' }}>
                          <tbody>
                            {tbl.grid_sample?.map((row, rIdx) => (
                              <tr key={rIdx}>
                                {row.map((cell, cIdx) => (
                                  <td key={cIdx} style={{ padding: '4px 8px', border: '1px solid var(--cool-gray-2)', backgroundColor: rIdx === 0 ? '#f0f0f0' : 'transparent', fontWeight: rIdx === 0 ? 600 : 400 }}>
                                    {cell}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
