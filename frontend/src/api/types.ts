/**
 * NVRSMS TypeScript API Type Definitions
 * Aligned with Hub Backend schemas
 */

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  created_at?: string;
}

export interface UserScope {
  id: string;
  user_id: string;
  scope_type: 'site' | 'area' | 'city' | 'province' | 'global';
  scope_id?: string;
  province_id?: string;
  city_id?: string;
  area_id?: string;
  site_id?: string;
  name?: string;
}

export interface User {
  id: string;
  email: string;
  name?: string;
  is_active: boolean;
  is_superuser: boolean;
  totp_enabled: boolean;
  tenant_id: string;
  role_id?: string;
  role_name?: string;
  roles?: string[];
  scopes?: UserScope[];
  permissions?: string[];
}

export interface Permission {
  id: string;
  code: string;
  name: string;
  description?: string;
  category?: string;
}

export interface Role {
  id: string;
  tenant_id: string;
  name: string;
  description?: string;
  is_system: boolean;
  permissions: Permission[];
}

export interface Province {
  id: string;
  tenant_id: string;
  name: string;
  code: string;
  cities?: City[];
}

export interface City {
  id: string;
  province_id: string;
  name: string;
  code: string;
  areas?: Area[];
}

export interface Area {
  id: string;
  city_id: string;
  name: string;
  code: string;
  sites?: Site[];
}

export interface Site {
  id: string;
  area_id: string;
  name: string;
  address?: string;
  code?: string;
}

export interface NVR {
  id: string;
  tenant_id: string;
  site_id: string;
  agent_id: string;
  name: string;
  ip_address: string;
  vendor: string;
  web_port: number;
  rtsp_port: number;
  onvif_port: number;
  status: 'online' | 'offline' | 'degraded';
  channel_count?: number;
  created_at?: string;
}

export interface Camera {
  id: string;
  nvr_id: string;
  tenant_id: string;
  site_id: string;
  channel_number: number;
  name: string;
  main_stream_url?: string;
  sub_stream_url?: string;
  is_ptz: boolean;
  status: 'online' | 'offline';
}

export interface StreamSession {
  stream_id: string;
  camera_id: string;
  stream_type: 'main' | 'sub';
  webrtc_url: string;
  stream_token: string;
  expires_in: number;
}

export interface Agent {
  id: string;
  tenant_id: string;
  site_id?: string;
  site_name?: string;
  name: string;
  status: 'connected' | 'disconnected' | 'degraded';
  version: string;
  last_heartbeat?: string;
  ip_address?: string;
}

export interface AuditLog {
  id: string;
  tenant_id: string;
  user_id?: string;
  user_email?: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  ip_address?: string;
  timestamp: string;
  details?: Record<string, unknown>;
}

export interface LoginRequest {
  email: string;
  password: string;
  totp_code?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  totp_required?: boolean;
}

export interface MeResponse {
  user: User;
  tenant: Tenant;
  permissions: string[];
}

export interface ApiErrorResponse {
  detail: string | { message?: string }[];
}
