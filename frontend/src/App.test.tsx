import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from './App';

describe('App', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders the login interface when unauthenticated', async () => {
    render(<App />);
    expect(screen.getByTestId('login-page')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/NVRSMS Hub/i);
    expect(screen.getByTestId('login-email-input')).toBeInTheDocument();
    expect(screen.getByTestId('login-password-input')).toBeInTheDocument();
  });

  it('renders quick fill buttons for test profiles', () => {
    render(<App />);
    expect(screen.getByTestId('quick-fill-admin')).toBeInTheDocument();
    expect(screen.getByTestId('quick-fill-operator')).toBeInTheDocument();
  });
});
