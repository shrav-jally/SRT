import React, { useEffect, useState } from 'react';
import { Loader2, CheckCircle2, FileText, Cpu, Table, FileCheck } from 'lucide-react';

const STAGES = [
  { id: 1, name: 'PDF Canonicalization & Layout OCR', icon: FileText, desc: 'Extracting high-resolution pages, token positions, and structural text blocks...' },
  { id: 2, name: 'Section Taxonomy & Table Grid Assembly', icon: Table, desc: 'Classifying document sections and reconstructing raw 2D table grid cells...' },
  { id: 3, name: 'On-Prem Qwen LLM Disambiguation', icon: Cpu, desc: 'Evaluating candidate financial statements to resolve Standalone vs Consolidated matches...' },
  { id: 4, name: 'Finalizing Excel & JSON Extraction Output', icon: FileCheck, desc: 'Verifying data provenance, confidence metrics, and preparing download packages...' }
];

export default function ExtractionProgress({ fileName }) {
  const [currentStage, setCurrentStage] = useState(0);

  useEffect(() => {
    const timer1 = setTimeout(() => setCurrentStage(1), 2500);
    const timer2 = setTimeout(() => setCurrentStage(2), 6000);
    const timer3 = setTimeout(() => setCurrentStage(3), 11000);

    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
    };
  }, []);

  return (
    <div className="dds-table-block" style={{ padding: '32px', textAlign: 'center', backgroundColor: '#ffffff' }}>
      <div style={{ maxWidth: '650px', margin: '0 auto' }}>
        <div style={{ marginBottom: '24px' }}>
          <div style={{ display: 'inline-flex', padding: '16px', borderRadius: '50%', backgroundColor: '#f0f7ea', color: 'var(--accessible-green)', marginBottom: '16px' }}>
            <Loader2 size={36} className="dds-spin" style={{ animation: 'spin 1.5s linear infinite' }} />
          </div>
          <h2 style={{ fontSize: '20px', fontWeight: 600, color: 'var(--black)', margin: '0 0 8px 0' }}>
            Extracting Enterprise Document
          </h2>
          <span style={{ fontSize: '13px', color: 'var(--cool-gray-9)' }}>
            File: <strong>{fileName || 'Annual_Report.pdf'}</strong>
          </span>
        </div>

        {/* Progress Bar */}
        <div style={{ width: '100%', height: '8px', backgroundColor: '#e0e0e0', borderRadius: '4px', overflow: 'hidden', marginBottom: '32px' }}>
          <div 
            style={{ 
              height: '100%', 
              width: `${((currentStage + 1) / STAGES.length) * 100}%`, 
              backgroundColor: 'var(--accessible-green)', 
              transition: 'width 0.5s ease-in-out' 
            }} 
          />
        </div>

        {/* Stages Timeline */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', textAlign: 'left' }}>
          {STAGES.map((stage, index) => {
            const Icon = stage.icon;
            const isDone = index < currentStage;
            const isCurrent = index === currentStage;

            return (
              <div 
                key={stage.id}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '16px',
                  padding: '16px',
                  borderRadius: '6px',
                  backgroundColor: isCurrent ? '#f4f9f1' : '#f8f9fa',
                  border: isCurrent ? '1.5px solid var(--accessible-green)' : '1px solid var(--cool-gray-2)',
                  opacity: index > currentStage ? 0.6 : 1,
                  transition: 'all 0.3s ease'
                }}
              >
                <div style={{ marginTop: '2px', color: isDone ? 'var(--accessible-green)' : (isCurrent ? 'var(--accessible-blue)' : 'var(--cool-gray-9)') }}>
                  {isDone ? <CheckCircle2 size={22} /> : <Icon size={22} className={isCurrent ? 'dds-spin' : ''} />}
                </div>
                <div style={{ flex: 1 }}>
                  <div className="dds-flex" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                    <strong style={{ fontSize: '14px', color: isCurrent ? 'var(--accessible-green)' : 'var(--black)' }}>
                      Stage {stage.id}: {stage.name}
                    </strong>
                    {isCurrent && (
                      <span className="dds-status-tag dds-status-tag_green" style={{ fontSize: '10px' }}>
                        Processing...
                      </span>
                    )}
                    {isDone && (
                      <span style={{ fontSize: '11px', color: 'var(--accessible-green)', fontWeight: 600 }}>
                        Completed
                      </span>
                    )}
                  </div>
                  <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: 'var(--cool-gray-9)' }}>
                    {stage.desc}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
