import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSummary, fetchViolations, fetchReference, fetchCurrent } from '../api';
import MetricCards from '../components/MetricCards';
import LeafletMap from '../components/LeafletMap';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend
} from 'recharts';

const SEVERITY_COLORS = { CRITICAL: '#e74c3c', HIGH: '#e67e22', MEDIUM: '#f1c40f', LOW: '#95a5a6' };
const TYPE_COLORS = ['#4f8cf7', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#06b6d4'];

export default function Dashboard() {
  const { data: summary, isLoading } = useQuery({ queryKey: ['summary'], queryFn: fetchSummary });
  const { data: violations } = useQuery({ queryKey: ['violations'], queryFn: fetchViolations });
  const { data: reference } = useQuery({ queryKey: ['reference'], queryFn: fetchReference });
  const { data: current } = useQuery({ queryKey: ['current'], queryFn: fetchCurrent });

  if (isLoading) return <div className="spinner" />;

  const sevData = Object.entries(summary?.severity_breakdown || {}).map(([k, v]) => ({ name: k, value: v }));
  const typeData = Object.entries(summary?.type_breakdown || {}).map(([k, v]) => ({ name: k, value: v }));

  return (
    <div>
      <MetricCards metrics={summary || {}} />

      <div className="grid-2" style={{ marginBottom: 20 }}>
        {/* Severity Pie */}
        <div className="card">
          <div className="card-header">Violations by Severity</div>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={sevData} cx="50%" cy="50%" outerRadius={100} innerRadius={50}
                paddingAngle={3} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                {sevData.map((entry, i) => (
                  <Cell key={i} fill={SEVERITY_COLORS[entry.name] || '#666'} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: '#1a1f35', border: '1px solid #2a3050', borderRadius: 8, color: '#f0f2f5' }} />
              <Legend wrapperStyle={{ color: '#8892a8', fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Type Bar */}
        <div className="card">
          <div className="card-header">Violations by Type</div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={typeData}>
              <XAxis dataKey="name" tick={{ fill: '#8892a8', fontSize: 11 }} axisLine={{ stroke: '#2a3050' }} tickLine={false} />
              <YAxis tick={{ fill: '#8892a8', fontSize: 11 }} axisLine={{ stroke: '#2a3050' }} tickLine={false} />
              <Tooltip contentStyle={{ background: '#1a1f35', border: '1px solid #2a3050', borderRadius: 8, color: '#f0f2f5' }} />
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                {typeData.map((_, i) => <Cell key={i} fill={TYPE_COLORS[i % TYPE_COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Map Preview */}
      <div className="card">
        <div className="card-header">🗺️ Compliance Map Overview</div>
        <LeafletMap
          reference={reference}
          violations={violations}
          current={current}
          mode="violations"
          height={420}
        />
      </div>

      {/* Quick Stats */}
      <div className="grid-3" style={{ marginTop: 20 }}>
        <div className="card" style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '2rem', fontWeight: 800, color: '#4f8cf7' }}>
            ₹{(summary?.total_estimated_cost_inr || 0).toLocaleString()}
          </div>
          <div style={{ fontSize: '0.82rem', color: '#8892a8', marginTop: 4 }}>
            Total Estimated Violation Cost
          </div>
        </div>
        <div className="card" style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '2rem', fontWeight: 800, color: '#10b981' }}>
            {summary?.compliant || 0}
          </div>
          <div style={{ fontSize: '0.82rem', color: '#8892a8', marginTop: 4 }}>
            Compliant Plots
          </div>
        </div>
        <div className="card" style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '2rem', fontWeight: 800, color: '#f59e0b' }}>
            &lt; 2 min
          </div>
          <div style={{ fontSize: '0.82rem', color: '#8892a8', marginTop: 4 }}>
            Avg Analysis Time Per Plot
          </div>
        </div>
      </div>
    </div>
  );
}
