import React, { useState, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchLivePlots, fetchLiveBoundaries, fetchReference, fetchCurrent,
  fetchAnalysisResults, fetchCsidcPlots,
  listCsidcAreas, fetchCsidcLive, runAnalysis, generateReport,
} from '../api';
import LeafletMap from '../components/LeafletMap';
import { Search, Download, Play, RefreshCw, Trash2, List, Camera } from 'lucide-react';
import html2canvas from 'html2canvas';

export default function PlotComparison() {
  const queryClient = useQueryClient();
  const [areaFilter, setAreaFilter] = useState('');
  const [statusMsg, setStatusMsg] = useState('');
  const [areas, setAreas] = useState([]);
  const [activeSection, setActiveSection] = useState('live'); // live | csidc | comparison
  const originalMapRef = useRef(null);
  const comparisonMapRef = useRef(null);
  const [capturingMaps, setCapturingMaps] = useState(false);

  const { data: livePlots } = useQuery({ queryKey: ['livePlots'], queryFn: fetchLivePlots });
  const { data: liveBoundaries } = useQuery({ queryKey: ['liveBoundaries'], queryFn: fetchLiveBoundaries });
  const { data: reference } = useQuery({ queryKey: ['reference'], queryFn: fetchReference });
  const { data: current } = useQuery({ queryKey: ['current'], queryFn: fetchCurrent });
  const { data: analysisResults } = useQuery({ queryKey: ['analysisResults'], queryFn: fetchAnalysisResults });
  const { data: csidcPlots } = useQuery({ queryKey: ['csidcPlots'], queryFn: fetchCsidcPlots });

  const hasLiveData = livePlots?.features?.length > 0;
  const liveFeatures = livePlots?.features || [];

  // Metrics for live data
  const allotedCount = liveFeatures.filter(f => {
    const s = ((f.properties?.STATUS || '') + (f.properties?.LABEL || '')).toUpperCase();
    return s.includes('ALLOT');
  }).length;
  const vacantCount = liveFeatures.filter(f => {
    const s = ((f.properties?.STATUS || '') + (f.properties?.LABEL || '')).toUpperCase();
    return s.includes('VACANT');
  }).length;
  const areasSet = new Set(liveFeatures.map(f => f.properties?.INDUSTRIAL || ''));

  // Mutations
  const fetchAreasMut = useMutation({
    mutationFn: listCsidcAreas,
    onSuccess: (data) => setAreas(data.areas || []),
    onError: (err) => setStatusMsg(`Error: ${err.message}`),
  });

  const fetchPlotsMut = useMutation({
    mutationFn: () => fetchCsidcLive(areaFilter || null),
    onSuccess: (data) => {
      setStatusMsg(`Fetched ${data.plots_count} plots and ${data.boundaries_count} boundaries!`);
      queryClient.invalidateQueries(['livePlots', 'liveBoundaries']);
    },
    onError: (err) => setStatusMsg(`Fetch failed: ${err.message}`),
  });

  const analysisMut = useMutation({
    mutationFn: runAnalysis,
    onSuccess: (data) => {
      setStatusMsg(`Analysis complete for ${data.count} plots!`);
      queryClient.invalidateQueries(['analysisResults']);
    },
    onError: (err) => setStatusMsg(`Analysis failed: ${err.message}`),
  });

  const reportMut = useMutation({
    mutationFn: generateReport,
    onSuccess: (response) => {
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'Analysis_Report.pdf';
      a.click();
      setCapturingMaps(false);
      setStatusMsg('Report downloaded!');
    },
    onError: (err) => { setCapturingMaps(false); setStatusMsg(`Report generation failed: ${err.message}`); },
  });

  const captureMapAsBase64 = useCallback(async (ref) => {
    if (!ref.current) return null;
    try {
      const canvas = await html2canvas(ref.current, {
        useCORS: true,
        allowTaint: true,
        backgroundColor: '#0a0e1a',
        scale: 2,
        logging: false,
      });
      return canvas.toDataURL('image/png').split(',')[1];
    } catch (err) {
      console.warn('Map capture failed:', err);
      return null;
    }
  }, []);

  const handleGenerateReport = useCallback(async () => {
    setCapturingMaps(true);
    setStatusMsg('Capturing map images for report...');

    // Small delay to ensure maps are fully rendered
    await new Promise(r => setTimeout(r, 1500));

    const originalMap = await captureMapAsBase64(originalMapRef);
    const comparisonMap = await captureMapAsBase64(comparisonMapRef);

    setStatusMsg('Generating PDF report...');
    reportMut.mutate({ original_map: originalMap, comparison_map: comparisonMap });
  }, [captureMapAsBase64, reportMut]);

  // Plot table data
  const tableRows = liveFeatures.slice(0, 200).map(f => {
    const p = f.properties || {};
    let status = p.STATUS || '';
    if (!status) {
      const lbl = (p.LABEL || '').toUpperCase();
      if (lbl.includes('ALLOT')) status = 'ALLOTTED';
      else if (lbl.includes('VACANT')) status = 'VACANT';
    }
    return {
      plotNo: p.PLOT_NO || '',
      area: p.INDUSTRIAL || '',
      type: p.TYPE || '',
      status,
      remark: p.REMARK || '',
      label: p.LABEL_2 || '',
    };
  });

  // Analysis results table
  const analysisRows = analysisResults || [];

  return (
    <div>
      {/* Sub-tabs */}
      <div className="tabs">
        <div className={`tab ${activeSection === 'live' ? 'active' : ''}`} onClick={() => setActiveSection('live')}>
          <RefreshCw size={16} /> Live CSIDC Data
        </div>
        <div className={`tab ${activeSection === 'csidc' ? 'active' : ''}`} onClick={() => setActiveSection('csidc')}>
          <Search size={16} /> CSIDC Scraped
        </div>
        <div className={`tab ${activeSection === 'comparison' ? 'active' : ''}`} onClick={() => setActiveSection('comparison')}>
          <Play size={16} /> Comparison & Analysis
        </div>
      </div>

      {statusMsg && (
        <div className="alert alert-info" style={{ marginBottom: 16 }}>
          {statusMsg}
          <button onClick={() => setStatusMsg('')} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: 16 }}>✕</button>
        </div>
      )}

      {/* ── SECTION: LIVE DATA ── */}
      {activeSection === 'live' && (
        <div>
          <div className="card">
            <div className="card-header">🔄 Fetch Live Data from CSIDC GeoServer</div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 16 }}>
              Real-time WFS data from cggis.cgstate.gov.in — no authentication required
            </p>

            <div className="grid-3" style={{ marginBottom: 16 }}>
              <div className="input-group">
                <label>🏭 Industrial Area Filter</label>
                <input
                  className="input-field"
                  placeholder="e.g. URLA, SILTARA, TIFRA"
                  value={areaFilter}
                  onChange={e => setAreaFilter(e.target.value)}
                />
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
                <button className="btn btn-primary" onClick={() => fetchPlotsMut.mutate()} disabled={fetchPlotsMut.isPending}>
                  <Download size={16} /> {fetchPlotsMut.isPending ? 'Fetching...' : 'Fetch Plots'}
                </button>
                <button className="btn btn-secondary" onClick={() => fetchAreasMut.mutate()} disabled={fetchAreasMut.isPending}>
                  <List size={16} /> List Areas
                </button>
              </div>
            </div>

            {areas.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
                {areas.map(a => (
                  <span key={a} className="badge compliant" style={{ cursor: 'pointer' }}
                    onClick={() => setAreaFilter(a)}>
                    {a}
                  </span>
                ))}
              </div>
            )}
          </div>

          {hasLiveData && (
            <>
              {/* Metrics */}
              <div className="metrics-grid">
                <div className="metric-card blue">
                  <div className="metric-value">{liveFeatures.length.toLocaleString()}</div>
                  <div className="metric-label">📊 Total Plots</div>
                </div>
                <div className="metric-card green">
                  <div className="metric-value">{allotedCount.toLocaleString()}</div>
                  <div className="metric-label">✅ Allotted</div>
                </div>
                <div className="metric-card yellow">
                  <div className="metric-value">{vacantCount.toLocaleString()}</div>
                  <div className="metric-label">⚠️ Vacant</div>
                </div>
                <div className="metric-card" style={{ background: 'var(--gradient-primary)' }}>
                  <div className="metric-value">{areasSet.size}</div>
                  <div className="metric-label">🏭 Industrial Areas</div>
                </div>
              </div>

              {/* Live Map */}
              <div className="card" style={{ marginTop: 16 }}>
                <div className="card-header">🗺️ Live CSIDC Plot Data</div>
                <LeafletMap
                  livePlots={livePlots}
                  liveBoundaries={liveBoundaries}
                  mode="live"
                  height={550}
                />
              </div>

              {/* Plot Table */}
              <div className="card" style={{ marginTop: 16 }}>
                <div className="card-header">📋 Plot Details</div>
                <div style={{ maxHeight: 400, overflow: 'auto' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Plot No</th>
                        <th>Industrial Area</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Remark</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tableRows.map((r, i) => (
                        <tr key={i}>
                          <td>{r.plotNo}</td>
                          <td>{r.area}</td>
                          <td>{r.type}</td>
                          <td>
                            <span className={`badge ${r.status.includes('ALLOT') ? 'compliant' : r.status.includes('VACANT') ? 'vacant' : 'low'}`}>
                              {r.status || '—'}
                            </span>
                          </td>
                          <td>{r.remark}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── SECTION: CSIDC SCRAPED ── */}
      {activeSection === 'csidc' && (
        <div>
          <div className="card">
            <div className="card-header">🏗️ CSIDC Scraped Plot Polygons</div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 16 }}>
              Polygons extracted from CSIDC GeoServer WMS tiles
            </p>
            {csidcPlots?.features?.length ? (
              <>
                <div className="alert alert-info">
                  📊 <b>{csidcPlots.features.length} polygons</b> scraped from CSIDC GeoServer
                </div>
                <LeafletMap csidcPlots={csidcPlots} mode="csidc" height={500} />
              </>
            ) : (
              <div className="alert alert-warning">
                No CSIDC scraped data found (data/csidc_real_plots.geojson)
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── SECTION: COMPARISON & ANALYSIS ── */}
      {activeSection === 'comparison' && (
        <div>
          {/* Analysis Controls */}
          <div className="card">
            <div className="card-header">🔬 Run CV Analysis on Plot Data</div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 16 }}>
              Generates simulated satellite imagery and runs edge detection to classify plot status
            </p>
            <div style={{ display: 'flex', gap: 12 }}>
              <button className="btn btn-primary" onClick={() => analysisMut.mutate()} disabled={analysisMut.isPending}>
                <Play size={16} /> {analysisMut.isPending ? 'Analyzing...' : 'Run Analysis'}
              </button>
              <button className="btn btn-success" onClick={handleGenerateReport}
                disabled={reportMut.isPending || capturingMaps || !analysisRows.length}>
                <Camera size={16} /> {capturingMaps ? 'Capturing Maps...' : reportMut.isPending ? 'Generating PDF...' : 'Generate PDF Report'}
              </button>
            </div>
          </div>

          {/* Original Live Data Map */}
          <div className="card" style={{ marginTop: 16 }}>
            <div className="card-header">🗺️ Original CSIDC Plot Data</div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 12 }}>
              Live WFS data from CSIDC GeoServer — Red Dashed = Area Boundary · Colored Fill = Plot Status
            </p>
            <div ref={originalMapRef}>
              <LeafletMap
                livePlots={livePlots}
                liveBoundaries={liveBoundaries}
                mode="live"
                height={450}
              />
            </div>
          </div>

          {/* Comparison Map */}
          <div className="card" style={{ marginTop: 16 }}>
            <div className="card-header">📐 Allotted (Reference) vs Current Development</div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 12 }}>
              Blue Dashed = Allotted Boundary · Colored Fill = Analyzed Status
            </p>
            <div ref={comparisonMapRef}>
              <LeafletMap
                reference={reference}
                current={current}
                livePlots={livePlots}
                analysisResults={analysisResults}
                mode="comparison"
                height={520}
              />
            </div>
          </div>

          {/* Analysis Results Table */}
          {analysisRows.length > 0 && (
            <div className="card" style={{ marginTop: 16 }}>
              <div className="card-header">📊 Analysis Results ({analysisRows.length} plots)</div>

              {/* Summary */}
              <div className="grid-4" style={{ marginBottom: 16 }}>
                {[
                  { label: 'Vacant', count: analysisRows.filter(r => r.status === 'Vacant').length, color: '#f59e0b' },
                  { label: 'Partial', count: analysisRows.filter(r => r.status === 'Partially Developed').length, color: '#e67e22' },
                  { label: 'Developed', count: analysisRows.filter(r => r.status === 'Fully Developed').length, color: '#10b981' },
                  { label: 'Deviations', count: analysisRows.filter(r => r.has_deviation).length, color: '#ef4444' },
                ].map(item => (
                  <div key={item.label} style={{ textAlign: 'center', padding: 12, background: 'var(--bg-secondary)', borderRadius: 8 }}>
                    <div style={{ fontSize: '1.5rem', fontWeight: 800, color: item.color }}>{item.count}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{item.label}</div>
                  </div>
                ))}
              </div>

              <div style={{ maxHeight: 400, overflow: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Plot ID</th>
                      <th>Zone</th>
                      <th>Area (m²)</th>
                      <th>Developed %</th>
                      <th>Status</th>
                      <th>Deviation</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysisRows.map((r, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 600 }}>{r.plot_id}</td>
                        <td>{r.zone || '—'}</td>
                        <td>{(r.area_sqm || 0).toFixed(1)}</td>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div style={{
                              width: 60, height: 6, background: 'var(--bg-secondary)', borderRadius: 3, overflow: 'hidden',
                            }}>
                              <div style={{
                                width: `${Math.min(r.developed_pct || 0, 100)}%`, height: '100%',
                                background: (r.developed_pct || 0) < 15 ? '#f59e0b' : (r.developed_pct || 0) < 60 ? '#e67e22' : '#10b981',
                                borderRadius: 3,
                              }} />
                            </div>
                            <span>{(r.developed_pct || 0).toFixed(1)}%</span>
                          </div>
                        </td>
                        <td>
                          <span className={`badge ${
                            r.status === 'Vacant' ? 'vacant' :
                            r.status === 'Partially Developed' ? 'medium' : 'compliant'
                          }`}>
                            {r.status}
                          </span>
                        </td>
                        <td>
                          {r.has_deviation ? (
                            <span className="badge critical">⚠ YES</span>
                          ) : (
                            <span style={{ color: 'var(--text-muted)' }}>No</span>
                          )}
                        </td>
                        <td style={{ fontSize: '0.78rem', color: r.has_deviation ? '#f87171' : 'var(--text-muted)' }}>
                          {r.deviation_reason || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
