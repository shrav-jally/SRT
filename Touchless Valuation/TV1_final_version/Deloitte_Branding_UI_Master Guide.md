# Deloitte Brand, Asset Naming & UI/UX Master Guide

**Purpose of this document:** a single, reusable reference that combines Deloitte's *Asset Name Clearance* rules, *UI Clearance* rules, and the *Digital Design System (DDS)* tokens/components into one master prompt/spec. Any project team (or an AI code editor / Claude / Copilot) can point to this file to generate on-brand naming and on-brand UI/UX for **any** Deloitte internal or external digital asset.

Reference live example: `https://design.deloitte.com/angular/portfolio/tax-jurisdiction-portal`
Reference DDS live example: `https://design.deloitte.com/example-app`

> ⚠️ Internal use only. Do not circulate outside the Deloitte Network. Always confirm current rules with your local/Global Brand team before final launch — this guide is a working reference, not a substitute for formal Brand/Legal approval.

---

## 0. How to Use This Guide (Prompt Template)

When starting a new Deloitte project (app, portal, dashboard, tool), use this as the system prompt / brief for name generation and UI generation:

```
You are building a Deloitte digital asset. Follow the Deloitte Brand, Asset Naming &
UI/UX Master Guide:
1. Determine if the asset qualifies for a standalone name (Section 1).
2. If yes, generate a name using the Naming Standards + Naming Structure (Section 2)
   — functional/industry category + descriptive tool name, optionally with an
   umbrella brand prefix (Ascend / Converge / Intela / Omnia / Levia).
3. Build all UI using the Digital Design System (DDS) tokens and components
   (Sections 3–6): Open Sans typography, 8px spacing grid, DDS color tokens,
   dds-* component classes, zero border-radius default, BEM naming.
4. Follow logo/favicon placement rules, color usage rules, and the circular motif
   for login/landing screens (Section 4).
5. Do not use forbidden naming patterns (acronyms, "Deloitte" prefix/suffix,
   "D." prefix, "AI"/"GenAI" in the name, year, homophones, abstract names).
6. Route the asset through the approval workflow (Section 7) before external use.
```

---

## 1. STEP 1 — Naming Qualification (Does the Asset Need a Name?)

Before any name generation work, confirm with local and/or Global Brand team whether the asset qualifies for a standalone name. An asset is a candidate if it is (in order of importance):

1. Used **externally**
2. Likely to be perceived by a client as a **differentiator**
3. Likely to be **repeatable** across multiple clients
4. Expected to **elevate/differentiate** the Deloitte brand
5. Receiving **significant marketing support/resources** before and after launch
6. Backed by a **1–3+ year business plan**
7. Offering a name **different** from any existing Deloitte asset (check Master Asset Inventory, Wordmark/Custom Name Registry, US Consulting Master Asset Inventory) or any direct competitor (web search required)
8. Qualified to pair with one of the **five global umbrella brands**
9. Likely to be **purchased as a standalone** product or generate **direct license revenue**
10. Appealing to **audiences not intrinsic** to Deloitte's core offering

If the asset does not meet these criteria, do **not** create a standalone name — use a plain descriptive/functional label instead.

---

## 2. STEP 2 — Naming Standards & Structure

### 2.1 A proposed name MUST meet ALL of the following

1. Have a **clear meaning** an individual would intrinsically understand without context
2. Be **no more than 2–3 words** — concise and short
3. Be **descriptive**
4. Be **easily pronounced** correctly by non-native English speakers
5. **Naturally lend itself to digital usage** (URL, SEO, social)
6. **Not already used** by any other area of Deloitte (check Master Asset Inventory, Wordmark/Custom Name Registry, US Consulting Master Asset Inventory) or a direct competitor (web search required)
7. Follow the **new descriptive naming protocol** (Section 2.3)

### 2.2 A proposed name MUST be FREE of

1. Complex and/or meaningless **acronyms**
2. **3rd-party naming conventions** (e.g., Apple's "iPhone" style)
3. **"Deloitte"** as a prefix or suffix (e.g., "Deloitte X" or "X Deloitte")
4. Initial cap of **"D"** or **"D."** (D-dot) as a prefix or suffix
5. **Abstract** names or references
6. **Distorted or inverted** letters/symbols
7. **Homophones** (e.g., sell/cell)
8. A **year** (e.g., 2020)
9. The phrase **"GenAI"** or **"AI"**

### 2.3 STEP 3 — Descriptive Naming Protocol (Umbrella Brands)

Going forward, all products/platforms fall under **five umbrella brands**. New names must be straightforward and descriptive so they are telegraphic and signal clearly to clients, the market, and internal teams exactly what the asset does.

**Structure:**
1. Select the **functional industry/category** you operate in — e.g., `Health`, `FS` (Financial Services), `Supply Chain`, etc.
2. State clearly **what your tool does** — e.g., `Record Match`, `Banking Suite`, `Optics`, etc.
3. **Merge the two words** — e.g., `Health Record Match`, `FS Banking Suite`, `Supply Chain Optics`

**Naming format (hybrid naming — no spaces, camel-style compound):**

| Functional/Industry Category (bold) | + Tool Name (regular) | = Resulting Name |
|---|---|---|
| Health | RecordMatch | `HealthRecordMatch` |
| FS | BankingSuite | `FSBankingSuite` |
| Audit | DocumentReader | `AuditDocumentReader` |
| Supply Chain | Optics | `SupplyChainOptics` |

**Add an umbrella hybrid brand only where the asset hits business criteria and has approval:**

Umbrella brands: `Ascend` / `Converge` / `Intela` / `Omnia` / `Levia`

Example: `Omnia AuditDocumentReader`

### 2.4 STEP 4 — Naming Business Case Form

Fill out the **Naming Business Case Form** (Excel, `Naming_Business_Case_Form_InternalAsset`, shared over email) with the proposed asset name(s) before submission.

### 2.5 STEP 5 — Submission & Approval Workflow

1. Submit for **local Brand approval** (Excel form with proposed names)
2. **Global Brand team approval** + consultation with each local brand team where the name is intended for use (cultural/language relevancy check)
3. **Local Legal check** — Brand team submits the asset name for legal review
4. **Approval from global business marketing team**
5. Submit the **approved asset name** to the legal team for **registry/trademark**

**Naming contact:** Amit Anand — amanand@deloitte.com

---

## 3. UI Clearance — STEP 1: Follow the Global Digital Design System

All UI/UX must follow the **Global Digital Design System (DDS)** guidelines. The goal of DDS is to build a unified, systematic language aligned to Deloitte's signature brand identity.

- Design system reference: `digital design system` (brandspace)
- UI Kit / Figma / HTML snippets / Accessibility / Global support: `https://brandspace.deloitte.com/content/index/guid/standards_inuse_customdigitalapplications#3-accessibility`
- Live example app: `https://design.deloitte.com/example-app`
- Live portfolio example: `https://design.deloitte.com/angular/portfolio/tax-jurisdiction-portal`

## UI Clearance — STEP 2: When Design System Guidelines Cannot Be Fully Followed

If, due to technical limitations, the full Digital Design System cannot be implemented, the application UI must still maintain these minimum standards:

### 3.1 Logo Usage & Placement

- Application header must show the **Deloitte logo** + **asset name** placement per Digital Design System guidelines
- **Favicon as profile logo**: usage is limited to **small-scale digital applications only**, where a full Deloitte logo would not be appropriate due to sizing limitations
- A full Deloitte logo may still appear elsewhere in the application (e.g., header image of a social page) while the favicon appears as the profile/avatar

### 3.2 Color Palette

Reference: `https://brandspace.deloitte.com/content/index/guid/standards_elements_color`

- Core palette: **White / Black / Primary / Secondary** color wheel
- **Red, Orange, Yellow are reserved for charts, graphs, or functional association only** — do not use them as general UI decoration
- Always check guidelines for **bright colors** before use

### 3.3 Circular Motif (Primary / Start / Login Screen)

- The **circular motif** is the signature visual element for primary/start/login screens
- **Note:** most internal applications do not have a login/start screen — in this scenario it's fine to skip it, or (if possible) follow the same circular-motif style for the start/landing screen instead

### 3.4 Typography

References:
- `https://brandspace.deloitte.com/content/index/guid/standards_elements_typography`
- `https://design.deloitte.com/angular/guidelines/typography`

Core typeface: **Open Sans** — Light, Light Italic, Regular, Regular Italic, Semi Bold, Semi Bold Italic, Bold, Bold Italic. No other typeface should be introduced.

## UI Clearance — STEP 3: Submission for Approval

Submit the application for local Brand approval by providing application access or submitting unique static screens.

**UI contacts:** Akash Negi — anegi@deloitte.com · Amit Anand — amanand@deloitte.com

---

## 4. Digital Design System (DDS) — Design Tokens

### 4.1 Color Tokens

```css
:root {
  /* Brand */
  --deloitte-green: #86BC25;
  --accessible-blue: #007CB0;
  --accessible-green: #26890D;
  --accessible-teal: #0D8390;
  --red: #DA291C;

  /* Neutrals */
  --black: #000000;
  --white: #FFFFFF;
  --cool-gray-2: #D0D0CE;
  --cool-gray-4: #BBBCBC;
  --cool-gray-6: #A7A8AA;
  --cool-gray-7: #97999B;
  --cool-gray-9: #75787B;
  --cool-gray-10: #63666A;
  --cool-gray-11: #53565A;

  /* Focus */
  --focus-color: #005587;
  --focus-width: 2px;
}
```

**Semantic themes** (each has main / hover / active / strong-hover / strong-active / inverse variants):

| Theme | Main Color | Usage |
|---|---|---|
| Green | `#86BC25` | Primary actions, success states |
| Dark | `#000000` | High-contrast, dark backgrounds |
| White | `#FFFFFF` | On dark backgrounds |
| Blue | `#007CB0` | Primary brand, links, info |
| Danger | `#DA291C` | Errors, destructive actions |

Extended palette: Green/Blue/Teal scales (1–7, light→dark); Accent Orange `#ED8B00`, Yellow `#FFCD00`; Bright Green `#0DF200`, Teal `#3EFAC5`, Blue `#33F0FF` — **charts/functional use only, per Section 3.2**.

### 4.2 Spacing (8px base grid)

```css
--space-0: 0;
--space-1: 8px;
--space-2: 12px;
--space-3: 16px;
--space-4: 20px;
--space-5: 24px;
```

### 4.3 Typography Tokens

```css
--font-family: "Open Sans", sans-serif;
--font-mono: monospace;

/* Headings */
--h1: 600 56px/72px var(--font-family);
--h2: 600 40px/52px var(--font-family);
--h3: 600 32px/40px var(--font-family);
--h4: 700 24px/36px var(--font-family);
--h5: 600 16px/24px var(--font-family);

/* Body */
--body: 400 14px/20px var(--font-family);
--body-bold: 700 14px/20px var(--font-family);
--label: 400 12px/16px var(--font-family);
--label-bold: 600 12px/16px var(--font-family);
```

| Heading | Size | Line Height | Weight |
|---|---|---|---|
| H1 | 56px | 72px | Semibold |
| H2 | 40px | 52px | Semibold |
| H3 | 32px | 40px | Semibold |
| H4 | 24px | 36px | Bold |
| H5 | 16px | 24px | Semibold |
| Body | 14px | 20px | Normal |
| Label | 12px | 16px | Normal |

### 4.4 Borders, Radius, Shadows, Transitions

```css
--border-width: 1px;
--border-color: var(--cool-gray-2);
--radius: 4px;          /* default is effectively 0 for most components — sharp corners */
--radius-sm: 2px;
--radius-lg: 6px;
--radius-pill: 50rem;

--shadow: 0 8px 16px rgba(0,0,0,.15);
--shadow-sm: 0 2px 4px rgba(0,0,0,.075);
--shadow-lg: 0 16px 48px rgba(0,0,0,.175);
--shadow-inset: inset 0 1px 2px rgba(0,0,0,.075);

--transition: .15s;
```

### 4.5 Breakpoints & Grid

```scss
$digital-grid-breakpoints: (xs: 0, sm: 576px, md: 768px, lg: 992px, xl: 1200px, xxl: 1400px);
$digital-grid-columns: 12;
$digital-grid-gutter-width: 24px;
$digital-container-max-widths: (sm: 540px, md: 720px, lg: 960px, xl: 1280px);
```

### 4.6 Z-Index Scale

```scss
$digital-modal--zIndex: 1000;
$digital-modal__overlay--zIndex: 999;
$digital-data-table_fixed-header--zIndex: 10;
$digital-data-table_fixed-left-column--zIndex: 11;
```

---

## 5. DDS Component Library — Class Patterns

> Naming convention: **BEM** — `Block__Element_Modifier`, all prefixed `dds-`.

### 5.1 Button

```html
<button class="dds-btn">Base</button>
<button class="dds-btn dds-btn_primary">Primary</button>
<button class="dds-btn dds-btn_secondary">Secondary</button>
<button class="dds-btn dds-btn_secondary-loud">Secondary Loud</button>
<button class="dds-btn dds-btn_silent">Silent</button>

<!-- Themes -->
<button class="dds-btn dds-btn_primary dds-btn_green">Green</button>
<button class="dds-btn dds-btn_primary dds-btn_blue">Blue</button>
<button class="dds-btn dds-btn_primary dds-btn_dark">Dark</button>
<button class="dds-btn dds-btn_primary dds-btn_danger">Danger</button>
<button class="dds-btn dds-btn_primary dds-btn_white">White</button>

<!-- Sizes -->
<button class="dds-btn dds-btn_primary dds-btn_green dds-btn_lg">Large</button>
<button class="dds-btn dds-btn_primary dds-btn_green dds-btn_sm">Small</button>

<!-- States -->
<button class="dds-btn dds-btn_primary dds-btn_green dds-btn_fluid-width">Full Width</button>
<button class="dds-btn dds-btn_primary dds-btn_green" disabled>Disabled</button>
```

| Kind | Background | Border | Text |
|---|---|---|---|
| Primary | Transparent | Theme color | Theme color |
| Secondary | Transparent | Gray-11 | Gray-11 |
| Secondary-Loud | Gray-11 | Gray-11 | White |
| Silent | Transparent | Transparent | Black |

Sizes: LG (16px/24px, 18px 24px padding) · MD (14px/20px, 12px 16px padding) · SM (12px/16px, 8px 12px padding)

### 5.2 Input

```html
<div class="dds-input">
  <div class="dds-input__header"><label class="dds-input__label">Label</label></div>
  <div class="dds-input__wrap"><input class="dds-input__field" type="text" placeholder="Placeholder"></div>
  <div class="dds-input__footer"><span class="dds-input__description">Helper text</span></div>
</div>

<!-- External (compact) -->
<div class="dds-input dds-input_external">
  <input class="dds-input__field" type="text" placeholder="Search...">
  <span class="dds-input__icon dds-icon">🔍</span>
</div>

<!-- Error -->
<div class="dds-input dds-input_error">
  <input class="dds-input__field" type="text" value="Error">
  <div class="dds-input__error-message">Error message</div>
</div>
```

### 5.3 Select

```html
<div class="dds-select">
  <span class="dds-select__title">Label</span>
  <div class="dds-select__field">
    <span class="dds-select__placeholder">Select option</span>
    <span class="dds-select__icon dds-icon">▼</span>
  </div>
  <div class="dds-select__list">
    <div class="dds-context-menu-item">Option 1</div>
  </div>
</div>
<!-- Sizes: dds-select_sm / dds-select_lg. External: dds-select_external -->
```

### 5.4 Checkbox / Radio

```html
<label class="dds-custom-control">
  <input type="checkbox" class="dds-custom-control__field dds-custom-control__field_checkbox">
  <span class="dds-custom-control__icon dds-custom-control__icon_checkbox"></span>
  <span class="dds-custom-control__text">Checkbox label</span>
</label>
<!-- Themes: dds-custom-control_blue / _green / _inverse / _danger -->
```

### 5.5 Modal

```html
<div class="dds-modal dds-modal_open">
  <div class="dds-modal__header">
    <h2 class="dds-modal__title">Title</h2>
    <button class="dds-modal__close dds-icon">×</button>
  </div>
  <div class="dds-modal__body">Content</div>
  <div class="dds-modal__footer">
    <div class="dds-modal__footer-content dds-modal__footer-content_left">
      <button class="dds-btn dds-btn_silent">Cancel</button>
    </div>
    <div class="dds-modal__footer-content dds-modal__footer-content_right">
      <button class="dds-btn dds-btn_primary dds-btn_green">Confirm</button>
    </div>
  </div>
</div>
<div class="dds-modal-overlay"></div>
<!-- Large: dds-modal_lg -->
```

### 5.6 Data Table + Table Block

```html
<div class="dds-table-block">
  <div class="dds-table-block__header">
    <h3 class="dds-table-block__title">Users</h3>
    <div class="dds-table-block__actions">
      <button class="dds-btn dds-btn_primary dds-btn_green">Add User</button>
    </div>
  </div>
  <div class="dds-table-block__content">
    <table class="dds-data-table">
      <thead>
        <tr>
          <th class="dds-data-table__header-cell dds-data-table__header-cell_sorting">Name</th>
          <th class="dds-data-table__header-cell">Status</th>
          <th class="dds-data-table__header-cell">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr class="dds-data-table__row">
          <td class="dds-data-table__cell">John Doe</td>
          <td class="dds-data-table__cell"><span class="dds-status-tag dds-status-tag_green">Active</span></td>
          <td class="dds-data-table__cell">
            <div class="dds-data-table-actions">
              <button class="dds-data-table-actions__item" title="Edit">✏️</button>
              <button class="dds-data-table-actions__item" title="Delete">🗑️</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
<!-- Variants: dds-data-table_striped / _fixed-header / _selection -->
```

### 5.7 Status Tags

```html
<span class="dds-status-tag dds-status-tag_green">Success</span>
<span class="dds-status-tag dds-status-tag_red">Error</span>
<span class="dds-status-tag dds-status-tag_orange">Warning</span>
<span class="dds-status-tag dds-status-tag_blue">Info</span>
<span class="dds-status-tag dds-status-tag_gray">Neutral</span>
```

### 5.8 Header (App Shell)

```html
<header class="dds-header">
  <div class="dds-header__container">
    <div class="dds-header__main">
      <div class="dds-header__logo"><img src="logo.svg" alt="Logo"></div>
      <a class="dds-header__project-name">Project Name</a>
    </div>
    <div class="dds-header__left-wrap">
      <nav class="dds-header__navigation">
        <a class="dds-header__nav-item">Link 1</a>
        <a class="dds-header__nav-item">Link 2</a>
      </nav>
    </div>
    <div class="dds-header__right-wrap">
      <div class="dds-header__icons">
        <button class="dds-btn dds-btn_silent dds-btn_dark dds-header__btn-icon">
          <span class="dds-btn__icon dds-icon">🔔</span>
        </button>
      </div>
      <div class="dds-header__profile"><div class="dds-user-pic">JD</div></div>
    </div>
  </div>
</header>
<!-- Inverse (dark): dds-header_inverse -->
```

### 5.9 Navigation: Tabs, Pagination, Breadcrumbs

```html
<div class="dds-tabs">
  <div class="dds-tabs__nav">
    <button class="dds-tabs__item dds-tabs__item_active">Tab 1</button>
    <button class="dds-tabs__item">Tab 2</button>
  </div>
  <div class="dds-tabs__content">Content</div>
</div>

<nav class="dds-pagination">
  <button class="dds-pagination__item dds-pagination__item_prev">‹</button>
  <button class="dds-pagination__item dds-pagination__item_active">2</button>
  <button class="dds-pagination__item dds-pagination__item_next">›</button>
</nav>

<nav class="dds-breadcrumbs">
  <a class="dds-breadcrumbs__item">Home</a>
  <span class="dds-breadcrumbs__separator">/</span>
  <span class="dds-breadcrumbs__item dds-breadcrumbs__item_current">Details</span>
</nav>
```

### 5.10 Other Components (quick reference)

```html
<!-- Avatar -->
<div class="dds-user-pic"><img class="dds-user-pic__img" src="avatar.jpg" alt="User"></div>

<!-- Progress -->
<div class="dds-progress"><div class="dds-progress__bar" style="width: 60%"></div></div>

<!-- Spinner -->
<div class="dds-spinner"></div>

<!-- Toggle -->
<label class="dds-toggle">
  <input type="checkbox" class="dds-toggle__input">
  <span class="dds-toggle__track"></span>
  <span class="dds-toggle__thumb"></span>
</label>

<!-- Tags -->
<div class="dds-tags">
  <span class="dds-tag">Tag 1</span>
  <span class="dds-tag dds-tag_removable">Tag 2 <button class="dds-tag__remove">×</button></span>
</div>
```

### 5.11 Layout Utilities

```html
<div class="dds-container">Content</div>
<div class="dds-row">
  <div class="dds-col-6">Half</div>
  <div class="dds-col-6">Half</div>
</div>
<div class="dds-col-sm-12 dds-col-md-6 dds-col-lg-4">Responsive</div>

<div class="dds-flex dds-flex_column dds-flex_center dds-flex_between">Flex</div>

<div class="dds-m-3">Margin 16px</div>
<div class="dds-p-3">Padding 16px</div>
<div class="dds-d-none">Hidden</div>
```

---

## 6. Accessibility, States & Theming

### 6.1 Focus & Screen Reader

```css
.dds-keyboard-focused { outline: 2px solid var(--focus-color); outline-offset: 0; }
.dds-input__field:focus { box-shadow: inset 0 0 0 2px var(--focus-color); }
```

```html
<span class="dds-sr-only">Screen reader text</span>

<div class="dds-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
  <h2 id="modal-title" class="dds-modal__title">Title</h2>
</div>

<th class="dds-data-table__header-cell_sorting" aria-sort="ascending" tabindex="0" role="button">Name</th>
<span class="dds-status-tag" role="status" aria-live="polite">Active</span>

<div class="dds-tabs__nav" role="tablist">
  <button class="dds-tabs__item" role="tab" aria-selected="true" aria-controls="panel-1">Tab 1</button>
</div>
```

### 6.2 Interactive States

```css
.dds-btn:hover { }
.dds-btn:active, .dds-btn_selected { }
.dds-keyboard-focused { }
.dds-btn_disabled, .dds-input_disabled, .dds-select_disabled { }
.dds-btn_loading .dds-btn__text { opacity: 0; }
.dds-input_error .dds-input__field { border-color: var(--red); }
```

### 6.3 Dark Mode / Theming

```html
<html class="digital dds-dark">
  <div class="dds dds-dark">
    <button class="dds-btn dds-btn_primary dds-btn_white">Light on dark</button>
    <label class="dds-custom-control dds-custom-control_inverse">...</label>
  </div>
</html>
```

```scss
$digital-theme-brand_main: #YOUR_COLOR;
$digital-theme-colors: map-merge($digital-theme-colors, ("brand": $digital-theme-brand_main));
```

### 6.4 Responsive Device Classes

| Breakpoint | Class | Width |
|---|---|---|
| XS | `.dds-mobile` | < 576px |
| SM | `.dds-tablet` | ≥ 576px |
| MD | `.dds-desktop` | ≥ 768px |

---

## 7. Rules & Conventions Summary (Do / Don't)

### 7.1 Naming — Do

- ✅ Confirm qualification with Brand team before naming (Section 1)
- ✅ Use functional/industry category + descriptive tool name, merged (Section 2.3)
- ✅ Keep names to 2–3 words, plain-meaning, easy to pronounce, URL/SEO friendly
- ✅ Check Master Asset Inventory + competitor names before finalizing
- ✅ Pair with an umbrella brand (`Ascend / Converge / Intela / Omnia / Levia`) only with approval
- ✅ Route through the 5-step naming + approval workflow

### 7.2 Naming — Don't

- ❌ Use "Deloitte" as a prefix/suffix
- ❌ Use "D" / "D." as a prefix/suffix
- ❌ Use acronyms, abstract names, distorted letters, homophones
- ❌ Use a year in the name
- ❌ Use "AI" or "GenAI" in the name
- ❌ Copy a 3rd-party naming convention (e.g., "iPhone"-style)

### 7.3 UI/UX — Do

- ✅ Follow the Digital Design System (DDS) first; fall back to Section 3 minimum standards only if technically blocked
- ✅ Use Open Sans exclusively, DDS type scale, 8px spacing grid
- ✅ Use `dds-*` BEM component classes
- ✅ Place Deloitte logo + asset name in the header per DDS guidelines
- ✅ Use the favicon-as-avatar pattern only for small-scale UI where a full logo doesn't fit
- ✅ Reserve Red/Orange/Yellow for charts/graphs/functional meaning only
- ✅ Use the circular motif on login/start/landing screens (or skip if the app has none)
- ✅ Ensure visible focus states, ARIA roles, and keyboard navigation on every component
- ✅ Submit static screens or app access for local Brand approval before external release

### 7.4 UI/UX — Don't

- ❌ Introduce a second font family
- ❌ Use non-DDS class names (e.g., `.btn-primary` instead of `.dds-btn_primary`)
- ❌ Use arbitrary border-radius values — DDS defaults are sharp/near-zero corners
- ❌ Use off-palette custom colors instead of theme tokens
- ❌ Use px-based ad hoc spacing instead of the 8px scale
- ❌ Use Red/Orange/Yellow decoratively outside charts/functional states
- ❌ Skip the approval workflow for anything client-facing

### 7.5 Bootstrap/Material → DDS Quick Mapping

| Concept | Bootstrap | Material | DDS |
|---|---|---|---|
| Primary Button | `.btn-primary` | `<Button color="primary">` | `.dds-btn_primary .dds-btn_green` |
| Input | `.form-control` | `<TextField>` | `.dds-input__field` |
| Modal | `.modal` | `<Dialog>` | `.dds-modal` |
| Table | `.table` | `<Table>` | `.dds-data-table` |
| Card | `.card` | `<Card>` | Compose with `.dds-table-block` |
| Grid | `.row/.col` | `<Grid>` | CSS Grid + `.dds-container` |

---

## 8. Quick-Start HTML Template

```html
<!DOCTYPE html>
<html class="digital" lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DDS Project</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
</head>
<body>
  <header class="dds-header">
    <div class="dds-header__container">
      <div class="dds-header__main">
        <div class="dds-header__logo"><img src="logo.svg" alt="Deloitte"></div>
        <span class="dds-header__project-name">My App</span>
      </div>
    </div>
  </header>

  <main class="dds-container" style="padding: 24px;">
    <h1 style="font: 600 32px/40px 'Open Sans', sans-serif;">Page Title</h1>

    <div class="dds-table-block">
      <div class="dds-table-block__header">
        <h2 class="dds-table-block__title" style="font: 600 16px/24px 'Open Sans', sans-serif;">Data Table</h2>
        <div class="dds-table-block__actions">
          <button class="dds-btn dds-btn_primary dds-btn_green">Add New</button>
        </div>
      </div>
      <div class="dds-table-block__content">
        <table class="dds-data-table">
          <thead>
            <tr>
              <th class="dds-data-table__header-cell">Name</th>
              <th class="dds-data-table__header-cell">Status</th>
              <th class="dds-data-table__header-cell">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr class="dds-data-table__row">
              <td class="dds-data-table__cell">John Doe</td>
              <td class="dds-data-table__cell"><span class="dds-status-tag dds-status-tag_green">Active</span></td>
              <td class="dds-data-table__cell">
                <div class="dds-data-table-actions">
                  <button class="dds-data-table-actions__item">✏️</button>
                  <button class="dds-data-table-actions__item">🗑️</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div style="margin-top: 24px; display: flex; gap: 12px;">
      <button class="dds-btn dds-btn_primary dds-btn_green">Primary Action</button>
      <button class="dds-btn dds-btn_secondary">Secondary</button>
      <button class="dds-btn dds-btn_silent">Silent</button>
    </div>
  </main>
</body>
</html>
```

---

## 9. Reference Links

| Topic | Link |
|---|---|
| Digital Design System (guidelines) | `digital design system` (brandspace) |
| UI Kit / Figma / HTML snippets / Accessibility | `https://brandspace.deloitte.com/content/index/guid/standards_inuse_customdigitalapplications#3-accessibility` |
| Color Palette | `https://brandspace.deloitte.com/content/index/guid/standards_elements_color` |
| Typography | `https://brandspace.deloitte.com/content/index/guid/standards_elements_typography` and `https://design.deloitte.com/angular/guidelines/typography` |
| DDS Live Example App | `https://design.deloitte.com/example-app` |
| Portfolio Live Example (Tax Jurisdiction Portal) | `https://design.deloitte.com/angular/portfolio/tax-jurisdiction-portal` |
| Umbrella Brands | linked from Brand Check deck, Step 3 |
| Naming contact | Amit Anand — amanand@deloitte.com |
| UI contacts | Akash Negi — anegi@deloitte.com · Amit Anand — amanand@deloitte.com |

---

## 10. Component Migration Checklist (for existing / legacy apps)

- [ ] Buttons → `.dds-btn` with kind/theme modifiers
- [ ] Inputs → `.dds-input` (external variant for dense UIs)
- [ ] Selects → `.dds-select`
- [ ] Checkboxes/Radios → `.dds-custom-control`
- [ ] Modals → `.dds-modal`
- [ ] Tables → `.dds-data-table` + `.dds-table-block`
- [ ] Headers → `.dds-header`
- [ ] Navigation → Tabs, Breadcrumbs, Pagination
- [ ] Feedback → Toaster, Tooltip, Progress, Spinner
- [ ] Data display → Status tags, Avatar, Tree, List
- [ ] Logo/favicon placement rechecked against Section 3.1
- [ ] Color usage rechecked against Section 3.2 (Red/Orange/Yellow reserved for charts only)
- [ ] Login/start screen circular motif applied or intentionally skipped
- [ ] Name (if any) rechecked against Section 2 rules
- [ ] Static screens or access submitted for local Brand approval

---

*Sources consolidated: "Brand Check — External Assets" deck (Asset Name clearance + UI clearance), Digital Design System (DDS) Quick Reference, and Digital Design System — Complete Style Guide. Deloitte refers to one or more of Deloitte Touche Tohmatsu Limited ("DTTL"), its network of member firms, and their related entities. For internal Deloitte Network use only — do not circulate externally.*
