import React from 'react';
import { UserButton } from '@clerk/clerk-react';

export default function Header() {
  return (
    <div className="page-header">
      <div>
        <h1>🛡️ LandGuard AI</h1>
        <p>Automated Industrial Plot Compliance Monitor — Powered by Computer Vision & GIS</p>
      </div>
      <UserButton
        appearance={{
          elements: {
            avatarBox: { width: '36px', height: '36px' },
          },
        }}
      />
    </div>
  );
}

