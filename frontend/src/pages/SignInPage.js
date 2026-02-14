import React from 'react';
import { SignIn } from '@clerk/clerk-react';

export default function SignInPage() {
    return (
        <div className="signin-page">
            <div className="signin-container">
                <div className="signin-branding">
                    <h1>🛡️ LandGuard AI</h1>
                    <p className="signin-welcome">Welcome to LandGuard</p>
                    <p>Automated Industrial Plot Compliance Monitor</p>
                    <p className="signin-subtitle">Powered by Computer Vision & GIS</p>
                </div>
                <div className="signin-widget">
                    <SignIn
                        appearance={{
                            elements: {
                                rootBox: { width: '100%' },
                                card: {
                                    boxShadow: 'none',
                                    border: 'none',
                                    backgroundColor: 'transparent',
                                },
                                headerTitle: { color: '#f0f2f5' },
                                headerSubtitle: { color: '#8892a8' },
                                formFieldLabel: { color: '#8892a8' },
                                formFieldInput: {
                                    backgroundColor: '#111827',
                                    borderColor: '#2a3050',
                                    color: '#f0f2f5',
                                },
                                footerActionLink: { color: '#4f8cf7' },
                                formButtonPrimary: {
                                    background: 'linear-gradient(135deg, #4f8cf7 0%, #8b5cf6 100%)',
                                },
                                dividerLine: { backgroundColor: '#2a3050' },
                                dividerText: { color: '#5a6480' },
                                socialButtonsBlockButton: {
                                    backgroundColor: '#111827',
                                    borderColor: '#2a3050',
                                    color: '#f0f2f5',
                                },
                                socialButtonsBlockButtonText: { color: '#f0f2f5' },
                                footer: { display: 'none' },
                            },
                        }}
                    />
                </div>
            </div>
        </div>
    );
}
