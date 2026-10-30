import { createTheme } from '@mui/material/styles';

const FONT_FAMILY = '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", sans-serif';
export const MONO_FONT = '"JetBrains Mono", "SFMono-Regular", Menlo, Consolas, monospace';

const light = {
  primary: { main: '#2563eb', contrastText: '#ffffff' },
  background: { default: '#f4f4f5', paper: '#ffffff' },
  divider: '#e4e4e7',
  borderStrong: '#d4d4d8',
  text: {
    primary: '#18181b',
    secondary: '#71717a',
    disabled: '#8a8a91',
    strong: '#18181b',
    inverted: '#ffffff',
  },
  interaction: {
    hover: 'rgba(0,0,0,0.04)',
    selected: 'rgba(0,0,0,0.06)',
  },
  status: {
    errorBg: '#fef2f2', errorText: '#dc2626',
    warningBg: '#fffbeb', warningText: '#b45309',
    successBg: '#f0fdf4', successText: '#16a34a',
  },
  elevation: {
    card: '0 1px 2px rgba(0,0,0,0.04)',
    hover: '0 4px 12px rgba(0,0,0,0.08)',
    popover: '0 8px 24px rgba(0,0,0,0.08), 0 2px 6px rgba(0,0,0,0.04)',
  },
};

export const theme = createTheme({
  cssVariables: { colorSchemeSelector: 'class' },
  colorSchemes: { light: { palette: light } },
  shape: { borderRadius: 4 },
  typography: {
    fontFamily: FONT_FAMILY,
    fontSize: 15,
    body1: { fontSize: '0.9375rem' },
    body2: { fontSize: '0.875rem' },
    h6: { fontSize: '1rem', fontWeight: 600, letterSpacing: '-0.01em' },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  components: {
    MuiCssBaseline: { styleOverrides: { body: { fontSize: '0.9375rem', lineHeight: 1.5 } } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiCard: {
      styleOverrides: {
        root: ({ theme: t }) => ({
          borderRadius: 8, boxShadow: t.vars.palette.elevation.card,
          border: `1px solid ${t.vars.palette.divider}`,
        }),
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 6, fontWeight: 600, minWidth: 0 },
        sizeSmall: { height: 34, paddingLeft: 12, paddingRight: 12, fontSize: '0.875rem' },
        sizeMedium: { height: 38, paddingLeft: 14, paddingRight: 14, fontSize: '0.9375rem' },
      },
    },
    MuiIconButton: { styleOverrides: { root: { borderRadius: 6 } } },
    MuiChip: { styleOverrides: { root: { borderRadius: 6, fontWeight: 500, height: 24 } } },
    MuiOutlinedInput: {
      styleOverrides: {
        root: ({ theme: t }) => ({
          borderRadius: 6, fontSize: '0.875rem',
          backgroundColor: t.vars.palette.background.paper,
          '& .MuiOutlinedInput-notchedOutline': { borderColor: t.vars.palette.divider },
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: t.vars.palette.borderStrong },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderWidth: 1, borderColor: t.vars.palette.primary.main },
        }),
        input: { paddingTop: 8, paddingBottom: 8 },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: ({ theme: t }) => ({ fontSize: '0.875rem', borderColor: t.vars.palette.divider, padding: '8px 12px' }),
        head: ({ theme: t }) => ({ fontSize: '0.75rem', fontWeight: 600, color: t.vars.palette.text.secondary, letterSpacing: '0.02em' }),
      },
    },
    MuiAlert: { styleOverrides: { root: { borderRadius: 8, fontSize: '0.875rem' } } },
    MuiTooltip: { defaultProps: { placement: 'top', arrow: true } },
    MuiTab: { styleOverrides: { root: { textTransform: 'none', fontWeight: 500, minHeight: 40 } } },
    MuiTabs: { styleOverrides: { root: { minHeight: 40 } } },
  },
});

export const BORDER = `1px solid ${theme.vars.palette.divider}`;
export const HOVER_BG = theme.vars.palette.interaction.hover;
export const SELECTED_BG = theme.vars.palette.interaction.selected;
export const STRONG_TEXT = theme.vars.palette.text.strong;
export const MUTED_TEXT = theme.vars.palette.text.secondary;
export const CARD_SHADOW = theme.vars.palette.elevation.card;
export const HOVER_SHADOW = theme.vars.palette.elevation.hover;
