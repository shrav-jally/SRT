import React, { useState } from 'react';
import { TAXONOMY } from '../data/taxonomyData';
import { ChevronDown, ChevronRight, Search, CheckSquare, Square } from 'lucide-react';

export default function InteractiveFieldSelector({ selectedFields, onSelectionChange }) {
  const [expandedCategories, setExpandedCategories] = useState({}); // Default all collapsed for 1-page fit
  const [searchQuery, setSearchQuery] = useState('');

  const toggleCategoryExpand = (catId) => {
    setExpandedCategories(prev => ({ ...prev, [catId]: !prev[catId] }));
  };

  const expandAllCategories = () => {
    const allExpanded = {};
    TAXONOMY.forEach(cat => { allExpanded[cat.id] = true; });
    setExpandedCategories(allExpanded);
  };

  const collapseAllCategories = () => {
    setExpandedCategories({});
  };

  const isFieldSelected = (category, subcategory) => {
    const key = `${category}::${subcategory}`;
    return !!selectedFields[key];
  };

  const toggleField = (catObj, subObj) => {
    const key = `${catObj.category}::${subObj.name}`;
    const updated = { ...selectedFields };
    if (updated[key]) {
      delete updated[key];
    } else {
      updated[key] = {
        category: catObj.category,
        subcategory: subObj.name,
        entity_name: subObj.name,
        entity_type: subObj.entity_type,
        description: subObj.description
      };
    }
    onSelectionChange(updated);
  };

  const toggleAllInCategory = (catObj) => {
    const updated = { ...selectedFields };
    const allSelected = catObj.subcategories.every(sub => isFieldSelected(catObj.category, sub.name));

    catObj.subcategories.forEach(sub => {
      const key = `${catObj.category}::${sub.name}`;
      if (allSelected) {
        delete updated[key];
      } else {
        updated[key] = {
          category: catObj.category,
          subcategory: sub.name,
          entity_name: sub.name,
          entity_type: sub.entity_type,
          description: sub.description
        };
      }
    });

    onSelectionChange(updated);
  };

  const clearAll = () => {
    onSelectionChange({});
  };

  const totalSelected = Object.keys(selectedFields).length;
  const isAnyExpanded = Object.values(expandedCategories).some(Boolean);

  const filteredTaxonomy = TAXONOMY.filter(catObj => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    if (catObj.category.toLowerCase().includes(q)) return true;
    return catObj.subcategories.some(sub => sub.name.toLowerCase().includes(q) || sub.description.toLowerCase().includes(q));
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Search and Action Toolbar */}
      <div 
        className="dds-flex" 
        style={{ 
          justifyContent: 'space-between', 
          alignItems: 'center', 
          backgroundColor: '#ffffff', 
          padding: '14px 20px', 
          borderRadius: '8px', 
          border: '1px solid var(--cool-gray-2)',
          boxShadow: '0 2px 6px rgba(0,0,0,0.03)'
        }}
      >
        <div className="dds-flex" style={{ gap: '12px', alignItems: 'center', flex: 1, maxWidth: '600px' }}>
          <div style={{ position: 'relative', width: '100%' }}>
            <Search size={16} style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: 'var(--cool-gray-9)' }} />
            <input 
              type="text"
              className="dds-input__field"
              placeholder="Search across 16 categories and 60+ subcategories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ paddingLeft: '38px', height: '38px', fontSize: '13px', backgroundColor: '#f8f9fa' }}
            />
          </div>

          <button 
            className="dds-btn dds-btn_secondary"
            onClick={isAnyExpanded ? collapseAllCategories : expandAllCategories}
            style={{ fontSize: '12px', padding: '6px 12px', whiteSpace: 'nowrap' }}
          >
            {isAnyExpanded ? 'Collapse All' : 'Expand All'}
          </button>
        </div>

        <div className="dds-flex" style={{ gap: '12px', alignItems: 'center' }}>
          <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--accessible-green)', padding: '4px 12px', backgroundColor: '#f4f9f1', borderRadius: '20px', border: '1px solid #d0e8c5' }}>
            {totalSelected} Fields Selected
          </span>
          {totalSelected > 0 && (
            <button className="dds-btn dds-btn_secondary" onClick={clearAll} style={{ fontSize: '12px', padding: '4px 12px' }}>
              Clear All
            </button>
          )}
        </div>
      </div>

      {/* Compact 4-Column Responsive Category Grid (Fits on 1 Screen!) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(270px, 1fr))', gap: '14px', alignItems: 'start' }}>
        {filteredTaxonomy.map(catObj => {
          const selectedCount = catObj.subcategories.filter(sub => isFieldSelected(catObj.category, sub.name)).length;
          const isAllSelected = selectedCount === catObj.subcategories.length && catObj.subcategories.length > 0;
          const isExpanded = expandedCategories[catObj.id] || searchQuery.length > 0;

          return (
            <div 
              key={catObj.id} 
              style={{ 
                border: selectedCount > 0 ? '1.5px solid var(--accessible-green)' : '1px solid var(--cool-gray-2)', 
                borderRadius: '8px', 
                backgroundColor: '#ffffff', 
                boxShadow: '0 1px 4px rgba(0,0,0,0.02)',
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column'
              }}
            >
              {/* Category Card Header */}
              <div 
                className="dds-flex" 
                style={{ 
                  justifyContent: 'space-between', 
                  alignItems: 'center', 
                  padding: '12px 14px', 
                  backgroundColor: selectedCount > 0 ? '#f4f9f1' : '#f8f9fa', 
                  cursor: 'pointer', 
                  userSelect: 'none', 
                  borderBottom: isExpanded ? '1px solid var(--cool-gray-2)' : 'none' 
                }}
                onClick={() => toggleCategoryExpand(catObj.id)}
              >
                <div className="dds-flex" style={{ alignItems: 'center', gap: '8px', flex: 1, minWidth: 0 }}>
                  {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  <div style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    <strong style={{ fontSize: '13px', color: 'var(--black)', display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {catObj.category}
                    </strong>
                    <span style={{ fontSize: '11px', color: selectedCount > 0 ? 'var(--accessible-green)' : 'var(--cool-gray-9)', fontWeight: selectedCount > 0 ? 600 : 400 }}>
                      {selectedCount} of {catObj.subcategories.length} selected
                    </span>
                  </div>
                </div>

                <button 
                  className="dds-btn dds-btn_secondary"
                  onClick={(e) => { e.stopPropagation(); toggleAllInCategory(catObj); }}
                  style={{ fontSize: '10px', padding: '3px 6px', height: 'auto', display: 'flex', alignItems: 'center', gap: '4px', whiteSpace: 'nowrap', marginLeft: '6px' }}
                >
                  {isAllSelected ? <CheckSquare size={12} /> : <Square size={12} />}
                  {isAllSelected ? 'Deselect' : 'All'}
                </button>
              </div>

              {/* Subcategories List inside Card */}
              {isExpanded && (
                <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '280px', overflowY: 'auto' }}>
                  {catObj.subcategories.map(sub => {
                    const checked = isFieldSelected(catObj.category, sub.name);
                    return (
                      <div 
                        key={sub.name}
                        onClick={() => toggleField(catObj, sub)}
                        style={{
                          padding: '8px 10px',
                          borderRadius: '6px',
                          border: checked ? '1.5px solid var(--accessible-green)' : '1px solid #e2e8f0',
                          backgroundColor: checked ? '#f4f9f1' : '#ffffff',
                          cursor: 'pointer',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '2px',
                          transition: 'all 0.12s ease'
                        }}
                      >
                        <div className="dds-flex" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                          <div className="dds-flex" style={{ alignItems: 'center', gap: '6px' }}>
                            <input 
                              type="checkbox"
                              checked={checked}
                              onChange={() => {}} // Handled by div click
                              style={{ accentColor: 'var(--deloitte-green)', cursor: 'pointer', width: '14px', height: '14px' }}
                            />
                            <strong style={{ fontSize: '12px', color: 'var(--black)' }}>{sub.name}</strong>
                          </div>
                          <span style={{ fontSize: '9px', padding: '1px 4px', borderRadius: '3px', backgroundColor: sub.entity_type === 'table' ? '#e8f4f8' : '#f1f5f9', color: sub.entity_type === 'table' ? 'var(--accessible-blue)' : 'var(--cool-gray-9)', fontWeight: 700, textTransform: 'uppercase' }}>
                            {sub.entity_type}
                          </span>
                        </div>
                        <p style={{ margin: 0, paddingLeft: '20px', fontSize: '10px', color: 'var(--cool-gray-9)', lineHeight: 1.2 }}>
                          {sub.description}
                        </p>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
