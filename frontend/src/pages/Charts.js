import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSummary, fetchViolations } from '../api';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend
} from 'recharts';

const SEVERITY_COLORS = { CRITICAL: '#e74c3c', HIGH: '#e67e22', MEDIUM: '#f1c40f', LOW: '#95a5a6' };
const TYPE_COLORS = ['#4f8cf7', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#06b6d4'];

export default function Charts() {
  const { data: summary } = useQuery({ queryKey: ['summary'], queryFn: fetchSummary });
  const { data: violations } = useQuery({ queryKey: ['violations'], queryFn: fetchViolations });

  const features = violations?.features || [];
  const rows = features.map(f => ({ ...f.properties }));

  // Type distribution
  const typeCounts = {};
  rows.forEach(r => { const t = r.primary_violation || 'Unknown'; typeCounts[t] = (typeCounts[t] || 0) + 1; });
  const typeData = Object.entries(typeCounts).map(([k, v]) => ({ name: k.replace(/_/g, ' '), value: v }));

  // Severity counts
  const sevData = Object.entries(summary?.severity_breakdown || {}).map(([k, v]) => ({ name: k, value: v }));

  // Cost by type
  const costByType = {};
  rows.forEach(r => {
    const t = (r.primary_violation || 'Unknown').replace(/_/g, ' ');
    costByType[t] = (costByType[t] || 0) + (r.estimated_cost_inr || 0);
  });
  const costData = Object.entries(costByType).map(([k, v]) => ({ name: k, cost: v }));

  // Area diff distribution
  const areaDiffData = rows.map(r => ({
    name: r.plot_id || '',
    diff: r.area_diff_pct || 0,
  })).sort((a, b) => b.diff - a.diff);

  return (
    <div>
      <div className="grid-2">
        {/* Pie: Violation Types */}
        <div className="card">
          <div className="card-header">Violation Distribution by Type</div>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie data={typeData} cx="50%" cy="50%" outerRadius={105} innerRadius={55}
                paddingAngle={3} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                {typeData.map((_, i) => <Cell key={i} fill={TYPE_COLORS[i % TYPE_COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#1a1f35', border: '1px solid #2a3050', borderRadius: 8, color: '#f0f2f5' }} />
              <Legend wrapperStyle={{ color: '#8892a8', fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Bar: Severity */}
        <div className="card">
          <div className="card-header">Violations by Severity</div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={sevData}>
              <XAxis dataKey="name" tick={{ fill: '#8892a8', fontSize: 12 }} axisLine={{ stroke: '#2a3050' }} tickLine={false} />
              <YAxis tick={{ fill: '#8892a8', fontSize: 11 }} axisLine={{ stroke: '#2a3050' }} tickLine={false} />
              <Tooltip contentStyle={{ background: '#1a1f35', border: '1px solid #2a3050', borderRadius: 8, color: '#f0f2f5' }} />
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                {sevData.map((entry, i) => <Cell key={i} fill={SEVERITY_COLORS[entry.name] || '#666'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Cost Impact */}
      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">💰 Estimated Cost Impact by Violation Type (₹)</div>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={costData}>
            <XAxis dataKey="name" tick={{ fill: '#8892a8', fontSize: 11 }} axisLine={{ stroke: '#2a3050' }} tickLine={false} />
            <YAxis tick={{ fill: '#8892a8', fontSize: 11 }} axisLine={{ stroke: '#2a3050' }} tickLine={false}
              tickFormatter={v => `₹${(v / 1000).toFixed(0)}K`} />
            <Tooltip
              contentStyle={{ background: '#1a1f35', border: '1px solid #2a3050', borderRadius: 8, color: '#f0f2f5' }}
              formatter={v => [`₹${v.toLocaleString()}`, 'Cost']}
            />
            <Bar dataKey="cost" radius={[6, 6, 0, 0]}>
              {costData.map((_, i) => <Cell key={i} fill={TYPE_COLORS[i % TYPE_COLORS.length]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Area Difference chart */}
      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">📐 Area Deviation by Plot</div>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={areaDiffData}>
            <XAxis dataKey="name" tick={{ fill: '#8892a8', fontSize: 10 }} axisLine={{ stroke: '#2a3050' }} tickLine={false} />
            <YAxis tick={{ fill: '#8892a8', fontSize: 11 }} axisLine={{ stroke: '#2a3050' }} tickLine={false}
              tickFormatter={v => `${v}%`} />
            <Tooltip
              contentStyle={{ background: '#1a1f35', border: '1px solid #2a3050', borderRadius: 8, color: '#f0f2f5' }}
              formatter={v => [`${v.toFixed(1)}%`, 'Area Diff']}
            />
            <Bar dataKey="diff" radius={[4, 4, 0, 0]}>
              {areaDiffData.map((entry, i) => (
                <Cell key={i} fill={entry.diff > 25 ? '#e74c3c' : entry.diff > 10 ? '#f59e0b' : '#10b981'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Cost-Benefit comparison */}
      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">📊 Cost-Benefit Analysis: Manual vs LandGuard AI</div>
        <div className="grid-2">
          <table className="data-table">
            <thead>
              <tr><th>Metric</th><th>Manual Survey</th><th>LandGuard AI</th></tr>
            </thead>
            <tbody>
              <tr><td>Cost per plot</td><td>₹25,000</td><td style={{ color: '#10b981', fontWeight: 600 }}>₹5,000</td></tr>
              <tr><td>Time per cycle</td><td>2-3 weeks</td><td style={{ color: '#10b981', fontWeight: 600 }}>&lt; 2 minutes</td></tr>
              <tr><td>Accuracy</td><td>~85%</td><td style={{ color: '#10b981', fontWeight: 600 }}>~95%</td></tr>
              <tr><td>Scalability</td><td>50 plots/cycle</td><td style={{ color: '#10b981', fontWeight: 600 }}>1000+ plots/cycle</td></tr>
              <tr><td><strong>Annual Savings</strong></td><td>—</td><td style={{ color: '#10b981', fontWeight: 800 }}>₹8,00,000+</td></tr>
            </tbody>
          </table>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 8 }}>
            <div style={{ fontSize: '3rem', fontWeight: 900, background: 'var(--gradient-green)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              80%
            </div>
            <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Cost Reduction</div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'center', maxWidth: 250 }}>
              LandGuard AI reduces monitoring costs by 80% while improving accuracy by 10%
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
