import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchMetadata, getPlotImageUrl } from '../api';

export default function ImageCompare() {
  const { data: metadata, isLoading } = useQuery({ queryKey: ['metadata'], queryFn: fetchMetadata });
  const [selectedPlot, setSelectedPlot] = useState(null);

  if (isLoading) return <div className="spinner" />;

  const plots = metadata || [];
  const selected = selectedPlot || (plots.length > 0 ? plots[0].plot_id : null);
  const plot = plots.find(p => p.plot_id === selected);

  if (!plots.length) {
    return (
      <div className="card">
        <div className="empty-state">
          <h3>No Plot Data Available</h3>
          <p>Generate sample data or upload plot metadata to enable image comparison.</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="card">
        <div className="card-header">🖼️ Side-by-Side Comparison</div>

        {/* Plot selector */}
        <div className="input-group" style={{ maxWidth: 400, marginBottom: 20 }}>
          <label>Select Plot for Comparison</label>
          <select
            className="input-field"
            value={selected || ''}
            onChange={e => setSelectedPlot(e.target.value)}
          >
            {plots.map(p => (
              <option key={p.plot_id} value={p.plot_id}>{p.plot_id}</option>
            ))}
          </select>
        </div>

        {/* Image comparison */}
        <div className="image-compare-grid">
          <div className="image-box">
            <div className="image-label">📸 Reference Image</div>
            <img
              src={getPlotImageUrl(selected, 'reference')}
              alt={`${selected} Reference`}
              onError={e => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }}
            />
            <div className="empty-state" style={{ display: 'none', padding: 40 }}>
              <p>Reference image not available</p>
            </div>
          </div>
          <div className="image-box">
            <div className="image-label">📸 Current Image</div>
            <img
              src={getPlotImageUrl(selected, 'current')}
              alt={`${selected} Current`}
              onError={e => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }}
            />
            <div className="empty-state" style={{ display: 'none', padding: 40 }}>
              <p>Current image not available</p>
            </div>
          </div>
        </div>

        {/* Plot details */}
        {plot && (
          <div className="plot-info">
            <div className="plot-info-item">
              <span>Plot:</span>
              <span>{plot.plot_id}</span>
            </div>
            <div className="plot-info-item">
              <span>Area:</span>
              <span>{(plot.area_sqm || 0).toLocaleString()} m²</span>
            </div>
            <div className="plot-info-item">
              <span>Status:</span>
              <span className={`badge ${
                plot.violation_type === 'COMPLIANT' ? 'compliant' : 'critical'
              }`}>
                {plot.violation_type || 'N/A'}
              </span>
            </div>
            <div className="plot-info-item">
              <span>Owner:</span>
              <span>{plot.owner || 'N/A'}</span>
            </div>
            <div className="plot-info-item">
              <span>Zone:</span>
              <span>{plot.zone || 'N/A'}</span>
            </div>
          </div>
        )}
      </div>

      {/* All plots overview grid */}
      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">📋 All Plot Images</div>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
          gap: 12,
        }}>
          {plots.map(p => (
            <div
              key={p.plot_id}
              className="image-box"
              style={{
                cursor: 'pointer',
                border: selected === p.plot_id ? '2px solid var(--accent-blue)' : undefined,
              }}
              onClick={() => setSelectedPlot(p.plot_id)}
            >
              <div className="image-label">{p.plot_id}</div>
              <img
                src={getPlotImageUrl(p.plot_id, 'current')}
                alt={p.plot_id}
                style={{ height: 120, objectFit: 'cover' }}
                onError={e => { e.target.style.display='none'; }}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
