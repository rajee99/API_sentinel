---
name: API Sentinel
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#434655'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#505f76'
  on-secondary: '#ffffff'
  secondary-container: '#d0e1fb'
  on-secondary-container: '#54647a'
  tertiary: '#943700'
  on-tertiary: '#ffffff'
  tertiary-container: '#bc4800'
  on-tertiary-container: '#ffede6'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#d3e4fe'
  secondary-fixed-dim: '#b7c8e1'
  on-secondary-fixed: '#0b1c30'
  on-secondary-fixed-variant: '#38485d'
  tertiary-fixed: '#ffdbcd'
  tertiary-fixed-dim: '#ffb596'
  on-tertiary-fixed: '#360f00'
  on-tertiary-fixed-variant: '#7d2d00'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
typography:
  headline-lg:
    fontFamily: Geist
    fontSize: 30px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Geist
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  code-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '450'
    lineHeight: 20px
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 16px
  margin-mobile: 16px
  margin-desktop: 32px
---

## Brand & Style
The design system is engineered for high-density technical environments, specifically targeting developers and DevOps engineers. The brand personality is clinical, precise, and authoritative, prioritizing information density and clarity over decorative elements.

The aesthetic follows a **Professional Minimalism** style. It utilizes a restrained color palette, rigorous grid alignment, and subtle depth to organize complex data streams. The goal is to evoke a sense of reliability and technical excellence, ensuring that critical API metrics remain the focal point of the interface.

## Colors
The color system is optimized for a high-contrast light mode environment. The foundation is built on a **Pure White (#FFFFFF)** workspace to maximize legibility.

- **Primary (Interactive):** A vibrant Blue (#2563EB) used exclusively for primary actions and active states.
- **Surface & Containers:** An extremely light gray (#F8FAFC) is used for secondary surfaces like sidebars and card backgrounds to create subtle grouping without heavy shadows.
- **Semantic Colors:** Success, Warning, and Error tones are calibrated for accessibility (WCAG AA) against white backgrounds, utilizing slightly deeper saturations than a typical dark-mode equivalent to maintain presence.
- **Typography:** Headlines utilize a deep charcoal (#0F172A) for maximum optical weight, while body text uses a softened dark gray (#334155) to reduce eye strain during long reading sessions.

## Typography
The typography strategy employs a multi-font approach to differentiate between hierarchy and data types.

- **Headlines (Geist):** Used for structural navigation and page titles. Its technical, slightly condensed nature permits high information density.
- **Body (Inter):** The primary workhorse for descriptions, labels, and UI controls, chosen for its exceptional legibility in light mode.
- **Data & Code (JetBrains Mono):** Reserved for API endpoints, JSON payloads, and status codes. This mono-spacing ensures that characters align vertically for quick scanning of technical logs.

## Layout & Spacing
The design system utilizes a **4px base grid** to ensure precise alignment of technical data. 

- **Layout Model:** A fluid 12-column grid is used for dashboard layouts, transitioning to a single-column stack on mobile devices.
- **Gutter Strategy:** A consistent 16px (md) gutter is maintained between cards and widgets to allow the white space to act as a separator, reducing the need for heavy borders.
- **Density:** Components should lean toward "Compact" density. Vertical padding in lists and tables should be kept to 8px or 12px to allow as much data as possible to be visible above the fold.

## Elevation & Depth
In this light-themed system, depth is achieved through **low-contrast outlines** rather than heavy shadows.

- **Level 0 (Background):** Pure #FFFFFF.
- **Level 1 (Cards/Sections):** A subtle 1px border (#E2E8F0) with a secondary background fill of #F8FAFC. 
- **Interactive Elevation:** Only active or hovered elements (like dropdowns or modals) should use a shadow. Use a very soft, highly diffused shadow: `0px 4px 12px rgba(15, 23, 42, 0.08)`.
- **Tonal Layering:** Use tinted backgrounds for semantic feedback (e.g., a very light red fill for error banners) to ensure the message is clear without relying solely on text color.

## Shapes
The design system adheres to a **ROUND_EIGHT** philosophy. This 8px (0.5rem) base radius provides a modern, professional softened edge that bridges the gap between clinical "Sharp" layouts and overly casual "Pill" designs.

- **Standard Elements:** Buttons, Input Fields, and Checkboxes utilize the 8px radius.
- **Large Containers:** Cards and Modals use the `rounded-lg` (16px) radius to create a distinct container hierarchy.
- **Small Elements:** Tooltips and tags may use the `rounded-sm` (4px) radius to maintain a sharp, technical feel.

## Components
- **Buttons:** Primary buttons use a solid #2563EB fill with white text. Secondary buttons use a white background with a #E2E8F0 border and #334155 text. Focus states should always show a 2px blue ring.
- **Inputs:** Use a white background with a 1px #E2E8F0 border. On focus, the border changes to #2563EB. Placeholder text should be #94A3B8.
- **Chips/Tags:** Used for API status codes. Success (200) should be a light green wash with dark green text; Errors (500) a light red wash with dark red text. Use JetBrains Mono for the text inside chips.
- **Data Tables:** These are the core of the system. Rows should have a subtle hover state (#F1F5F9). Headers must be in `label-caps` style with a bottom border but no side borders.
- **Monospace Blocks:** For code snippets or API responses, use a #0F172A background with light gray text to provide a "Dark Mode" break that highlights technical content within the light UI.