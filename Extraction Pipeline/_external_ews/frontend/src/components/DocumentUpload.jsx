import React, { useRef, useState } from 'react';
import { Upload } from 'lucide-react';

export default function DocumentUpload({ onFileSelect }) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const inputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  };

  const handleFile = (file) => {
    setSelectedFile(file);
    onFileSelect(file);
  };

  return (
    <div className="dds-table-block">
      <div className="dds-table-block__header">
        <h3 className="dds-table-block__title">Upload Annual Report (PDF)</h3>
      </div>
      <div className="dds-table-block__content">
        <div 
          className="dds-upload-area"
          style={{
            border: `2px dashed ${dragActive ? 'var(--accessible-blue)' : 'var(--cool-gray-4)'}`,
            borderRadius: 'var(--radius-lg)',
            padding: '40px 20px',
            textAlign: 'center',
            backgroundColor: dragActive ? '#f0f8ff' : 'transparent',
            cursor: 'pointer',
            transition: 'all 0.2s ease'
          }}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".pdf"
            onChange={handleChange}
            style={{ display: "none" }}
          />
          <Upload size={48} color="var(--accessible-blue)" style={{ marginBottom: '16px' }} />
          <p style={{ margin: 0, font: '600 16px/24px var(--font-family)' }}>
            {selectedFile ? selectedFile.name : "Drag & Drop PDF here, or click to browse"}
          </p>
          <p style={{ margin: '8px 0 0 0', color: 'var(--cool-gray-9)', font: 'var(--body)' }}>
            Supports 100-400 page IFRS/Ind AS reports
          </p>
        </div>
      </div>
    </div>
  );
}
