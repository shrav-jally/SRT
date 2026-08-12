import React, { useState } from 'react';
import { FileJson, ListChecks, SlidersHorizontal } from 'lucide-react';
import InteractiveFieldSelector from './InteractiveFieldSelector';

const PRESETS = [
  { id: 'sample_custom_spec.json', label: 'Enterprise Demo Spec (10 Core Fields)' },
  { id: 'financial_statements_spec.json', label: 'Financial Statements Only (BS, P&L, CF)' },
  { id: 'msme_financial_metrics_spec.json', label: 'Detailed Financial Metrics (27 Items)' },
  { id: 'comprehensive_sections_spec.json', label: 'Comprehensive Narrative Sections (13 Items)' },
  { id: 'custom', label: 'Upload / Custom JSON Spec' }
];

export default function SpecConfiguration({ onSpecChange }) {
  const [activeTab, setActiveTab] = useState('builder'); // 'builder' or 'presets'
  const [selectedFields, setSelectedFields] = useState({});
  const [mode, setMode] = useState(PRESETS[0].id);
  const [customJson, setCustomJson] = useState('{\n  "spec_id": "custom",\n  "company_name": "Example",\n  "fields": []\n}');
  const [showJson, setShowJson] = useState(false);

  // When user checks/unchecks fields in the Visual Builder
  const handleBuilderSelectionChange = (newSelectedFields) => {
    setSelectedFields(newSelectedFields);
    
    // Transform selected taxonomy fields into CustomExtractionSpec format
    const fieldsList = Object.values(newSelectedFields).map((item, idx) => ({
      field_id: item.subcategory.toLowerCase().replace(/[^a-z0-9]+/g, '_'),
      category: item.category,
      subcategory: item.subcategory,
      entity_name: item.entity_name,
      entity_type: item.entity_type,
      description: item.description,
      extraction_mode: 'DIRECT_MAPPING',
      synonyms: [item.subcategory.toLowerCase()],
      expected_section_types: [item.category.toLowerCase()],
      expected_value_type: item.entity_type === 'table' ? 'table' : 'string',
      required: false
    }));

    const compiledSpec = {
      spec_id: 'custom_builder_spec',
      spec_name: `Custom Interactive Spec (${fieldsList.length} fields)`,
      description: 'Schema generated from interactive taxonomy selection.',
      fields: fieldsList
    };

    onSpecChange({ type: 'custom', value: JSON.stringify(compiledSpec, null, 2) });
  };

  const handleModeChange = (e) => {
    const val = e.target.value;
    setMode(val);
    if (val !== 'custom') {
      onSpecChange({ type: 'preset', value: val });
    } else {
      onSpecChange({ type: 'custom', value: customJson });
    }
  };

  const handleJsonChange = (e) => {
    const val = e.target.value;
    setCustomJson(val);
    if (mode === 'custom') {
      onSpecChange({ type: 'custom', value: val });
    }
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        setCustomJson(e.target.result);
        if (mode === 'custom') {
          onSpecChange({ type: 'custom', value: e.target.result });
        }
      };
      reader.readAsText(file);
    }
  };

  const selectedPreset = PRESETS.find(p => p.id === mode);

  return (
    <div className="dds-table-block">
      <div className="dds-table-block__header" style={{ borderBottom: '1px solid var(--cool-gray-2)', padding: '16px 24px' }}>
        <div className="dds-flex" style={{ width: '100%', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 className="dds-table-block__title" style={{ margin: 0 }}>Configure Target Extraction Fields</h3>
          
          {/* Top Mode Tabs */}
          <div className="dds-flex" style={{ gap: '8px', backgroundColor: '#f0f0f0', padding: '4px', borderRadius: '6px' }}>
            <button 
              className="dds-btn"
              onClick={() => { setActiveTab('builder'); handleBuilderSelectionChange(selectedFields); }}
              style={{
                fontSize: '12px',
                padding: '6px 14px',
                backgroundColor: activeTab === 'builder' ? '#ffffff' : 'transparent',
                color: activeTab === 'builder' ? 'var(--accessible-blue)' : 'var(--cool-gray-9)',
                boxShadow: activeTab === 'builder' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                fontWeight: activeTab === 'builder' ? 600 : 400
              }}
            >
              <ListChecks size={14} style={{ marginRight: '6px' }} /> Interactive Taxonomy Builder
            </button>
            <button 
              className="dds-btn"
              onClick={() => { setActiveTab('presets'); handleModeChange({ target: { value: mode } }); }}
              style={{
                fontSize: '12px',
                padding: '6px 14px',
                backgroundColor: activeTab === 'presets' ? '#ffffff' : 'transparent',
                color: activeTab === 'presets' ? 'var(--accessible-blue)' : 'var(--cool-gray-9)',
                boxShadow: activeTab === 'presets' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                fontWeight: activeTab === 'presets' ? 600 : 400
              }}
            >
              <SlidersHorizontal size={14} style={{ marginRight: '6px' }} /> Presets & Raw JSON
            </button>
          </div>
        </div>
      </div>

      <div className="dds-table-block__content" style={{ padding: '24px' }}>
        {activeTab === 'builder' ? (
          <div>
            <div style={{ marginBottom: '16px', fontSize: '13px', color: 'var(--cool-gray-9)' }}>
              Expand any category below and check off the specific subcategories you want extracted from your PDF document.
            </div>
            <InteractiveFieldSelector 
              selectedFields={selectedFields}
              onSelectionChange={handleBuilderSelectionChange}
            />
          </div>
        ) : (
          <div>
            <div className="dds-input dds-mb-3">
              <div className="dds-input__header">
                <label className="dds-input__label">Select Pre-built Specification Preset</label>
              </div>
              <div className="dds-select">
                <select value={mode} onChange={handleModeChange}>
                  {PRESETS.map(p => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {mode !== 'custom' ? (
              <div style={{ backgroundColor: '#f8f9fa', padding: '16px', borderRadius: '4px', border: '1px solid var(--cool-gray-2)', marginTop: '16px' }}>
                <div className="dds-flex" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <strong style={{ color: 'var(--accessible-blue)', fontSize: '14px' }}>Active Spec: {selectedPreset?.label}</strong>
                    <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: 'var(--cool-gray-9)' }}>
                      Pre-configured enterprise specification for automated canonical extraction.
                    </p>
                  </div>
                  <button 
                    className="dds-btn dds-btn_secondary" 
                    onClick={() => setShowJson(!showJson)}
                    style={{ fontSize: '12px', padding: '6px 12px', whiteSpace: 'nowrap' }}
                  >
                    {showJson ? 'Hide JSON Spec' : '👁️ View Spec Details'}
                  </button>
                </div>

                {showJson && (
                  <div className="dds-textarea" style={{ marginTop: '16px' }}>
                    <textarea 
                      className="dds-textarea__field" 
                      value={
                        mode === 'financial_statements_spec.json' ? 
                        "Extracts: Standalone & Consolidated Balance Sheet, Profit & Loss, and Cash Flow Statements" :
                        mode === 'sample_custom_spec.json' ?
                        "Extracts 10 Core Fields: Company Legal Name, CIN, Auditor, FY End, Revenue, Net Profit, Debt, etc." :
                        "Preconfigured schema specification file: " + mode
                      }
                      readOnly
                      style={{ fontFamily: 'monospace', height: '100px', backgroundColor: '#ffffff', fontSize: '12px' }}
                    />
                  </div>
                )}
              </div>
            ) : (
              <div className="dds-flex dds-flex_column" style={{ gap: '16px', marginTop: '16px', borderTop: '1px solid var(--cool-gray-2)', paddingTop: '16px' }}>
                <div style={{ fontSize: '13px', color: 'var(--cool-gray-9)' }}>
                  Provide a custom schema JSON or upload a <code>.json</code> file defining target fields.
                </div>

                <div className="dds-flex" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                  <label className="dds-input__label" style={{ margin: 0 }}>Custom Schema JSON Definition</label>
                  <label className="dds-btn dds-btn_secondary" style={{ padding: '6px 12px', fontSize: '12px', cursor: 'pointer' }}>
                    <FileJson size={16} style={{ marginRight: '8px' }} /> Upload JSON File
                    <input type="file" accept=".json" onChange={handleFileUpload} style={{ display: 'none' }} />
                  </label>
                </div>
                
                <div className="dds-textarea">
                  <textarea 
                    className="dds-textarea__field" 
                    value={customJson}
                    onChange={handleJsonChange}
                    placeholder="Paste your custom spec JSON here..."
                    style={{ fontFamily: 'monospace', height: '220px', backgroundColor: '#ffffff', fontSize: '12px' }}
                    spellCheck={false}
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

