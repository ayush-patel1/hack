import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const SEVERITY_COLORS = {
  CRITICAL: '#e74c3c',
  HIGH: '#e67e22',
  MEDIUM: '#f1c40f',
  LOW: '#95a5a6',
};

const STATUS_COLORS = {
  ALLOTTED: '#2ecc71',
  ALLOTED: '#2ecc71',
  VACANT: '#e74c3c',
  PROPOSED: '#f39c12',
  CANCELLED: '#95a5a6',
};

export default function LeafletMap({
  reference,
  violations,
  current,
  livePlots,
  liveBoundaries,
  analysisResults,
  height = 520,
  mode = 'violations', // 'violations' | 'live' | 'comparison' | 'csidc'
  csidcPlots,
}) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);

  useEffect(() => {
    if (mapInstance.current) {
      mapInstance.current.remove();
      mapInstance.current = null;
    }

    const map = L.map(mapRef.current, {
      zoomControl: true,
    }).setView([21.2514, 81.6296], 15);

    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Esri',
      maxZoom: 19,
    }).addTo(map);

    mapInstance.current = map;

    const allCoords = [];

    const extractCoords = (geom) => {
      if (!geom) return;
      if (geom.type === 'Polygon') {
        (geom.coordinates[0] || []).forEach(c => allCoords.push([c[1], c[0]]));
      } else if (geom.type === 'MultiPolygon') {
        (geom.coordinates[0]?.[0] || []).forEach(c => allCoords.push([c[1], c[0]]));
      }
    };

    if (mode === 'violations') {
      // Reference boundaries (green dashed)
      if (reference?.features) {
        const refGroup = L.featureGroup();
        reference.features.forEach(feat => {
          if (feat.geometry?.type !== 'Polygon') return;
          const coords = feat.geometry.coordinates[0].map(c => [c[1], c[0]]);
          extractCoords(feat.geometry);
          L.polygon(coords, {
            color: '#38ef7d', weight: 2, fill: true,
            fillColor: '#38ef7d', fillOpacity: 0.15, dashArray: '6',
          }).bindTooltip(`📐 ${feat.properties?.plot_id || ''} — Reference`).addTo(refGroup);
        });
        refGroup.addTo(map);
      }

      // Violations
      const violatedIds = new Set();
      if (violations?.features) {
        violations.features.forEach(feat => {
          violatedIds.add(feat.properties?.plot_id);
          const p = feat.properties || {};
          const sev = p.severity || 'LOW';
          const color = SEVERITY_COLORS[sev] || '#e74c3c';
          if (feat.geometry?.type !== 'Polygon') return;
          const coords = feat.geometry.coordinates[0].map(c => [c[1], c[0]]);
          extractCoords(feat.geometry);
          L.polygon(coords, {
            color, weight: 3, fill: true,
            fillColor: color, fillOpacity: 0.35,
          }).bindTooltip(
            `<b>🏗️ ${p.plot_id || ''}</b><br>Type: ${p.primary_violation || ''}<br>Severity: ${sev}<br>Area Diff: ${(p.area_diff_pct || 0).toFixed(1)}%`
          ).addTo(map);
        });
      }

      // Compliant current
      if (current?.features) {
        current.features.forEach(feat => {
          const pid = feat.properties?.plot_id;
          if (violatedIds.has(pid)) return;
          if (feat.geometry?.type !== 'Polygon') return;
          const coords = feat.geometry.coordinates[0].map(c => [c[1], c[0]]);
          extractCoords(feat.geometry);
          L.polygon(coords, {
            color: '#2ecc71', weight: 2, fill: true,
            fillColor: '#2ecc71', fillOpacity: 0.25,
          }).bindTooltip(`✅ ${pid} — Compliant`).addTo(map);
        });
      }
    }

    if (mode === 'live' && livePlots?.features) {
      livePlots.features.forEach(feat => {
        const geom = feat.geometry;
        if (!geom) return;
        const props = feat.properties || {};
        let coordsList = [];
        if (geom.type === 'Polygon') coordsList = [geom.coordinates[0]];
        else if (geom.type === 'MultiPolygon') coordsList = [geom.coordinates[0][0]];

        let status = (props.STATUS || '').toUpperCase();
        if (!status) {
          const label = (props.LABEL || '').toUpperCase();
          if (label.includes('ALLOT')) status = 'ALLOTTED';
          else if (label.includes('VACANT')) status = 'VACANT';
          else if (label.includes('PROPOSED')) status = 'PROPOSED';
        }

        let color = '#3498db';
        for (const [key, c] of Object.entries(STATUS_COLORS)) {
          if (status.includes(key)) { color = c; break; }
        }

        coordsList.forEach(coords => {
          const latlng = coords.map(c => [c[1], c[0]]);
          allCoords.push(...latlng);
          L.polygon(latlng, {
            color, weight: 2, fill: true, fillColor: color, fillOpacity: 0.25,
          }).bindTooltip(
            `<b>Plot ${props.PLOT_NO || '?'}</b><br>Area: ${props.INDUSTRIAL || 'N/A'}<br>Status: ${status || 'N/A'}<br>Type: ${props.TYPE || 'N/A'}`
          ).addTo(map);
        });
      });

      // Boundaries
      if (liveBoundaries?.features) {
        liveBoundaries.features.forEach(feat => {
          const geom = feat.geometry;
          if (!geom) return;
          let coordsList = [];
          if (geom.type === 'Polygon') coordsList = [geom.coordinates[0]];
          else if (geom.type === 'MultiPolygon') coordsList = [geom.coordinates[0][0]];
          coordsList.forEach(coords => {
            const latlng = coords.map(c => [c[1], c[0]]);
            L.polygon(latlng, {
              color: '#e74c3c', weight: 4, fill: false, dashArray: '10 5',
            }).bindTooltip(`🏭 ${feat.properties?.industrial || 'Unknown'} — Boundary`).addTo(map);
          });
        });
      }
    }

    if (mode === 'comparison') {
      // Build a lookup from plot_id / PLOT_NO → geometry from livePlots
      const geoLookup = new Map(); // key → feature
      const geoByIndex = [];       // fallback: by index
      const refData = livePlots?.features?.length ? livePlots : reference;

      if (refData?.features) {
        refData.features.forEach((feat, idx) => {
          const p = feat.properties || {};
          const pid = String(p.PLOT_NO || p.plot_id || '').trim();
          if (pid) geoLookup.set(pid, feat);
          geoByIndex.push(feat);
        });
      }

      // Reference layer (blue dashed boundaries)
      if (refData?.features) {
        refData.features.forEach(feat => {
          const geom = feat.geometry;
          if (!geom) return;
          let coordsList = [];
          if (geom.type === 'Polygon') coordsList = [geom.coordinates[0]];
          else if (geom.type === 'MultiPolygon') coordsList = geom.coordinates.map(p => p[0]);

          const pid = feat.properties?.PLOT_NO || feat.properties?.plot_id || '';
          coordsList.forEach(coords => {
            const latlng = coords.map(c => [c[1], c[0]]);
            allCoords.push(...latlng);
            L.polygon(latlng, {
              color: '#3498db', weight: 2, fill: false, dashArray: '5 5',
            }).bindTooltip(`Allotted: ${pid}`).addTo(map);
          });
        });
      }

      // Analysis results overlay — match to geometry and color by status
      if (analysisResults?.length) {
        const matchedIds = new Set();

        analysisResults.forEach((r, idx) => {
          const status = r.status || 'Unknown';
          const pct = r.developed_pct || 0;
          const hasDev = r.has_deviation || false;

          // Determine color based on status + deviation
          let color;
          if (hasDev) {
            color = '#e74c3c'; // Encroachment / Deviation = red
          } else if (status === 'Vacant') {
            color = '#f1c40f'; // Yellow
          } else if (status === 'Partially Developed') {
            color = '#e67e22'; // Orange
          } else if (status === 'Fully Developed') {
            color = '#2ecc71'; // Green
          } else {
            color = '#9b59b6'; // Purple for unknown
          }

          // Find matching geometry: try by plot_id, then by index
          const pid = String(r.plot_id || r.plot_number || '').trim();
          let feat = pid ? geoLookup.get(pid) : null;
          if (!feat && idx < geoByIndex.length) {
            feat = geoByIndex[idx];
          }
          if (!feat) return;

          const geom = feat.geometry;
          if (!geom) return;
          let coordsList = [];
          if (geom.type === 'Polygon') coordsList = [geom.coordinates[0]];
          else if (geom.type === 'MultiPolygon') coordsList = geom.coordinates.map(p => p[0]);

          const label = `<b>Plot: ${r.plot_id || r.plot_number || idx}</b><br>` +
            `Status: ${status}<br>` +
            `Developed: ${pct.toFixed(1)}%<br>` +
            `Area: ${(r.area_sqm || 0).toFixed(1)} m²` +
            (hasDev ? `<br><b style="color:#e74c3c">⚠ ${r.deviation_reason || 'Deviation'}</b>` : '');

          coordsList.forEach(coords => {
            const latlng = coords.map(c => [c[1], c[0]]);
            L.polygon(latlng, {
              color, weight: 2.5, fill: true, fillColor: color, fillOpacity: 0.45,
            }).bindTooltip(label).addTo(map);
          });

          if (pid) matchedIds.add(pid);
        });

        // Draw remaining unmatched live features in grey
        if (refData?.features) {
          refData.features.forEach(feat => {
            const p = feat.properties || {};
            const pid = String(p.PLOT_NO || p.plot_id || '').trim();
            if (matchedIds.has(pid)) return;
            const geom = feat.geometry;
            if (!geom) return;
            let coordsList = [];
            if (geom.type === 'Polygon') coordsList = [geom.coordinates[0]];
            else if (geom.type === 'MultiPolygon') coordsList = geom.coordinates.map(pp => pp[0]);
            coordsList.forEach(coords => {
              const latlng = coords.map(c => [c[1], c[0]]);
              L.polygon(latlng, {
                color: '#95a5a6', weight: 1.5, fill: true, fillColor: '#95a5a6', fillOpacity: 0.15,
              }).bindTooltip(`Plot: ${pid} (No analysis data)`).addTo(map);
            });
          });
        }
      } else {
        // No analysis results — fallback: draw current overlay
        if (current?.features) {
          current.features.forEach(feat => {
            if (feat.geometry?.type !== 'Polygon') return;
            const coords = feat.geometry.coordinates[0].map(c => [c[1], c[0]]);
            const vtype = feat.properties?.violation_type || 'COMPLIANT';
            const color = vtype === 'COMPLIANT' ? '#2ecc71' : '#e74c3c';
            L.polygon(coords, {
              color, weight: 2, fill: true, fillColor: color, fillOpacity: 0.4,
            }).bindTooltip(`Status: ${vtype}`).addTo(map);
          });
        }
      }
    }

    if (mode === 'csidc' && csidcPlots?.features) {
      const colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
        '#1abc9c', '#e67e22', '#00bcd4', '#ff5722', '#607d8b'];
      csidcPlots.features.forEach((feat, i) => {
        if (feat.geometry?.type !== 'Polygon') return;
        const coords = feat.geometry.coordinates[0].map(c => [c[1], c[0]]);
        allCoords.push(...coords);
        const color = colors[i % colors.length];
        const pid = feat.properties?.plot_id || `Plot_${i}`;
        L.polygon(coords, {
          color, weight: 3, fill: true, fillColor: color, fillOpacity: 0.3,
        }).bindTooltip(`🏗️ ${pid} | Area: ${(feat.properties?.area_px || 0).toLocaleString()} px`).addTo(map);
      });
    }

    // Fit bounds
    if (allCoords.length > 0) {
      const bounds = L.latLngBounds(allCoords);
      map.fitBounds(bounds, { padding: [30, 30] });
    }

    // Legend
    const legend = L.control({ position: 'bottomleft' });
    legend.onAdd = () => {
      const div = L.DomUtil.create('div');
      div.style.cssText = 'background:rgba(0,0,0,0.85);padding:12px 16px;border-radius:8px;color:white;font-size:12px;font-family:Inter,sans-serif;line-height:1.6;';
      if (mode === 'violations') {
        div.innerHTML = `<b>Legend</b><br>
          <span style="color:#38ef7d">━━</span> Reference &nbsp;
          <span style="color:#2ecc71">■</span> Compliant &nbsp;
          <span style="color:#e74c3c">■</span> Critical &nbsp;
          <span style="color:#e67e22">■</span> High &nbsp;
          <span style="color:#f1c40f">■</span> Medium &nbsp;
          <span style="color:#95a5a6">■</span> Low`;
      } else if (mode === 'live') {
        div.innerHTML = `<b>Live Data Legend</b><br>
          <span style="color:#e74c3c">━ ━</span> Area Boundary &nbsp;
          <span style="color:#2ecc71">■</span> Allotted &nbsp;
          <span style="color:#e74c3c">■</span> Vacant &nbsp;
          <span style="color:#f39c12">■</span> Proposed &nbsp;
          <span style="color:#3498db">■</span> Other`;
      } else if (mode === 'comparison') {
        div.innerHTML = `<b>Analysis Legend</b><br>
          <span style="color:#3498db">╍╍</span> Allotted Boundary<br>
          <span style="color:#2ecc71">■</span> Fully Developed (&gt;60%)<br>
          <span style="color:#e67e22">■</span> Partially Developed (15-60%)<br>
          <span style="color:#f1c40f">■</span> Vacant (&lt;15%)<br>
          <span style="color:#e74c3c">■</span> <b>Encroachment / Deviation</b><br>
          <span style="color:#9b59b6">■</span> Unknown Status<br>
          <span style="color:#95a5a6">■</span> Unanalyzed`;
      }
      return div;
    };
    legend.addTo(map);

    return () => {
      if (mapInstance.current) {
        mapInstance.current.remove();
        mapInstance.current = null;
      }
    };
  }, [reference, violations, current, livePlots, liveBoundaries, analysisResults, mode, csidcPlots, height]);

  return (
    <div className="map-container">
      <div ref={mapRef} style={{ height: `${height}px` }} />
    </div>
  );
}
