import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSatelliteChanges, fetchChangeMasks, getChangeMaskUrl } from '../api';
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend
} from 'recharts';

const COLORS = ['#4f8cf7', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#06b6d4'];

export default function SatelliteView() {
  const { data: satChanges } = useQuery({ queryKey: ['satChanges'], queryFn: fetchSatelliteChanges });
  const { data: maskFiles } = useQuery({ queryKey: ['changeMasks'], queryFn: fetchChangeMasks });

  const features = satChanges?.features || [];

  const rows = features.map(feat => {
    const p = feat.properties || {};
    const ev = p.satellite_evidence || {};
    const sar = ev.sar || {};
    const ndvi = ev.ndvi || {};
    const ndbi = ev.ndbi || {};
    const tile = ev.tile_diff || {};
    return {
      plotId: p.plot_id || '',
      verdict: p.violation_type || '',
      severity: p.severity || '-',
      confidence: p.confidence || 0,
      sarChange: sar.change_db ?? '-',
      sarSignal: sar.interpretation || '-',
      ndviNow: ndvi.cur_ndvi ?? '-',
      ndviSignal: ndvi.interpretation || '-',
      ndbiSignal: ndbi.interpretation || '-',
      pixelChange: tile.change_pct ?? '-',
    };
  });

  const verdictCounts = {};
  rows.forEach(r => { verdictCounts[r.verdict] = (verdictCounts[r.verdict] || 0) + 1; });
  const verdictData = Object.entries(verdictCounts).map(([k, v]) => ({ name: k, value: v }));
  const satViolations = rows.filter(r => r.verdict !== 'COMPLIANT');

  const methods = [];
  if (rows.some(r => r.sarChange !== '-')) methods.push('SAR');
  if (rows.some(r => r.ndviNow !== '-')) methods.push('NDVI');
  if (rows.some(r => r.pixelChange !== '-')) methods.push('Pixel');

  return (
    <div>
      <div className="card">
        <div className="card-header">🛰️ Satellite Data — Google Earth Engine</div>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: 16 }}>
          Sentinel-1/2 imagery analysis, change detection results, and SAR/NDVI metrics
        </p>

        {!features.length ? (
          <div className="alert alert-info">
            No satellite change data available yet. Run the satellite fetch pipeline to generate data.
          </div>
        ) : (
          <>
            {/* Metrics */}
            <div className="grid-3" style={{ marginBottom: 20 }}>
              <div style={{ textAlign: 'center', padding: 16, background: 'var(--bg-secondary)', borderRadius: 8 }}>
                <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#4f8cf7' }}>{rows.length}</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Plots Analyzed</div>
              </div>
              <div style={{ textAlign: 'center', padding: 16, background: 'var(--bg-secondary)', borderRadius: 8 }}>
                <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#ef4444' }}>{satViolations.length}</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Satellite Violations</div>
              </div>
              <div style={{ textAlign: 'center', padding: 16, background: 'var(--bg-secondary)', borderRadius: 8 }}>
                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#10b981' }}>{methods.join(', ') || 'N/A'}</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Detection Methods</div>
              </div>
            </div>

            {/* Chart + Table */}
            <div className="grid-2">
              <div>
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie data={verdictData} cx="50%" cy="50%" outerRadius={100} innerRadius={50}
                      paddingAngle={3} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                      {verdictData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip contentStyle={{ background: '#1a1f35', border: '1px solid #2a3050', borderRadius: 8, color: '#f0f2f5' }} />
                    <Legend wrapperStyle={{ color: '#8892a8', fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              <div style={{ maxHeight: 280, overflow: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Plot ID</th>
                      <th>Verdict</th>
                      <th>Severity</th>
                      <th>Confidence</th>
                      <th>SAR (dB)</th>
                      <th>NDVI</th>
                      <th>Pixel Δ%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 600 }}>{r.plotId}</td>
                        <td>
                          <span className={`badge ${r.verdict === 'COMPLIANT' ? 'compliant' : 'critical'}`}>
                            {r.verdict}
                          </span>
                        </td>
                        <td><span className={`badge ${r.severity.toLowerCase()}`}>{r.severity}</span></td>
                        <td>{typeof r.confidence === 'number' ? `${(r.confidence * 100).toFixed(0)}%` : '-'}</td>
                        <td>{r.sarChange}</td>
                        <td>{r.ndviNow}</td>
                        <td>{r.pixelChange}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Change Masks */}
            {maskFiles?.length > 0 && (
              <div style={{ marginTop: 20 }}>
                <div className="card-header">🔍 Change Masks (Red = Changed Areas)</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginTop: 12 }}>
                  {maskFiles.slice(0, 8).map(f => (
                    <div key={f} className="image-box">
                      <div className="image-label">{f}</div>
                      <img src={getChangeMaskUrl(f)} alt={f} style={{ width: '100%' }} />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
