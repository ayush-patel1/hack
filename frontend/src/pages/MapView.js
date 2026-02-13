import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchViolations, fetchReference, fetchCurrent } from '../api';
import LeafletMap from '../components/LeafletMap';

export default function MapView() {
  const { data: violations } = useQuery({ queryKey: ['violations'], queryFn: fetchViolations });
  const { data: reference } = useQuery({ queryKey: ['reference'], queryFn: fetchReference });
  const { data: current } = useQuery({ queryKey: ['current'], queryFn: fetchCurrent });

  return (
    <div>
      <div className="card">
        <div className="card-header">🗺️ Interactive Compliance Map</div>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: 16 }}>
          Green dashed = Reference boundaries · Color-coded by violation severity · Click polygons for details
        </p>
        <LeafletMap
          reference={reference}
          violations={violations}
          current={current}
          mode="violations"
          height={600}
        />
      </div>

      {/* Map Legend Detail */}
      <div className="grid-4" style={{ marginTop: 16 }}>
        {[
          { label: 'Critical', color: '#e74c3c', desc: '>25% deviation' },
          { label: 'High', color: '#e67e22', desc: '15-25% deviation' },
          { label: 'Medium', color: '#f1c40f', desc: '5-15% deviation' },
          { label: 'Low', color: '#95a5a6', desc: '<5% deviation' },
        ].map(item => (
          <div key={item.label} className="card" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: item.color, flexShrink: 0,
            }} />
            <div>
              <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{item.label}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{item.desc}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
