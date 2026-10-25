import React from 'react';
import { Link } from 'react-router-dom';
import { Home } from 'lucide-react';

export const NotFoundPage: React.FC = () => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '70vh',
        textAlign: 'center',
      }}
      data-testid="not-found-page"
    >
      <h1 style={{ fontSize: '72px', fontWeight: 900, color: 'var(--color-primary)', margin: 0 }}>404</h1>
      <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)', marginTop: '8px' }}>
        Page Not Found
      </h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: '14px', maxWidth: '380px', marginTop: '8px', marginBottom: '24px' }}>
        The route you requested does not exist or may have been relocated.
      </p>
      <Link to="/dashboard" className="btn btn-primary">
        <Home size={16} /> Return to Dashboard
      </Link>
    </div>
  );
};
