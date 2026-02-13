import React from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { fetchAnalysisResults, runAnalysis, generateReport } from '../api';
import { Play, Download, Microscope } from 'lucide-react';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend
} from 'recharts';

const STATUS_COLORS = { Vacant: '#f59e0b', 'Partially Developed': '#e67e22', 'Fully Developed': '#10b981' };

export default function PlotAnalysis() {
  const { data: results, refetch } = useQuery({ queryKey: ['analysisResults'], queryFn: fetchAnalysisResults });

  const analysisMut = useMutation({
    mutationFn: runAnalysis,
    onSuccess: () => refetch(),
  });

  const reportMut = useMutation({
    mutationFn: generateReport,
    onSuccess: (response) => {
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement('a'); a.href = url; a.download = 'Analysis_Report.pdf'; a.click();
    },
  });

  const analysisRows = results || [];
  const statusCounts = {};
  analysisRows.forEach(r => { statusCounts[r.status] = (statusCounts[r.status] || 0) + 1; });
  const statusData = Object.entries(statusCounts).map(([k, v]) => ({ name: k, value: v }));
  const deviations = analysisRows.filter(r => r.has_deviation);

  // Zone breakdown
  const zoneCounts = {};
  analysisRows.forEach(r => { const z = r.zone || 'Unknown'; zoneCounts[z] = (zoneCounts[z] || 0) + 1; });
  const zoneData = Object.entries(zoneCounts).map(([k, v]) => ({ name: k, value: v }));

  return (
    <div>
      <div className="card">
        <div className="card-header"><Microscope size={20} /> Plot Development Analysis</div>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: 16 }}>
          Run edge detection and multi-signal analysis on plot imagery to classify development status
        </p>

        <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
          <button className="btn btn-primary" onClick={() => analysisMut.mutate()} disabled={analysisMut.isPending}>
            <Play size={16} /> {analysisMut.isPending ? 'Running Analysis...' : 'Run Full Analysis'}
          </button>
          <button className="btn btn-success" onClick={() => reportMut.mutate()} disabled={!analysisRows.length || reportMut.isPending}>
            <Download size={16} /> {reportMut.isPending ? 'Generating...' : 'Download PDF Report'}
          </button>
        </div>

        {!analysisRows.length ? (
          <div className="empty-state">
            <Microscope size={48} />
            <h3>No Analysis Results</h3>
            <p>Click "Run Full Analysis" to analyze plots using computer vision edge detection.</p>
          </div>
        ) : (
          <>
            {/* Summary stats */}
            <div className="metrics-grid" style={{ marginBottom: 20 }}>
              <div className="metric-card blue">
                <div className="metric-value">{analysisRows.length}</div>
                <div className="metric-label">Total Plots Analyzed</div>
              </div>
              <div className="metric-card green">
                <div className="metric-value">{statusCounts['Fully Developed'] || 0}</div>
                <div className="metric-label">Fully Developed</div>
              </div>
              <div className="metric-card yellow">
                <div className="metric-value">{statusCounts['Vacant'] || 0}</div>
                <div className="metric-label">Vacant</div>
              </div>
              <div className="metric-card red">
                <div className="metric-value">{deviations.length}</div>
                <div className="metric-label">Deviations Found</div>
              </div>
            </div>

            {/* Charts */}
            <div className="grid-2" style={{ marginBottom: 20 }}>
              <div className="card">
                <div className="card-header">Development Status Distribution</div>
                <ResponsiveContainer width="100%" height={250}>
                  <PieChart>
                    <Pie data={statusData} cx="50%" cy="50%" outerRadius={90} innerRadius={45}
                      paddingAngle={3} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                      {statusData.map((entry, i) => (
                        <Cell key={i} fill={STATUS_COLORS[entry.name] || '#666'} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ background: '#1a1f35', border: '1px solid #2a3050', borderRadius: 8, color: '#f0f2f5' }} />
                    <Legend wrapperStyle={{ color: '#8892a8', fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              <div className="card">
                <div className="card-header">Plots by Zone</div>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={zoneData}>
                    <XAxis dataKey="name" tick={{ fill: '#8892a8', fontSize: 10 }} axisLine={{ stroke: '#2a3050' }} tickLine={false} />
                    <YAxis tick={{ fill: '#8892a8', fontSize: 11 }} axisLine={{ stroke: '#2a3050' }} tickLine={false} />
                    <Tooltip contentStyle={{ background: '#1a1f35', border: '1px solid #2a3050', borderRadius: 8, color: '#f0f2f5' }} />
                    <Bar dataKey="value" radius={[6, 6, 0, 0]} fill="#4f8cf7" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Deviations list */}
            {deviations.length > 0 && (
              <div className="card">
                <div className="card-header" style={{ borderLeftColor: '#ef4444' }}>
                  ⚠️ Deviation Details ({deviations.length})
                </div>
                {deviations.map((r, i) => (
                  <div key={i} style={{
                    padding: '10px 14px', marginBottom: 8,
                    background: 'rgba(239,68,68,0.05)', borderRadius: 8,
                    borderLeft: '3px solid #ef4444', fontSize: '0.85rem',
                  }}>
                    <strong>{r.plot_id}</strong> (Zone: {r.zone || '?'}) — {r.deviation_reason}
                  </div>
                ))}
              </div>
            )}

            {/* Full results table */}
            <div className="card" style={{ marginTop: 16 }}>
              <div className="card-header">Full Results Table</div>
              <div style={{ maxHeight: 400, overflow: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Plot ID</th>
                      <th>Plot #</th>
                      <th>Zone</th>
                      <th>Area (m²)</th>
                      <th>Dev %</th>
                      <th>Status</th>
                      <th>Industry</th>
                      <th>Deviation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysisRows.map((r, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 600 }}>{r.plot_id}</td>
                        <td>{r.plot_number}</td>
                        <td>{r.zone || '—'}</td>
                        <td>{(r.area_sqm || 0).toFixed(1)}</td>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div style={{ width: 50, height: 5, background: '#1a1f35', borderRadius: 3, overflow: 'hidden' }}>
                              <div style={{
                                width: `${Math.min(r.developed_pct || 0, 100)}%`, height: '100%',
                                background: (r.developed_pct || 0) < 15 ? '#f59e0b' : (r.developed_pct || 0) < 60 ? '#e67e22' : '#10b981',
                              }} />
                            </div>
                            <span style={{ fontSize: '0.78rem' }}>{(r.developed_pct || 0).toFixed(1)}%</span>
                          </div>
                        </td>
                        <td>
                          <span className={`badge ${r.status === 'Vacant' ? 'vacant' : r.status === 'Partially Developed' ? 'medium' : 'compliant'}`}>
                            {r.status}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.78rem' }}>{r.industry_type || '—'}</td>
                        <td>{r.has_deviation ? <span className="badge critical">⚠ YES</span> : <span style={{ color: 'var(--text-muted)' }}>No</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
