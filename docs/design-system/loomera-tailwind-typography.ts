import type { Config } from 'tailwindcss';

export const loomeraTypographyTheme: Partial<Config['theme']> = {
  extend: {
    fontFamily: {
      sans: ['Yekan Bakh', 'Vazirmatn', 'Inter', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
      display: ['Source Serif 4', 'Georgia', 'Times New Roman', 'serif'],
      brand: ['Source Serif 4', 'Georgia', 'Times New Roman', 'serif'],
    },
    fontSize: {
      'display-xl': ['4rem', { lineHeight: '4.5rem', letterSpacing: '-0.03em', fontWeight: '600' }],
      'display-l': ['3.25rem', { lineHeight: '3.75rem', letterSpacing: '-0.02em', fontWeight: '600' }],
      'h1': ['2.5rem', { lineHeight: '3.25rem', letterSpacing: '-0.02em', fontWeight: '600' }],
      'h2': ['2rem', { lineHeight: '2.75rem', letterSpacing: '-0.015em', fontWeight: '600' }],
      'h3': ['1.75rem', { lineHeight: '2.5rem', letterSpacing: '-0.01em', fontWeight: '600' }],
      'h4': ['1.5rem', { lineHeight: '2.125rem', letterSpacing: '0', fontWeight: '600' }],
      'h5': ['1.25rem', { lineHeight: '1.875rem', letterSpacing: '0', fontWeight: '600' }],
      'body-lg': ['1.125rem', { lineHeight: '2rem', letterSpacing: '0', fontWeight: '400' }],
      'body': ['1rem', { lineHeight: '1.75rem', letterSpacing: '0', fontWeight: '400' }],
      'body-sm': ['0.875rem', { lineHeight: '1.5rem', letterSpacing: '0', fontWeight: '400' }],
      'label': ['0.8125rem', { lineHeight: '1.25rem', letterSpacing: '0', fontWeight: '500' }],
      'caption': ['0.75rem', { lineHeight: '1.125rem', letterSpacing: '0.01em', fontWeight: '400' }],
      'overline': ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.08em', fontWeight: '600' }],
      'button': ['0.9375rem', { lineHeight: '1.375rem', letterSpacing: '0', fontWeight: '600' }],
      'input': ['0.9375rem', { lineHeight: '1.5rem', letterSpacing: '0', fontWeight: '400' }],
      'table-header': ['0.8125rem', { lineHeight: '1.25rem', letterSpacing: '0.02em', fontWeight: '600' }],
      'table-cell': ['0.875rem', { lineHeight: '1.375rem', letterSpacing: '0', fontWeight: '400' }],
      'metric': ['2rem', { lineHeight: '2.5rem', letterSpacing: '0', fontWeight: '600' }],
    },
  },
};

export const loomeraTypographyUtilities = {
  '.lm-ltr': { direction: 'ltr', unicodeBidi: 'isolate' },
  '.lm-rtl': { direction: 'rtl', unicodeBidi: 'isolate' },
  '.lm-tabular': {
    fontVariantNumeric: 'tabular-nums',
    fontFeatureSettings: '"tnum" 1, "lnum" 1',
  },
} as const;
