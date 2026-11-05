import { describe, expect, it } from 'vitest';
import { formatINR, parseRupeesToPaise, paiseToInput } from './money';

describe('INR conversion', () => {
  it('converts whole rupees and paise exactly', () => {
    expect(parseRupeesToPaise('125')).toBe(12500);
    expect(parseRupeesToPaise('125.5')).toBe(12550);
    expect(parseRupeesToPaise('0.01')).toBe(1);
    expect(paiseToInput(12505)).toBe('125.05');
    expect(formatINR(125050)).toContain('₹');
    expect(formatINR(125050)).toContain('1,250.50');
  });

  it('rejects invalid precision, zero, signs, and unsafe values', () => {
    expect(parseRupeesToPaise('4.999')).toBeNull();
    expect(parseRupeesToPaise('0')).toBeNull();
    expect(parseRupeesToPaise('-2')).toBeNull();
    expect(parseRupeesToPaise('90071992547409.92')).toBeNull();
    expect(parseRupeesToPaise('1e3')).toBeNull();
  });
});
