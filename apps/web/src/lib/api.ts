import { ApiError, createClient } from "@gigscout/api-client";

/** Same-origin in dev (Vite proxy) and in production (reverse proxy); override for a remote API. */
export const api = createClient(import.meta.env.VITE_API_URL ?? "");

export function messageOf(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Something went wrong";
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}
