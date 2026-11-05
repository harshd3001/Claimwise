const MAX_SAFE_INTEGER = Number.MAX_SAFE_INTEGER;

export function parseRupeesToPaise(value: string): number | null {
  const normalized = value.trim();
  const match = /^(?:\d+)(?:\.(\d{1,2}))?$/.exec(normalized);
  if (!match) return null;
  const [whole] = normalized.split('.');
  const paise = (match[1] ?? '').padEnd(2, '0');
  const result = Number(whole) * 100 + Number(paise || '0');
  if (!Number.isSafeInteger(result) || result <= 0 || result > MAX_SAFE_INTEGER) return null;
  return result;
}

export function formatINR(paise: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(paise / 100);
}

export function paiseToInput(paise: number): string {
  return `${Math.floor(paise / 100)}.${String(paise % 100).padStart(2, '0')}`;
}
