import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { Shield, Lock, Mail, KeyRound, ArrowRight } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { login, totpRequired, pendingEmail } = useAuth();
  const { showToast } = useToast();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const activeEmail = totpRequired && pendingEmail ? pendingEmail : email;
      const result = await login({
        email: activeEmail,
        password,
        totp_code: totpCode.trim() || undefined,
      });

      if (result.success) {
        showToast('Successfully authenticated', 'success');
        navigate('/dashboard');
      } else if (result.totpRequired) {
        showToast('Two-Factor Authentication required', 'info');
      }
    } catch (err: unknown) {
      const msg = (err as Error)?.message || 'Authentication failed. Please verify credentials.';
      setError(msg);
      showToast(msg, 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleQuickFill = (demoEmail: string, demoPass: string) => {
    setEmail(demoEmail);
    setPassword(demoPass);
    setError(null);
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        width: '100vw',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#0f172a',
        backgroundImage: `radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.15) 0px, transparent 50%),
                          radial-gradient(at 100% 100%, rgba(168, 85, 247, 0.15) 0px, transparent 50%)`,
        padding: '24px',
      }}
      data-testid="login-page"
    >
      <div
        className="card"
        style={{
          width: '100%',
          maxWidth: '440px',
          padding: '36px',
          backgroundColor: '#ffffff',
          borderRadius: '16px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.35)',
        }}
      >
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: '28px' }}>
          <div
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: 'linear-gradient(135deg, #4f46e5, #7c3aed)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#ffffff',
              boxShadow: '0 8px 16px rgba(79, 70, 229, 0.3)',
              marginBottom: '16px',
            }}
          >
            <Shield size={26} />
          </div>
          <h1 style={{ fontSize: '24px', fontWeight: 800, color: 'var(--text-primary)', margin: 0, letterSpacing: '-0.02em' }}>
            NVRSMS Hub
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '6px' }}>
            Enterprise Video Surveillance & Edge Management
          </p>
        </div>

        {error && (
          <div
            style={{
              backgroundColor: 'var(--status-offline-bg)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              borderRadius: 'var(--radius-md)',
              padding: '12px',
              color: 'var(--status-offline)',
              fontSize: '13px',
              marginBottom: '20px',
              textAlign: 'left',
            }}
            role="alert"
            data-testid="login-error-alert"
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {!totpRequired ? (
            <>
              <div className="form-group">
                <label className="form-label" htmlFor="login-email">
                  Email Address
                </label>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <Mail
                    size={16}
                    color="var(--text-muted)"
                    style={{ position: 'absolute', left: '12px', pointerEvents: 'none' }}
                  />
                  <input
                    id="login-email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="admin@nvrsms.local"
                    className="form-input"
                    style={{ paddingLeft: '36px' }}
                    data-testid="login-email-input"
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="login-password">
                  Password
                </label>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <Lock
                    size={16}
                    color="var(--text-muted)"
                    style={{ position: 'absolute', left: '12px', pointerEvents: 'none' }}
                  />
                  <input
                    id="login-password"
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="form-input"
                    style={{ paddingLeft: '36px' }}
                    data-testid="login-password-input"
                  />
                </div>
              </div>
            </>
          ) : (
            <div className="form-group">
              <label className="form-label" htmlFor="login-totp">
                Two-Factor Security Code (TOTP)
              </label>
              <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                <KeyRound
                  size={16}
                  color="var(--color-primary)"
                  style={{ position: 'absolute', left: '12px', pointerEvents: 'none' }}
                />
                <input
                  id="login-totp"
                  type="text"
                  maxLength={6}
                  autoFocus
                  required
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ''))}
                  placeholder="000000"
                  className="form-input"
                  style={{
                    paddingLeft: '36px',
                    fontSize: '18px',
                    letterSpacing: '0.25em',
                    fontFamily: 'var(--font-mono)',
                    textAlign: 'center',
                  }}
                  data-testid="login-totp-input"
                />
              </div>
              <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                Enter the 6-digit code from your authenticator app for {pendingEmail}
              </p>
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="btn btn-primary"
            style={{ width: '100%', height: '42px', marginTop: '12px' }}
            data-testid="login-submit-button"
          >
            {submitting ? (
              <span>Authenticating...</span>
            ) : totpRequired ? (
              <>
                <span>Verify TOTP</span>
                <ArrowRight size={16} />
              </>
            ) : (
              <>
                <span>Sign In to Platform</span>
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>

        {/* Quick-fill demo section */}
        {!totpRequired && (
          <div
            style={{
              marginTop: '28px',
              paddingTop: '20px',
              borderTop: '1px solid var(--border-subtle)',
              textAlign: 'center',
            }}
          >
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Quick-Fill Test Profiles
            </span>
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', marginTop: '10px' }}>
              <button
                type="button"
                onClick={() => handleQuickFill('admin@nvrsms.local', 'SuperAdminSecret123!')}
                className="btn btn-secondary"
                style={{ fontSize: '11px', padding: '5px 10px' }}
                data-testid="quick-fill-admin"
              >
                Super Admin
              </button>
              <button
                type="button"
                onClick={() => handleQuickFill('operator@nvrsms.local', 'OperatorSecret123!')}
                className="btn btn-secondary"
                style={{ fontSize: '11px', padding: '5px 10px' }}
                data-testid="quick-fill-operator"
              >
                Operator
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
