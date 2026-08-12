import React, { useState } from 'react';
import { Download, Table as TableIcon, FileText, CheckCircle, AlertTriangle } from 'lucide-react';

export default function ExtractionResults({ results, onInspect }) {
  const [activeCategory, setActiveCategory] = useState('ALL');

  if (!results) return null;

  const allFields = results.results || [];
  
  // Extract unique categories
  const categories = ['ALL', ...new Set(allFields.map(f => f.category))];

  // Filter fields based on selected category
  const filteredFields = activeCategory === 'ALL' 
    ? allFields 
    : allFields.filter(f => f.category === activeCategory);

  // Helper to convert 2D array, List of Objects, or JSON strings into standard { headers, rows }
  const parseTableStructure = (val) => {
    if (!val) return null;
    let data = val;
    if (typeof val === 'string') {
      try {
        data = JSON.parse(val);
      } catch (e) {
        return null;
      }
    }

    if (!Array.isArray(data) || data.length === 0) return null;

    // Case 1: 2D Grid Array [['Col1', 'Col2'], ['Val1', 'Val2']]
    if (Array.isArray(data[0])) {
      return {
        headers: data[0].map(h => String(h || '')),
        rows: data.slice(1).map(row => Array.isArray(row) ? row.map(cell => String(cell ?? '')) : [])
      };
    }

    // Case 2: Array of Objects [{ line_item: '...', current_period: 100 }, ...]
    if (typeof data[0] === 'object' && data[0] !== null) {
      const keys = Array.from(new Set(data.flatMap(item => Object.keys(item || {}))));
      const formatHeader = (k) => {
        if (k === 'line_item' || k === 'particulars') return 'Particulars / Line Item';
        if (k === 'current_period' || k === 'current_year') return 'Current Period (2024-2025)';
        if (k === 'previous_period' || k === 'previous_year') return 'Previous Period (2023-2024)';
        return k.replace(/_/g, ' ').toUpperCase();
      };
      
      return {
        headers: keys.map(formatHeader),
        rows: data.map(item => keys.map(k => {
          const v = item[k];
          if (v === null || v === undefined) return '-';
          if (typeof v === 'number') return v.toLocaleString('en-IN');
          return String(v);
        }))
      };
    }

    return null;
  };

  return (
    <div className="dds-flex dds-flex_column" style={{ gap: '24px' }}>
      {/* Header Block */}
      <div className="dds-table-block">
        <div className="dds-table-block__header">
          <div>
            <h3 className="dds-table-block__title" style={{ margin: 0 }}>Custom Extraction Dashboard</h3>
            <span style={{ fontSize: '12px', color: 'var(--cool-gray-9)' }}>Document ID: {results.document_id}</span>
          </div>
          <div className="dds-flex" style={{ gap: '12px' }}>
            <button className="dds-btn dds-btn_secondary" onClick={() => onInspect(results.document_id)}>
              👁️ Inspect Canonical
            </button>
            <a href={`http://localhost:8080/api/v1/download/excel/${results.document_id}`} className="dds-btn dds-btn_primary dds-btn_green" target="_blank" rel="noreferrer">
              <Download size={16} style={{ marginRight: '8px' }} /> Download Excel Workbook
            </a>
          </div>
        </div>
        
        {/* KPI Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', padding: '20px 24px', backgroundColor: '#f8f9fa', borderBottom: '1px solid var(--cool-gray-2)' }}>
          <div style={{ padding: '12px 16px', backgroundColor: '#ffffff', borderRadius: '6px', border: '1px solid var(--cool-gray-2)' }}>
            <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--accessible-blue)' }}>{results.summary.fields_found} / {results.summary.total_fields_requested}</div>
            <div style={{ fontSize: '11px', color: 'var(--cool-gray-9)', textTransform: 'uppercase', marginTop: '2px', fontWeight: 600 }}>Fields Found</div>
          </div>
          <div style={{ padding: '12px 16px', backgroundColor: '#ffffff', borderRadius: '6px', border: '1px solid var(--cool-gray-2)' }}>
            <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--accessible-green)' }}>{results.summary.completion_rate_pct}%</div>
            <div style={{ fontSize: '11px', color: 'var(--cool-gray-9)', textTransform: 'uppercase', marginTop: '2px', fontWeight: 600 }}>Completion Rate</div>
          </div>
          <div style={{ padding: '12px 16px', backgroundColor: '#ffffff', borderRadius: '6px', border: '1px solid var(--cool-gray-2)' }}>
            <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--accessible-blue)' }}>{results.summary.canonical_pages}</div>
            <div style={{ fontSize: '11px', color: 'var(--cool-gray-9)', textTransform: 'uppercase', marginTop: '2px', fontWeight: 600 }}>Canonical Pages Scanned</div>
          </div>
          <div style={{ padding: '12px 16px', backgroundColor: '#ffffff', borderRadius: '6px', border: '1px solid var(--cool-gray-2)' }}>
            <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--accessible-blue)' }}>{results.summary.canonical_tables}</div>
            <div style={{ fontSize: '11px', color: 'var(--cool-gray-9)', textTransform: 'uppercase', marginTop: '2px', fontWeight: 600 }}>Canonical Tables Reconstructed</div>
          </div>
        </div>

        {/* Category Filter Tabs */}
        <div style={{ padding: '12px 24px', backgroundColor: '#ffffff', borderBottom: '1px solid var(--cool-gray-2)', display: 'flex', gap: '8px', overflowX: 'auto' }}>
          {categories.map((cat, idx) => {
            const count = cat === 'ALL' ? allFields.length : allFields.filter(f => f.category === cat).length;
            const isActive = activeCategory === cat;
            return (
              <button
                key={idx}
                onClick={() => setActiveCategory(cat)}
                style={{
                  padding: '6px 16px',
                  borderRadius: '20px',
                  border: isActive ? '1.5px solid var(--accessible-blue)' : '1px solid var(--cool-gray-2)',
                  backgroundColor: isActive ? '#e8f4f8' : '#ffffff',
                  color: isActive ? 'var(--accessible-blue)' : 'var(--black)',
                  fontWeight: isActive ? 600 : 400,
                  fontSize: '12px',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap'
                }}
              >
                {cat} ({count})
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Spacious Results List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {filteredFields.map((field, fIdx) => {
          const tableData = parseTableStructure(field.value_normalized) || parseTableStructure(field.value_raw);

          return (
            <div 
              key={fIdx} 
              style={{ 
                backgroundColor: '#ffffff', 
                borderRadius: '8px', 
                border: '1px solid var(--cool-gray-2)', 
                boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
                overflow: 'hidden'
              }}
            >
              {/* Field Header */}
              <div 
                className="dds-flex" 
                style={{ 
                  justifyContent: 'space-between', 
                  alignItems: 'center', 
                  padding: '16px 24px', 
                  backgroundColor: '#f8f9fa', 
                  borderBottom: '1px solid var(--cool-gray-2)' 
                }}
              >
                <div className="dds-flex" style={{ alignItems: 'center', gap: '12px' }}>
                  <div style={{ padding: '8px', borderRadius: '4px', backgroundColor: tableData ? '#e8f4f8' : '#f0f7ea', color: tableData ? 'var(--accessible-blue)' : 'var(--accessible-green)' }}>
                    {tableData ? <TableIcon size={20} /> : <FileText size={20} />}
                  </div>
                  <div>
                    <div className="dds-flex" style={{ alignItems: 'center', gap: '8px' }}>
                      <strong style={{ fontSize: '16px', color: 'var(--black)' }}>{field.entity_name}</strong>
                      <span className="dds-status-tag dds-status-tag_gray" style={{ fontSize: '11px' }}>{field.category} &rsaquo; {field.subcategory}</span>
                    </div>
                    <span style={{ fontSize: '12px', color: 'var(--cool-gray-9)' }}>Mode: {field.extraction_mode}</span>
                  </div>
                </div>

                <div className="dds-flex" style={{ alignItems: 'center', gap: '16px' }}>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '11px', color: 'var(--cool-gray-9)', textTransform: 'uppercase' }}>Confidence</div>
                    <strong style={{ fontSize: '14px', color: field.confidence >= 0.8 ? 'var(--accessible-green)' : 'var(--accessible-blue)' }}>
                      {field.confidence ? `${(field.confidence * 100).toFixed(0)}%` : '-'}
                    </strong>
                  </div>
                  <span className={`dds-status-tag ${field.status === 'FOUND' ? 'dds-status-tag_green' : (field.status === 'ERROR' ? 'dds-status-tag_red' : 'dds-status-tag_gray')}`} style={{ fontSize: '12px', padding: '4px 12px' }}>
                    {field.status}
                  </span>
                </div>
              </div>

              {/* Field Content Body */}
              <div style={{ padding: '24px' }}>
                {field.status === 'FOUND' && (field.value_raw || field.value_normalized) ? (
                  <div>
                    {tableData ? (
                      <div>
                        <div className="dds-flex" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--cool-gray-9)', textTransform: 'uppercase' }}>
                            Reconstructed Financial Grid ({tableData.rows.length} Rows x {tableData.headers.length} Columns)
                          </span>
                        </div>

                        {/* Uncramped Spacious Table Container */}
                        <div style={{ width: '100%', overflowX: 'auto', borderRadius: '6px', border: '1px solid var(--cool-gray-2)' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', backgroundColor: '#ffffff' }}>
                            <thead>
                              <tr style={{ backgroundColor: '#1e293b', color: '#ffffff' }}>
                                {tableData.headers.map((headerCell, cIdx) => (
                                  <th 
                                    key={cIdx} 
                                    style={{ 
                                      padding: '12px 16px', 
                                      textAlign: cIdx === 0 ? 'left' : 'right', 
                                      fontWeight: 600, 
                                      borderRight: '1px solid #334155',
                                      whiteSpace: 'nowrap'
                                    }}
                                  >
                                    {headerCell || `Col ${cIdx + 1}`}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {tableData.rows.map((row, rIdx) => (
                                <tr 
                                  key={rIdx} 
                                  style={{ 
                                    backgroundColor: rIdx % 2 === 0 ? '#ffffff' : '#f8fafc', 
                                    borderBottom: '1px solid #e2e8f0' 
                                  }}
                                >
                                  {row.map((cell, cIdx) => (
                                    <td 
                                      key={cIdx} 
                                      style={{ 
                                        padding: '10px 16px', 
                                        textAlign: cIdx === 0 ? 'left' : 'right', 
                                        borderRight: '1px solid #e2e8f0',
                                        color: cIdx === 0 ? '#0f172a' : '#334155',
                                        fontWeight: cIdx === 0 ? 600 : 400,
                                        whiteSpace: 'nowrap'
                                      }}
                                    >
                                      {cell}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        
                        {/* Other Candidates Collapse */}
                        {field.other_candidates && field.other_candidates.length > 0 && (
                          <details style={{ marginTop: '16px', border: '1px solid #e2e8f0', borderRadius: '6px', backgroundColor: '#f8fafc' }}>
                            <summary style={{ padding: '12px 16px', cursor: 'pointer', fontWeight: 600, color: '#334155', outline: 'none' }}>
                              View Other Candidates ({field.other_candidates.length} alternatives)
                            </summary>
                            <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
                              {field.other_candidates.map((cand, idx) => {
                                const candTableData = parseTableStructure(cand.grid);
                                if (!candTableData) return null;
                                return (
                                  <div key={idx} style={{ border: '1px dashed #cbd5e1', borderRadius: '6px', padding: '16px', backgroundColor: '#ffffff' }}>
                                    <div style={{ marginBottom: '8px', display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
                                      <span style={{ fontSize: '13px', fontWeight: 600, color: '#475569' }}>
                                        {cand.title || cand.table_id}
                                      </span>
                                      <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '12px', backgroundColor: '#e2e8f0', color: '#64748b' }}>
                                        Page {cand.page_number}
                                      </span>
                                      <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '12px', backgroundColor: '#fef3c7', color: '#92400e' }}>
                                        Score: {cand.score}
                                      </span>
                                      {cand.table_id && (
                                        <span style={{ fontSize: '11px', fontFamily: 'monospace', color: '#94a3b8' }}>{cand.table_id}</span>
                                      )}
                                    </div>
                                    {cand.sec_context && (
                                      <div style={{ marginBottom: '8px', fontSize: '11px', color: '#94a3b8', fontStyle: 'italic' }}>
                                        Section context: {cand.sec_context}
                                      </div>
                                    )}
                                    <div style={{ width: '100%', overflowX: 'auto', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
                                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                                        <thead>
                                          <tr style={{ backgroundColor: '#f1f5f9' }}>
                                            {candTableData.headers.map((h, c) => (
                                              <th key={c} style={{ padding: '8px', textAlign: c === 0 ? 'left' : 'right', borderBottom: '1px solid #e2e8f0' }}>{h || `Col ${c+1}`}</th>
                                            ))}
                                          </tr>
                                        </thead>
                                        <tbody>
                                          {candTableData.rows.map((r, ri) => (
                                            <tr key={ri} style={{ borderBottom: '1px solid #e2e8f0' }}>
                                              {r.map((cell, ci) => (
                                                <td key={ci} style={{ padding: '6px 8px', textAlign: ci === 0 ? 'left' : 'right' }}>{cell}</td>
                                              ))}
                                            </tr>
                                          ))}
                                        </tbody>
                                      </table>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </details>
                        )}
                      </div>
                    ) : (
                      <div style={{ backgroundColor: '#f8f9fa', padding: '16px 20px', borderRadius: '6px', border: '1px solid var(--cool-gray-2)', fontSize: '14px', lineHeight: 1.5, color: '#0f172a' }}>
                        {field.value_raw || JSON.stringify(field.value_normalized)}
                      </div>
                    )}

                    {/* Provenance & Explanation Footer */}
                    {field.explanation && (
                      <div style={{ marginTop: '16px', padding: '10px 14px', backgroundColor: '#f1f5f9', borderRadius: '4px', borderLeft: '3px solid var(--accessible-blue)', fontSize: '12px', color: '#475569' }}>
                        <strong>Provenance Explanation:</strong> {field.explanation}
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ padding: '16px', backgroundColor: '#fff5f5', borderRadius: '6px', border: '1px solid #fecaca', color: 'var(--red)', fontSize: '13px' }}>
                    <AlertTriangle size={16} style={{ display: 'inline', marginRight: '6px' }} />
                    {field.explanation || 'Target entity could not be extracted from document.'}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

