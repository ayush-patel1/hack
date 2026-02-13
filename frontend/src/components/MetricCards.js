import React from 'react';

export default function MetricCards({ metrics }) {
  const cards = [
    { label: '📊 Total Plots Monitored', value: metrics.total_plots, color: 'blue' },
    { label: '⚠️ Violations Detected', value: metrics.total_violations, color: 'red' },
    { label: '🔴 Critical Issues', value: metrics.critical, color: 'yellow' },
    { label: '💰 Estimated Savings', value: `₹${(metrics.estimated_savings || 0).toLocaleString()}`, color: 'green' },
  ];

  return (
    <div className="metrics-grid">
      {cards.map((c, i) => (
        <div key={i} className={`metric-card ${c.color}`}>
          <div className="metric-value">{c.value}</div>
          <div className="metric-label">{c.label}</div>
        </div>
      ))}
    </div>
  );
}
