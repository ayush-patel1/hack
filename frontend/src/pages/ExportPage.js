import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { exportCSV, exportGeoJSON, generateComplianceReport, generateSampleData } from '../api';
import { Download, FileText, Map as MapIcon, Database, Play } from 'lucide-react';

function downloadBlob(response, filename) {
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
}

export default function ExportPage() {
  const [status, setStatus] = useState('');

  const csvMut = useMutation({
    mutationFn: exportCSV,
    onSuccess: (r) => { downloadBlob(r, 'landguard_violations.csv'); setStatus('CSV downloaded!'); },
    onError: (e) => setStatus(`Error: ${e.message}`),
  });

  const geojsonMut = useMutation({
    mutationFn: exportGeoJSON,
    onSuccess: (r) => { downloadBlob(r, 'violations.geojson'); setStatus('GeoJSON downloaded!'); },
    onError: (e) => setStatus(`Error: ${e.message}`),
  });

  const pdfMut = useMutation({
    mutationFn: generateComplianceReport,
    onSuccess: (r) => { downloadBlob(r, 'landguard_compliance_report.pdf'); setStatus('PDF Report downloaded!'); },
    onError: (e) => setStatus(`Error: ${e.message}`),
  });

  const genDataMut = useMutation({
    mutationFn: generateSampleData,
    onSuccess: () => setStatus('Sample data generated and violations detected! Refresh the page to see updated data.'),
    onError: (e) => setStatus(`Error: ${e.message}`),
  });

  return (
    <div>
      <div className="card">
        <div className="card-header">📥 Export & Reports</div>

        {status && (
          <div className="alert alert-success" style={{ marginBottom: 16 }}>
            {status}
            <button onClick={() => setStatus('')} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>✕</button>
          </div>
        )}

        <div className="grid-3" style={{ marginBottom: 24 }}>
          <div className="card" style={{ textAlign: 'center', padding: 32 }}>
            <FileText size={40} style={{ color: 'var(--accent-blue)', margin: '0 auto 16px' }} />
            <h3 style={{ fontSize: '1rem', marginBottom: 8 }}>Violations CSV</h3>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 16 }}>
              Export all violation data as CSV spreadsheet
            </p>
            <button className="btn btn-primary" style={{ width: '100%' }} onClick={() => csvMut.mutate()} disabled={csvMut.isPending}>
              <Download size={16} /> {csvMut.isPending ? 'Downloading...' : 'Download CSV'}
            </button>
          </div>

          <div className="card" style={{ textAlign: 'center', padding: 32 }}>
            <MapIcon size={40} style={{ color: 'var(--accent-green)', margin: '0 auto 16px' }} />
            <h3 style={{ fontSize: '1rem', marginBottom: 8 }}>Violations GeoJSON</h3>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 16 }}>
              Export spatial data for use with GIS tools
            </p>
            <button className="btn btn-success" style={{ width: '100%' }} onClick={() => geojsonMut.mutate()} disabled={geojsonMut.isPending}>
              <Download size={16} /> {geojsonMut.isPending ? 'Downloading...' : 'Download GeoJSON'}
            </button>
          </div>

          <div className="card" style={{ textAlign: 'center', padding: 32 }}>
            <FileText size={40} style={{ color: 'var(--accent-purple)', margin: '0 auto 16px' }} />
            <h3 style={{ fontSize: '1rem', marginBottom: 8 }}>PDF Report</h3>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 16 }}>
              Generate & download compliance PDF report
            </p>
            <button className="btn btn-primary" style={{ width: '100%', background: 'linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%)' }}
              onClick={() => pdfMut.mutate()} disabled={pdfMut.isPending}>
              <Download size={16} /> {pdfMut.isPending ? 'Generating...' : 'Generate PDF Report'}
            </button>
          </div>
        </div>
      </div>

      {/* Pipeline Actions */}
      <div className="card">
        <div className="card-header"><Database size={20} /> Data Pipeline Actions</div>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: 16 }}>
          Generate sample data and run the full violation detection pipeline
        </p>
        <button className="btn btn-primary" onClick={() => genDataMut.mutate()} disabled={genDataMut.isPending}>
          <Play size={16} /> {genDataMut.isPending ? 'Generating...' : 'Generate Sample Data & Run Detection'}
        </button>
      </div>
    </div>
  );
}
