import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from 'react';
import type { ReactNode } from 'react';
import { api, setAccessToken, getAccessToken } from '../api/client';
import type { User, Tenant, TokenResponse, MeResponse, LoginRequest } from '../api/types';

export interface AuthContextType {
  user: User | null;
  tenant: Tenant | null;
  permissions: Set<string>;
  isAuthenticated: boolean;
  isLoading: boolean;
  totpRequired: boolean;
  pendingEmail: string | null;
  login: (credentials: LoginRequest) => Promise<{ success: boolean; totpRequired?: boolean }>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  hasPermission: (permissionCode: string) => boolean;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [permissions, setPermissions] = useState<Set<string>>(new Set());
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [totpRequired, setTotpRequired] = useState<boolean>(false);
  const [pendingEmail, setPendingEmail] = useState<string | null>(null);

  const fetchProfile = useCallback(async (): Promise<boolean> => {
    try {
      const data = await api.get<MeResponse>('/auth/me');
      setUser(data.user);
      setTenant(data.tenant);
      const permList = data.permissions || data.user.permissions || [];
      setPermissions(new Set(permList));
      setIsAuthenticated(true);
      return true;
    } catch {
      setUser(null);
      setTenant(null);
      setPermissions(new Set());
      setIsAuthenticated(false);
      setAccessToken(null);
      return false;
    }
  }, []);

  const refreshProfile = useCallback(async (): Promise<void> => {
    await fetchProfile();
  }, [fetchProfile]);

  useEffect(() => {
    const initAuth = async () => {
      const existingToken = getAccessToken();
      if (existingToken) {
        await fetchProfile();
      }
      setIsLoading(false);
    };

    initAuth();

    // Listen for session expiry from API client
    const handleAuthExpired = () => {
      setUser(null);
      setTenant(null);
      setPermissions(new Set());
      setIsAuthenticated(false);
      setAccessToken(null);
    };

    // Listen for real-time permissions update
    const handlePermissionsUpdated = () => {
      fetchProfile();
    };

    window.addEventListener('auth:expired', handleAuthExpired);
    window.addEventListener('permissions_changed', handlePermissionsUpdated);

    return () => {
      window.removeEventListener('auth:expired', handleAuthExpired);
      window.removeEventListener('permissions_changed', handlePermissionsUpdated);
    };
  }, [fetchProfile]);

  const login = async (credentials: LoginRequest): Promise<{ success: boolean; totpRequired?: boolean }> => {
    try {
      const response = await api.post<TokenResponse>('/auth/login', credentials);

      if (response.totp_required) {
        setTotpRequired(true);
        setPendingEmail(credentials.email);
        return { success: false, totpRequired: true };
      }

      setAccessToken(response.access_token);
      setTotpRequired(false);
      setPendingEmail(null);

      const profileOk = await fetchProfile();
      return { success: profileOk, totpRequired: false };
    } catch (err) {
      setAccessToken(null);
      throw err;
    }
  };

  const logout = async () => {
    try {
      await api.post('/auth/logout', {});
    } catch {
      // Ignore network errors on logout
    } finally {
      setAccessToken(null);
      setUser(null);
      setTenant(null);
      setPermissions(new Set());
      setIsAuthenticated(false);
      setTotpRequired(false);
      setPendingEmail(null);
    }
  };

  const hasPermission = useCallback(
    (code: string): boolean => {
      if (!user) return false;
      if (user.is_superuser) return true;
      return permissions.has(code);
    },
    [user, permissions]
  );

  return (
    <AuthContext.Provider
      value={{
        user,
        tenant,
        permissions,
        isAuthenticated,
        isLoading,
        totpRequired,
        pendingEmail,
        login,
        logout,
        refreshProfile,
        hasPermission,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
