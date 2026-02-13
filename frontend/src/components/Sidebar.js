import React from 'react';
import {
  LayoutDashboard, GitCompare,
  Microscope, Table2, BarChart3, Download, Shield
} from 'lucide-react';

const iconMap = {
  LayoutDashboard, GitCompare,
  Microscope, Table2, BarChart3, Download,
};

export default function Sidebar({ pages, active, onNavigate }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <span className="logo-icon"><Shield size={24} /></span>
        <h2>LandGuard AI</h2>
      </div>
      <nav className="sidebar-nav">
        {pages.map(p => {
          const Icon = iconMap[p.icon] || LayoutDashboard;
          return (
            <div
              key={p.id}
              className={`nav-item ${active === p.id ? 'active' : ''}`}
              onClick={() => onNavigate(p.id)}
            >
              <Icon size={18} />
              <span>{p.label}</span>
            </div>
          );
        })}
      </nav>
      <div className="sidebar-footer">
        <p>LandGuard AI v1.0</p>
        <p style={{ marginTop: 4 }}>CSIDC Compliance Monitor</p>
      </div>
    </aside>
  );
}
