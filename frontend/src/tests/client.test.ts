import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api, setAccessToken, getAccessToken, ApiError, apiClient } from '../api/client';

describe('Resilient API Client', () => {
  beforeEach(() => {
    localStorage.clear();
    setAccessToken(null);
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('manages access token lifecycle in memory and storage', () => {
    expect(getAccessToken()).toBeNull();
    setAccessToken('test_jwt_token_123');
    expect(getAccessToken()).toBe('test_jwt_token_123');
    expect(localStorage.getItem('nvrsms_access_token')).toBe('test_jwt_token_123');

    setAccessToken(null);
    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem('nvrsms_access_token')).toBeNull();
  });

  it('injects Authorization Bearer header when token is present', async () => {
    setAccessToken('bearer_token_xyz');

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok' }),
    });
    globalThis.fetch = fetchMock;

    await api.get('/health');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledHeaders = fetchMock.mock.calls[0][1].headers;
    expect(calledHeaders['Authorization']).toBe('Bearer bearer_token_xyz');
  });

  it('constructs ApiError with HTTP status and detail message', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ detail: 'Location scope restriction active' }),
    });

    await expect(api.get('/locations')).rejects.toThrow(ApiError);
    try {
      await api.get('/locations');
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(403);
      expect(apiErr.message).toBe('Location scope restriction active');
    }
  });

  it('automatically refreshes token on 401 and replays request', async () => {
    setAccessToken('expired_token');

    let requestCount = 0;
    globalThis.fetch = vi.fn().mockImplementation(async (url: string) => {
      requestCount++;
      if (url.includes('/auth/refresh')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ access_token: 'new_fresh_token_456' }),
        };
      }

      if (url.includes('/protected-data')) {
        if (requestCount === 1) {
          return {
            ok: false,
            status: 401,
            json: async () => ({ detail: 'Token expired' }),
          };
        }
        // Second attempt after refresh
        return {
          ok: true,
          status: 200,
          json: async () => ({ data: 'success_after_refresh' }),
        };
      }

      return { ok: true, status: 200, json: async () => ({}) };
    });

    const result = await apiClient<{ data: string }>('/protected-data');
    expect(result.data).toBe('success_after_refresh');
    expect(getAccessToken()).toBe('new_fresh_token_456');
  });
});
