import { NextResponse } from 'next/server';
import { studioSecurityHeaders } from '@/lib/security-headers';

export function middleware() {
  const response = NextResponse.next();
  for (const [name, value] of Object.entries(studioSecurityHeaders)) response.headers.set(name, value);
  return response;
}

export const config = { matcher: ['/', '/studio'] };
