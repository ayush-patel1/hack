import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchViolations } from '../api';

const SEVERITY_COLORS = {
  CRITICAL: { bg: 'rgba(239,68,68,0.15)', color: '#f87171' },
  HIGH: { bg: 'rgba(249,115,22,0.15)', color: '#fb923c' },
  MEDIUM: { bg: 'rgba(245,158,11,0.15)', color: '#fbbf24' },
  LOW: { bg: 'rgba(148,163,184,0.15)', color: '#94a3b8' },
};

export default function ViolationTable() {
  const { data: violations, isLoading } = useQuery({ queryKey: ['violations'], queryFn: fetchViolations });
  const [filterType, setFilterType] = useState('All');
  const [filterSeverity, setFilterSeverity] = useState('All');
  const [searchPlot, setSearchPlot] = useState('');

  if (isLoading) return <div className="spinner" />;

  const features = violations?.features || [];

  let rows = features.map(f => {
    const p = f.properties || {};
    return {
      plotId: p.plot_id || '',
      type: p.primary_violation || '',
      allTypes: (p.violation_types || []).join(', '),
      severity: p.severity || '',
      areaRef: p.area_ref_sqm || 0,
      areaCur: p.area_cur_sqm || 0,
      areaDiff: p.area_diff_pct || 0,
      overlap: p.overlap_pct || 0,
      iou: p.iou || 0,
      date: p.detection_date || '',
      action: p.action_required || '',
      cost: p.estimated_cost_inr || 0,
    };
  });

  // Filters
  const types = ['All', ...new Set(rows.map(r => r.type))];
  const severities = ['All', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];

  if (filterType !== 'All') rows = rows.filter(r => r.type === filterType);
  if (filterSeverity !== 'All') rows = rows.filter(r => r.severity === filterSeverity);
  if (searchPlot) rows = rows.filter(r => r.plotId.toUpperCase().includes(searchPlot.toUpperCase()));

  return (
    <div>
      <div className="card">
        <div className="card-header">📋 Violation Details</div>

        {/* Filters */}
        <div className="grid-3" style={{ marginBottom: 20 }}>
          <div className="input-group">
            <label>Violation Type</label>
            <select className="input-field" value={filterType} onChange={e => setFilterType(e.target.value)}>
              {types.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="input-group">
            <label>Severity</label>
            <select className="input-field" value={filterSeverity} onChange={e => setFilterSeverity(e.target.value)}>
              {severities.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="input-group">
            <label>🔎 Search Plot ID</label>
            <input
              className="input-field"
              placeholder="e.g. P001"
              value={searchPlot}
              onChange={e => setSearchPlot(e.target.value)}
            />
          </div>
        </div>

        <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 12 }}>
          Showing {rows.length} of {features.length} violations
        </div>

        {rows.length === 0 ? (
          <div className="alert alert-success">🎉 No violations found matching your filters.</div>
        ) : (
          <div style={{ maxHeight: 500, overflow: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Plot ID</th>
                  <th>Violation Type</th>
                  <th>Severity</th>
                  <th>Area Diff (%)</th>
                  <th>Overlap (%)</th>
                  <th>IoU</th>
                  <th>Detection Date</th>
                  <th>Action Required</th>
                  <th>Est. Cost (₹)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const sevStyle = SEVERITY_COLORS[r.severity] || {};
                  return (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{r.plotId}</td>
                      <td>
                        <span className={`badge ${r.type.toLowerCase().replace(/_/g, '-')}`}>
                          {r.type.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td>
                        <span style={{
                          display: 'inline-flex', alignItems: 'center',
                          padding: '4px 10px', borderRadius: 20,
                          fontSize: '0.72rem', fontWeight: 600,
                          background: sevStyle.bg, color: sevStyle.color,
                        }}>
                          {r.severity}
                        </span>
                      </td>
                      <td>{r.areaDiff.toFixed(1)}%</td>
                      <td>{r.overlap.toFixed(1)}%</td>
                      <td>{r.iou.toFixed(3)}</td>
                      <td style={{ fontSize: '0.78rem' }}>{r.date}</td>
                      <td style={{ fontSize: '0.78rem', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.action}
                      </td>
                      <td style={{ fontWeight: 600, color: '#f59e0b' }}>₹{r.cost.toLocaleString()}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
