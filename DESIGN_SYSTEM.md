# CAFlow Visual Design System & UI Architecture (LOCKED)

> **MANDATORY POLICY NOTICE**  
> The CAFlow visual design system is officially **LOCKED**.  
> From this point forward, every screen, view, and module (Clients, Tasks, Documents, Compliance, Calendar, Messages, Reports, Billing, Team, Settings, Audit Logs) **MUST** strictly adhere to this visual language.  
> **NEVER** redesign screens for individual modules.  
> **NEVER** introduce one-off styles, arbitrary colors, random margins, or ad-hoc components.  
> The entire product must feel like **ONE** cohesive, premium fintech SaaS platform engineered for Chartered Accountants in Nepal.

---

## 1. Visual Direction & Principles

- **Fintech & Accounting Precision**: Clean, dense, authoritative, and data-dense without visual clutter.
- **Nepal-First CA Practice Context**: Native support for IRD PAN numbers, Bikram Sambat fiscal years (e.g., FY 2081/82), ICAN audit standards, and NPR financial denominations.
- **Consistent Hierarchy**: Standard typography, explicit elevation tokens, unified card padding, and uniform border radiuses.
- **Intentional Responsiveness**: Desktop, laptop, tablet, and mobile layouts are purposefully engineered. Tables scroll horizontally with indicators; drawers slide out cleanly; modals anchor appropriately.

---

## 2. Color System (CSS Variables)

All color references in templates and stylesheets **must** use the CSS custom properties defined in `static/css/variables.css`.

| Token | Variable Name | Hex Code | Purpose & Usage |
|---|---|---|---|
| **Primary Navy** | `--cf-primary-navy` | `#0B1F33` | Brand anchor, sidebar background, primary buttons, major headings, table headers |
| **Secondary Navy** | `--cf-secondary-navy` | `#173B57` | Hover states, active tabs, secondary links, active firm indicators |
| **Canvas Background** | `--cf-bg` | `#F8F7F3` | Warm, subtle canvas background (reduces eye strain during long accounting hours) |
| **Surface White** | `--cf-surface` | `#FFFFFF` | Cards, modals, topbar, table bodies, input surfaces |
| **Primary Text** | `--cf-text-primary` | `#18232C` | High-contrast body text, form values, table data, modal copy |
| **Muted Text** | `--cf-text-muted` | `#687680` | Subtitles, labels, secondary metadata, table headers, breadcrumb links |
| **Border / Divider** | `--cf-border` | `#DDE3E7` | Card borders, input outlines, table cell borders, dividers |
| **Success** | `--cf-success` | `#3F7D5A` | IRD filed returns, active licenses, positive audit validations, completed tasks |
| **Warning** | `--cf-warning` | `#B58A3A` | Deadlines approaching (48h/7d), review pending, draft working papers |
| **Danger** | `--cf-danger` | `#B94A48` | Overdue filings, tax penalties, audit modifications, delete actions |

### Semantic Accent Colors
- `--cf-info`: `#2B6CB0` (General information, ICAN circulars, system notices)
- `--cf-nepal-red`: `#DC2626` (Nepali flag & statutory urgency accents)
- `--cf-gold-accent`: `#D4AF37` (Fiscal year highlight badges, premium practice badges)

---

## 3. Typography Scale & Stacks

### Font Families
- **Interface & Headings**: `'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif`
- **Numbers, Financials, Codes, PAN**: `'JetBrains Mono', SFMono-Regular, Consolas, monospace` (via `.mono-font`)

### Type Scale
- `h1`: `1.875rem` (30px), Weight 700, Line-height 1.25
- `h2`: `1.5rem` (24px), Weight 700, Line-height 1.3
- `h3`: `1.25rem` (20px), Weight 700, Line-height 1.35
- `h4`: `1.0625rem` (17px), Weight 600, Line-height 1.4
- `h5`: `0.9375rem` (15px), Weight 600
- `h6`: `0.8125rem` (13px), Weight 600, uppercase, letter-spacing `0.05em`
- `body`: `0.9375rem` (15px), Line-height 1.55
- `small` / metadata: `0.8125rem` (13px) or `0.75rem` (12px)

---

## 4. Global Application Shell

The standard authenticated shell is provided by `templates/layouts/app.html`.

### Sidebar Navigation Architecture
```text
WORKSPACE
├── Dashboard       (/)
├── Clients         (/clients/)
├── Tasks           (/tasks/)
├── Documents       (/documents/)
├── Compliance      (/compliance/)
├── Calendar        (/calendar/)
└── Messages        (/messages/)

INSIGHTS
├── Reports         (/reports/)
└── Billing         (/billing/)

ADMIN
├── Team            (/firms/team/)
├── Settings        (/firm/settings/)
└── Audit Logs      (/audit/)

BOTTOM
└── Profile Card & Sign Out
```

### Top Navigation Architecture
- **Global Search**: Search bar with `⌘K` keyboard shortcut autofocus.
- **Fiscal Year Badge**: Displays active Bikram Sambat fiscal year (e.g. `FY 2081/82 • Ashoj 2081`).
- **Help Modal Trigger**: Quick ICAN guidelines & keyboard shortcuts modal.
- **Notifications Dropdown**: Alerts & IRD deadline badges with unread indicator dot.
- **User Profile Dropdown**: User display name, role, firm preferences, and sign out.

---

## 5. Global Reusable Components Registry

Every module view must reuse these components from `templates/components/`:

| Component | Template Path | Usage |
|---|---|---|
| **Buttons** | `templates/components/button.html` | Primary, secondary, outline, ghost, success, danger buttons with sizes and loading states. |
| **Cards** | `templates/components/card.html` | Base cards, metric stat cards (`.cf-stat-card`), accent stripe cards, interactive cards. |
| **Tables** | `templates/components/table.html` | Responsive table wrapper with search filter, sortable headers, compact density, row selection. |
| **Form Fields** | `templates/components/form_field.html` | Standard form fields supporting Django Form instances or manual HTML inputs. |
| **Inputs** | `templates/components/input.html` | Text, number, date, search, and currency inputs with interaction states. |
| **Selects** | `templates/components/select.html` | Standard styled dropdown select with hover and focus states. |
| **Badges** | `templates/components/badge.html` | Pill badges (`primary`, `secondary`, `success`, `warning`, `danger`, `muted`) with optional dot. |
| **Status Dots** | `templates/components/status_dot.html` | Compact status indicator dots with accompanying label. |
| **Tabs** | `templates/components/tabs.html` | Underline tabs and segmented pill tabs (`.cf-nav-pills`) with count badges. |
| **Dropdowns** | `templates/components/dropdown.html` | Reusable dropdown action menus. |
| **Modals** | `templates/components/modal.html` | Pop-up dialogs with backdrop blur, autofocus, and ESC dismissal. |
| **Drawers** | `templates/components/drawer.html` | Slide-over inspection panels (`sm`, `md`, `lg`) from right/left. |
| **Toasts** | `templates/components/toast.html` / `CAFlow.toast()` | Dynamic stacked notifications with auto-dismiss. |
| **Alerts** | `templates/components/alert.html` | Inline dismissible banners for success, warning, danger, and info. |
| **Pagination** | `templates/components/pagination.html` | Standard paginator buttons with active and disabled states. |
| **Breadcrumbs** | `templates/components/breadcrumbs.html` | Contextual navigation trail. |
| **Empty States** | `templates/components/empty_state.html` | Clean placeholder when lists or tables have zero records. |
| **Loading States**| `templates/components/loading_state.html` | Shimmer skeleton cards, skeleton table rows, and container spinners. |
| **Error States** | `templates/components/error_state.html` | Error fallback with error codes, descriptions, and retry actions. |
| **Confirm Dialogs**| `templates/components/confirm_dialog.html` / `CAFlow.confirm()` | Danger/warning confirmation modal for destructive operations. |

---

## 6. Interaction States Standard

Every interactive component **must** support the following interaction states:

1. **Default**: Crisp border (`#DDE3E7`), surface background (`#FFFFFF`), readable typography.
2. **Hover**: Darkened border (`#C6D0D6`), subtle background tint (`#F9FAFB`).
3. **Focus**: High-contrast outline ring:
   ```css
   outline: none;
   border-color: var(--cf-primary-navy);
   box-shadow: 0 0 0 3px rgba(11, 31, 51, 0.12);
   ```
4. **Active**: Pressed down visual feedback (e.g. background `#071523` for primary navy button).
5. **Disabled**: Opacity `0.55-0.65`, `cursor: not-allowed`, pointer events disabled.
6. **Loading**: Embedded animated spinner (`.cf-spinner`), text changed to "Processing...", submit button disabled.
7. **Success / Valid**: Border `#3F7D5A`, focus ring `rgba(63, 125, 90, 0.2)`, success icon & text.
8. **Error / Invalid**: Border `#B94A48`, focus ring `rgba(185, 74, 72, 0.2)`, danger icon & message.

---

## 7. Responsive Design Rules

- **Mobile Viewports (< 576px)**:
  - Sidebar collapses into an off-canvas drawer opened via hamburger toggle `#cf-sidebar-toggle`.
  - Drawers expand to `100vw` for full-screen focus.
  - Modals anchor to the bottom of the viewport for thumb-friendly mobile dialog UX.
  - Table toolbars stack vertically; tables scroll horizontally with smooth touch scrolling.
  - Search input expands to 100% width; `⌘K` keyboard badge hides automatically.
- **Tablet & Laptop Viewports (768px - 1199px)**:
  - Grid adapts from 4 columns to 2 columns for stat cards.
  - Sidebar collapses on viewports below `992px`.
- **Desktop Viewports (≥ 1200px)**:
  - Permanent 260px dark navy sidebar with firm workspace selector.
  - Max container width capped at `1400px` for optimal typography reading lengths.

---

## 8. Development Rules & Governance

1. **Never create one-off CSS**: If a new component is needed, implement it in `templates/components/` and style it in `static/css/caflow.css` using existing tokens first.
2. **Never hardcode hex codes**: Always use `var(--cf-...)` CSS variables.
3. **Single Living Source of Truth**: Visit `/design-system/` locally at any time to inspect live components, interactions, and tokens.
4. **Preserve Integrity**: Any PR or module development that violates the locked design system will be rejected.
