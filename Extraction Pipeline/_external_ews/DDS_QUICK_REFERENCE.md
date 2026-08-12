-# DDS Quick Reference Card for AI Code Editors


## 🎨 Essential Tokens (Copy-Paste Ready)


### Colors (CSS Custom Properties)
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


### Spacing (8px base)
```css
--space-0: 0;
--space-1: 8px;
--space-2: 12px;
--space-3: 16px;
--space-4: 20px;
--space-5: 24px;
```


### Typography
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


### Borders & Radius
```css
--border-width: 1px;
--border-color: var(--cool-gray-2);
--radius: 4px;
--radius-sm: 2px;
--radius-lg: 6px;
--radius-pill: 50rem;
```


### Shadows
```css
--shadow: 0 8px 16px rgba(0,0,0,.15);
--shadow-sm: 0 2px 4px rgba(0,0,0,.075);
--shadow-lg: 0 16px 48px rgba(0,0,0,.175);
--shadow-inset: inset 0 1px 2px rgba(0,0,0,.075);
```


### Transitions
```css
--transition: .15s;
```


---


## 🧱 Component Class Patterns


### Button
```html
<!-- Base -->
<button class="dds-btn">Base</button>


<!-- Kinds -->
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
<button class="dds-btn dds-btn_primary dds-btn_green dds-btn_with-icon">
  <span class="dds-btn__content">
    <span class="dds-btn__text">With Icon</span>
    <span class="dds-btn__icon dds-icon">★</span>
  </span>
</button>
<button class="dds-btn dds-btn_primary dds-btn_green" disabled>Disabled</button>
```


### Input
```html
<!-- Standard -->
<div class="dds-input">
  <div class="dds-input__header">
    <label class="dds-input__label">Label</label>
  </div>
  <div class="dds-input__wrap">
    <input class="dds-input__field" type="text" placeholder="Placeholder">
  </div>
  <div class="dds-input__footer">
    <span class="dds-input__description">Helper text</span>
  </div>
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


<!-- With internal label -->
<div class="dds-input dds-input_with-icon">
  <input class="dds-input__field" type="password" placeholder="Password">
  <span class="dds-input__icon dds-icon">👁</span>
</div>
```


### Select
```html
<div class="dds-select">
  <span class="dds-select__title">Label</span>
  <div class="dds-select__field">
    <span class="dds-select__placeholder">Select option</span>
    <span class="dds-select__icon dds-icon">▼</span>
  </div>
  <div class="dds-select__list">
    <div class="dds-context-menu-item">Option 1</div>
    <div class="dds-context-menu-item">Option 2</div>
  </div>
</div>


<!-- Sizes -->
<div class="dds-select dds-select_sm">...</div>
<div class="dds-select dds-select_lg">...</div>


<!-- External -->
<div class="dds-select dds-select_external">...</div>
```


### Checkbox/Radio
```html
<!-- Checkbox -->
<label class="dds-custom-control">
  <input type="checkbox" class="dds-custom-control__field dds-custom-control__field_checkbox">
  <span class="dds-custom-control__icon dds-custom-control__icon_checkbox"></span>
  <span class="dds-custom-control__text">Checkbox label</span>
</label>


<!-- Radio -->
<label class="dds-custom-control">
  <input type="radio" name="group" class="dds-custom-control__field dds-custom-control__field_radio">
  <span class="dds-custom-control__icon dds-custom-control__icon_radio"></span>
  <span class="dds-custom-control__text">Radio label</span>
</label>


<!-- Themes -->
<label class="dds-custom-control dds-custom-control_blue">...</label>
<label class="dds-custom-control dds-custom-control_green">...</label>
<label class="dds-custom-control dds-custom-control_inverse">...</label>
<label class="dds-custom-control dds-custom-control_danger">...</label>
```


### Modal
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


<!-- Large -->
<div class="dds-modal dds-modal_lg dds-modal_open">...</div>
```


### Data Table
```html
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
      <td class="dds-data-table__cell">
        <span class="dds-status-tag dds-status-tag_green">Active</span>
      </td>
      <td class="dds-data-table__cell">
        <div class="dds-data-table-actions">
          <button class="dds-data-table-actions__item" title="Edit">✏️</button>
          <button class="dds-data-table-actions__item" title="Delete">🗑️</button>
        </div>
      </td>
    </tr>
    <tr class="dds-data-table__row dds-data-table__row_selected">
      <td class="dds-data-table__cell">Jane Smith</td>
      <td class="dds-data-table__cell">
        <span class="dds-status-tag dds-status-tag_orange">Pending</span>
      </td>
      <td class="dds-data-table__cell">...</td>
    </tr>
  </tbody>
</table>


<!-- Variants -->
<table class="dds-data-table dds-data-table_striped">...</table>
<table class="dds-data-table dds-data-table_fixed-header">...</table>
<table class="dds-data-table dds-data-table_selection">...</table>
```


### Table Block (Wrapper)
```html
<div class="dds-table-block">
  <div class="dds-table-block__header">
    <h3 class="dds-table-block__title">Users</h3>
    <div class="dds-table-block__actions">
      <button class="dds-btn dds-btn_primary dds-btn_green">Add User</button>
    </div>
  </div>
  <div class="dds-table-block__content">
    <table class="dds-data-table">...</table>
  </div>
</div>
```


### Status Tags
```html
<span class="dds-status-tag dds-status-tag_green">Success</span>
<span class="dds-status-tag dds-status-tag_red">Error</span>
<span class="dds-status-tag dds-status-tag_orange">Warning</span>
<span class="dds-status-tag dds-status-tag_blue">Info</span>
<span class="dds-status-tag dds-status-tag_gray">Neutral</span>
```


### Header
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
      <div class="dds-header__profile">
        <div class="dds-user-pic">JD</div>
      </div>
    </div>
  </div>
</header>


<!-- Inverse (dark) -->
<header class="dds-header dds-header_inverse">...</header>
```


### Tabs
```html
<div class="dds-tabs">
  <div class="dds-tabs__nav">
    <button class="dds-tabs__item dds-tabs__item_active">Tab 1</button>
    <button class="dds-tabs__item">Tab 2</button>
    <button class="dds-tabs__item">Tab 3</button>
  </div>
  <div class="dds-tabs__content">Content</div>
</div>
```


### Pagination
```html
<nav class="dds-pagination">
  <button class="dds-pagination__item dds-pagination__item_prev">‹</button>
  <button class="dds-pagination__item">1</button>
  <button class="dds-pagination__item dds-pagination__item_active">2</button>
  <button class="dds-pagination__item">3</button>
  <button class="dds-pagination__item dds-pagination__item_next">›</button>
</nav>
```


### Breadcrumbs
```html
<nav class="dds-breadcrumbs">
  <a class="dds-breadcrumbs__item">Home</a>
  <span class="dds-breadcrumbs__separator">/</span>
  <a class="dds-breadcrumbs__item">Products</a>
  <span class="dds-breadcrumbs__separator">/</span>
  <span class="dds-breadcrumbs__item dds-breadcrumbs__item_current">Details</span>
</nav>
```


### Avatar/User Pic
```html
<div class="dds-user-pic">
  <img class="dds-user-pic__img" src="avatar.jpg" alt="User">
</div>
<div class="dds-user-pic dds-user-pic_sm">JD</div>
<div class="dds-user-pic dds-user-pic_lg">JD</div>
```


### Progress
```html
<div class="dds-progress">
  <div class="dds-progress__bar" style="width: 60%"></div>
</div>
```


### Spinner
```html
<div class="dds-spinner"></div>
<div class="dds-spinner dds-spinner_sm"></div>
<div class="dds-spinner dds-spinner_lg"></div>
```


### Toggle
```html
<label class="dds-toggle">
  <input type="checkbox" class="dds-toggle__input">
  <span class="dds-toggle__track"></span>
  <span class="dds-toggle__thumb"></span>
</label>
```


### Tags
```html
<div class="dds-tags">
  <span class="dds-tag">Tag 1</span>
  <span class="dds-tag dds-tag_removable">
    Tag 2
    <button class="dds-tag__remove">×</button>
  </span>
</div>
```


---


## 📐 Layout Utilities


### Container
```html
<div class="dds-container">Content</div>
<div class="dds-container dds-container_fluid">Full width</div>
```


### Grid
```html
<div class="dds-row">
  <div class="dds-col-6">Half</div>
  <div class="dds-col-6">Half</div>
  <div class="dds-col-4">Third</div>
  <div class="dds-col-4">Third</div>
  <div class="dds-col-4">Third</div>
</div>


<!-- Responsive -->
<div class="dds-col-sm-12 dds-col-md-6 dds-col-lg-4">Responsive</div>
```


### Flex Utilities
```html
<div class="dds-flex">Flex container</div>
<div class="dds-inline-flex">Inline flex</div>
<div class="dds-flex dds-flex_column">Column</div>
<div class="dds-flex dds-flex_wrap">Wrap</div>
<div class="dds-flex dds-flex_center">Center</div>
<div class="dds-flex dds-flex_between">Space between</div>
```


### Spacing Utilities
```html
<div class="dds-m-3">Margin 16px</div>
<div class="dds-mt-2">Margin top 12px</div>
<div class="dds-mb-4">Margin bottom 20px</div>
<div class="dds-p-3">Padding 16px</div>
<div class="dds-px-2">Padding x 12px</div>
<div class="dds-py-3">Padding y 16px</div>
```


### Display
```html
<div class="dds-d-none">Hidden</div>
<div class="dds-d-block">Block</div>
<div class="dds-d-flex">Flex</div>
<div class="dds-d-inline-block">Inline block</div>
```


---


## ♿ Accessibility Patterns


### Focus Styles (Applied via `.dds-keyboard-focused`)
```css
.dds-keyboard-focused {
  outline: 2px solid var(--focus-color);
  outline-offset: 0;
}


/* For inputs with inner focus */
.dds-input__field:focus {
  box-shadow: inset 0 0 0 2px var(--focus-color);
}
```


### Screen Reader Only
```html
<span class="dds-sr-only">Screen reader text</span>
```


### ARIA Patterns
```html
<!-- Modal -->
<div class="dds-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
  <h2 id="modal-title" class="dds-modal__title">Title</h2>
</div>


<!-- Table with sort -->
<th class="dds-data-table__header-cell_sorting"
    aria-sort="ascending"
    tabindex="0"
    role="button">Name</th>


<!-- Status -->
<span class="dds-status-tag" role="status" aria-live="polite">Active</span>


<!-- Tabs -->
<div class="dds-tabs__nav" role="tablist">
  <button class="dds-tabs__item" role="tab" aria-selected="true" aria-controls="panel-1">Tab 1</button>
</div>
<div class="dds-tabs__content" role="tabpanel" id="panel-1">Content</div>
```


---


## 🔄 State Classes


### Interactive States
```html
<!-- Hover (CSS pseudo) -->
.dds-btn:hover { ... }


<!-- Active/Pressed -->
.dds-btn:active,
.dds-btn_dds-btn_selected { ... }


<!-- Focus (keyboard) -->
.dds-keyboard-focused { ... }


<!-- Disabled -->
.dds-btn_disabled,
.dds-input_disabled,
.dds-select_disabled { ... }


<!-- Loading -->
.dds-btn_loading .dds-btn__text { opacity: 0; }
.dds-btn_loading .dds-btn__icon_loading { display: block; }


<!-- Error -->
.dds-input_error .dds-input__field { border-color: var(--red); }
.dds-select_error .dds-select__field { border-color: var(--red); }
```


---


## 🎯 Theme Switching


### Dark Mode
```html
<html class="digital dds-dark">
  <!-- Or apply to container -->
  <div class="dds dds-dark">
    <button class="dds-btn dds-btn_primary dds-btn_white">Light on dark</button>
    <label class="dds-custom-control dds-custom-control_inverse">...</label>
  </div>
</html>
```


### Custom Theme
```scss
// In your theme override file
$digital-theme-brand_main: #YOUR_COLOR;
$digital-theme-brand_hover: blend-transparent($digital-cover_16, $digital-theme-brand_main);
$digital-theme-brand_active: blend-transparent($digital-cover_24, $digital-theme-brand_main);
$digital-theme-brand_s_hover: blend-transparent($digital-cover_32, $digital-theme-brand_main);
$digital-theme-brand_s_active: blend-transparent($digital-cover_48, $digital-theme-brand_main);


$digital-theme-colors: map-merge($digital-theme-colors, ("brand": $digital-theme-brand_main));
```


```html
<button class="dds-btn dds-btn_primary dds-btn_brand">Brand Button</button>
```


---


## 📱 Responsive Classes


```html
<!-- Device detection (applied via JS) -->
<html class="digital dds-desktop">...</html>
<html class="digital dds-tablet">...</html>
<html class="digital dds-mobile">...</html>


<!-- Component responsive -->
<div class="dds-data-table dds-data-table_sm">Small table</div>
<div class="dds-modal dds-modal_lg">Large modal</div>
```


---


## ⚡ Quick Component Composition


### Form Field Group
```html
<div class="dds-flex dds-flex_column" style="gap: 16px; max-width: 400px;">
  <div class="dds-input">
    <div class="dds-input__header">
      <label class="dds-input__label">Email</label>
    </div>
    <div class="dds-input__wrap">
      <input class="dds-input__field" type="email" required>
    </div>
    <div class="dds-input__footer">
      <span class="dds-input__description">We'll never share your email</span>
    </div>
  </div>
 
  <div class="dds-input">
    <div class="dds-input__header">
      <label class="dds-input__label">Password</label>
    </div>
    <div class="dds-input__wrap">
      <input class="dds-input__field" type="password" required>
      <span class="dds-input__icon dds-icon">👁</span>
    </div>
  </div>
 
  <label class="dds-custom-control">
    <input type="checkbox" class="dds-custom-control__field dds-custom-control__field_checkbox">
    <span class="dds-custom-control__icon dds-custom-control__icon_checkbox"></span>
    <span class="dds-custom-control__text">Remember me</span>
  </label>
 
  <button class="dds-btn dds-btn_primary dds-btn_green dds-btn_fluid-width">Sign In</button>
</div>
```


### Card-like Layout (using table-block)
```html
<div class="dds-table-block">
  <div class="dds-table-block__header">
    <h3 class="dds-table-block__title">Account Settings</h3>
  </div>
  <div class="dds-table-block__content" style="padding: 24px;">
    <!-- Form content -->
  </div>
</div>
```


---


## 🚫 Common Mistakes to Avoid


| ❌ Wrong | ✅ Correct |
|----------|-----------|
| `.btn-primary` | `.dds-btn_primary` |
| `.form-control` | `.dds-input__field` |
| `border-radius: 8px` | `border-radius: 0` (default) |
| Custom colors | Use theme tokens |
| `px` for spacing | Use 8px scale (8, 12, 16, 20, 24) |
| Multiple fonts | Use Open Sans only |
| JS for dropdowns | Use CSS-only `.dds-select` |


---


## 📦 Import Order (SCSS)


```scss
// 1. Theme variables & functions
@import 'themes/default/functions';
@import 'themes/default/mixins';
@import 'themes/default/variables';


// 2. Core components (dependencies first)
@import 'components/common';
@import 'components/icons';
@import 'components/button';
@import 'components/controlForm';
@import 'components/input';
@import 'components/textarea';
@import 'components/select';
@import 'components/dropdown';


// 3. Layout components
@import 'components/header';
@import 'components/table-block';
@import 'components/data-table';


// 4. Feedback/Overlay
@import 'components/modal';
@import 'components/tooltip';
@import 'components/toaster';
@import 'components/popup';
@import 'components/spinner';
@import 'components/progress';


// 5. Navigation
@import 'components/tabs';
@import 'components/vertical-tabs';
@import 'components/breadcrumbs';
@import 'components/pagination';
@import 'components/pager';


// 6. Data display
@import 'components/status-tag';
@import 'components/user-pic';
@import 'components/profile';
@import 'components/profile-block';
@import 'components/list';
@import 'components/tree';
@import 'components/rating';
@import 'components/counter';
@import 'components/tags';


// 7. Form advanced
@import 'components/multi-select';
@import 'components/datepicker';
@import 'components/timepicker';
@import 'components/slider';
@import 'components/slider-tick';
@import 'components/number-input';
@import 'components/suggestions-tags-input';
@import 'components/toggle';
@import 'components/segmented';
@import 'components/upload-area';
@import 'components/wizard';
@import 'components/quick-actions';
@import 'components/search';
@import 'components/context-menu';
@import 'components/logo';
@import 'components/link';
```


---


This reference card contains everything needed to implement DDS components correctly. Keep it handy when prompting AI code editors!

