import 'server-only';
import { createHash, timingSafeEqual } from 'node:crypto';

// Hashing first gives equal lengths, which timingSafeEqual requires, without leaking the length.
export function secretMatches(received: string | null, expected: string | undefined): boolean {
  if (!received || !expected) return false;
  const digest = (value: string) => createHash('sha256').update(value).digest();
  return timingSafeEqual(digest(received), digest(expected));
}
