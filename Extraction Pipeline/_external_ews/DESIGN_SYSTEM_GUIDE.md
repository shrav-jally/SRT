# Digital Design System - Complete Style Guide


A comprehensive design system documentation for the Deloitte Digital Design System (DDS) extracted from the live-example project. Use this as a reference for AI code editors to replicate this design language across projects.


---


## 🎨 Design Tokens


### Color Palette


#### Core Colors
```scss
// Primary brand colors
$digital-deloitte-green: #86BC25;
$digital-accessible-green: #26890D;
$digital-accessible-blue: #007CB0;
$digital-accessible-teal: #0D8390;
$digital-red: #DA291C;


// Neutral colors
$digital-black: #000000;
$digital-white: #FFFFFF;


// Cool Gray Scale
$digital-cool-gray-2:  #D0D0CE;
$digital-cool-gray-4:  #BBBCBC;
$digital-cool-gray-6:  #A7A8AA;
$digital-cool-gray-7:  #97999B;
$digital-cool-gray-9:  #75787B;
$digital-cool-gray-10: #63666A;
$digital-cool-gray-11: #53565A;
```


#### Semantic Color Themes
Each theme includes: main, hover, active, strong-hover (s_hover), strong-active (s_active), and inverse variants.


| Theme | Main Color | Usage |
|-------|-----------|-------|
| **Green** | `#86BC25` | Primary actions, success states |
| **Dark** | `#000000` | High contrast, dark backgrounds |
| **White** | `#FFFFFF` | On dark backgrounds |
| **Blue** | `#007CB0` | Primary brand, links, info |
| **Danger** | `#DA291C` | Errors, destructive actions |


#### Extended Palette
- **Green Scale**: 1-7 (light to dark)
- **Blue Scale**: 1-7 (light to dark)
- **Teal Scale**: 1-7 (light to dark)
- **Accent**: Orange `#ED8B00`, Yellow `#FFCD00`
- **Bright**: Green `#0DF200`, Teal `#3EFAC5`, Blue `#33F0FF`


#### Transparency Layers
```scss
// Dark backgrounds with white overlay
$digital-transparent_dark_white_hover:   rgba(255,255,255, 0.16);
$digital-transparent_dark_white_active:  rgba(255,255,255, 0.24);
$digital-transparent_dark_white_s_hover: rgba(255,255,255, 0.32);
$digital-transparent_dark_white_s_active:rgba(255,255,255, 0.48);


// Light backgrounds with black overlay
$digital-transparent_light_black_hover:   rgba(0,0,0, 0.08);
$digital-transparent_light_black_active:  rgba(0,0,0, 0.12);
$digital-transparent_light_black_s_hover: rgba(0,0,0, 0.16);
$digital-transparent_light_black_s_active:rgba(0,0,0, 0.24);
```


---


### Typography


#### Font Family
```scss
$digital-font-base: "Open Sans", sans-serif;
$digital-font-monospace: monospace;
```


#### Font Size Scale
| Level | Size | Line Height |
|-------|------|-------------|
| 1 | 56px | 72px |
| 2 | 40px | 52px |
| 3 | 32px | 40px |
| 4 | 24px | 36px |
| 5 | 16px | 24px |
| 6 | 14px | 20px |
| 7 | 12px | 16px |
| 8 | 10px | - |
| 9 | 8px | - |


#### Font Weights
- `lighter`: lighter
- `light`: 300
- `normal`: 400
- `semibold`: 600
- `bold`: 700
- `bolder`: bolder


#### Component Typography Presets
```scss
// Regular
$digital-regular-12:       400 12px/16px;
$digital-regular-14:       400 14px/16px;
$digital-regular-14-larger:400 14px/20px;
$digital-regular-16:       400 16px/20px;
$digital-regular-16-enlarged:400 16px/24px;


// Semibold
$digital-semibold-10:      600 10px/16px;
$digital-semibold-12:      600 12px/16px;
$digital-semibold-14:      600 14px/16px;
$digital-semibold-14-enlarged:600 14px/20px;
$digital-semibold-14-larger:  600 14px/24px;
$digital-semibold-16:      600 16px/20px;
$digital-semibold-16-enlarged:600 16px/24px;


// Bold
$digital-bold-14:          700 14px/20px;
```


#### Heading Styles
| Heading | Size | Line Height | Weight |
|---------|------|-------------|--------|
| H1 | 56px | 72px | Semibold |
| H2 | 40px | 52px | Semibold |
| H3 | 32px | 40px | Semibold |
| H4 | 24px | 36px | Bold |
| H5 | 16px | 24px | Semibold |


#### Body & Label
| Type | Size | Line Height | Weight |
|------|------|-------------|--------|
| Body | 14px | 20px | Normal |
| Body Semibold | 14px | 20px | Semibold |
| Body Bold | 14px | 20px | Bold |
| Label | 12px | 16px | Normal |
| Label Semibold | 12px | 16px | Semibold |


---


### Spacing System


#### Base Spacer
```scss
$digital-spacer: 8px;
```


#### Spacer Scale
| Level | Value |
|-------|-------|
| 0 | 0 |
| 1 | 8px |
| 2 | 12px |
| 3 | 16px |
| 4 | 20px |
| 5 | 24px |


#### Negative Margins
Enabled via `$digital-enable-negative-margins: true`


---


### Border System


```scss
$digital-border-width: 1px;
$digital-border-color: $digital-cool-gray-2; // #D0D0CE


// Border Widths
1: 1px, 2: 2px, 3: 3px, 4: 4px, 5: 5px


// Border Radius
$digital-border-radius: 4px;
$digital-border-radius-sm: 2px;
$digital-border-radius-lg: 6px;
$digital-border-radius-pill: 50rem;
```


---


### Focus System
```scss
$digital-focus-border-color: $digital-blue-5; // #005587
$digital-focus-border-width: 2px;
$digital-focus: 2px solid #005587;
```


---


### Shadow System
```scss
$digital-box-shadow:        0 8px 16px rgba(0,0,0,.15);
$digital-box-shadow-sm:     0 2px 4px rgba(0,0,0,.075);
$digital-box-shadow-lg:     0 16px 48px rgba(0,0,0,.175);
$digital-box-shadow-inset:  inset 0 1px 2px rgba(0,0,0,.075);
```


---


### Breakpoints
```scss
$digital-grid-breakpoints: (
  xs: 0,
  sm: 576px,
  md: 768px,
  lg: 992px,
  xl: 1200px,
  xxl: 1400px
);
```


---


### Grid System
```scss
$digital-grid-columns: 12;
$digital-grid-row-columns: 6;
$digital-grid-gutter-width: 24px;


$digital-container-max-widths: (
  sm: 540px,
  md: 720px,
  lg: 960px,
  xl: 1280px
);
```


---


### Transitions
```scss
$digital-transition-duration: .15s;
```


---


### Z-Index Scale
```scss
$digital-modal--zIndex: 1000;
$digital-modal__overlay--zIndex: 999;
$digital-data-table_fixed-header--zIndex: 10;
$digital-data-table_fixed-left-column--zIndex: 11;
```


---


## 🧱 Component Library


### 1. Button (`.dds-btn`)


#### Sizes
| Size | Font | Padding | Icon Margin |
|------|------|---------|-------------|
| LG | 16px/24px | 18px 24px | 12px |
| MD | 14px/20px | 12px 16px | 8px |
| SM | 12px/16px | 8px 12px | 5px |


#### Kinds
| Kind | Description | Background | Border | Text Color |
|------|-------------|------------|--------|------------|
| **Primary** | Main action | Transparent | Theme color | Theme color |
| **Secondary** | Alternative | Transparent | Gray-11 | Gray-11 |
| **Secondary-Loud** | Emphasized secondary | Gray-11 | Gray-11 | White |
| **Silent** | Subtle | Transparent | Transparent | Black |


#### Themes
- `._green` - Deloitte Green
- `._dark` - Black
- `._blue` - Accessible Blue
- `._danger` - Red
- `._white` - White (for dark backgrounds)


#### States
- Default, Hover, Active, Disabled, Loading, Selected
- Inverse variants for dark backgrounds
- Dark variants for dark mode


#### CSS Classes
```html
<!-- Primary button -->
<button class="dds-btn dds-btn_primary dds-btn_green">Primary</button>


<!-- Secondary button -->
<button class="dds-btn dds-btn_secondary">Secondary</button>


<!-- Silent button -->
<button class="dds-btn dds-btn_silent">Silent</button>


<!-- With icon -->
<button class="dds-btn dds-btn_primary dds-btn_green dds-btn_with-icon">
  <span class="dds-btn__content">
    <span class="dds-btn__text">Save</span>
    <span class="dds-btn__icon dds-icon">icon</span>
  </span>
</button>


<!-- Fluid width -->
<button class="dds-btn dds-btn_primary dds-btn_fluid-width">Full Width</button>
```


---


### 2. Input (`.dds-input`)


#### Variants
- **Default** - Standard input with label above
- **External** - Compact version for dense UIs
- **With Icon** - Input with trailing icon


#### Sizes
| Size | Height | Font | Padding |
|------|--------|------|---------|
| Default | Auto | 14px/20px | 9px 16px 11px |
| External MD | 32px | 14px/20px | 12px |
| External LG | 40px | 16px/24px | 16px |
| External SM | 24px | 12px/16px | 8px 4px |


#### States
- Default, Hover, Focus, Error, Disabled
- With internal label (floating)
- Counter/character limit support


#### CSS Classes
```html
<!-- Standard input -->
<div class="dds-input">
  <div class="dds-input__header">
    <label class="dds-input__label">Email</label>
  </div>
  <div class="dds-input__wrap">
    <input class="dds-input__field" type="email" placeholder="Enter email">
  </div>
  <div class="dds-input__footer">
    <span class="dds-input__description">Helper text</span>
  </div>
</div>


<!-- External (compact) -->
<div class="dds-input dds-input_external">
  <input class="dds-input__field" type="text" placeholder="Search...">
</div>


<!-- Error state -->
<div class="dds-input dds-input_error">
  <input class="dds-input__field" type="text" value="Invalid">
  <div class="dds-input__error-message">Error message</div>
</div>
```


---


### 3. Textarea (`.dds-textarea`)


#### Features
- Vertical resize only
- Internal floating label support
- Character counter
- External variant


#### CSS Classes
```html
<div class="dds-textarea">
  <div class="dds-textarea__header">
    <label class="dds-textarea__label">Description</label>
  </div>
  <div class="dds-textarea__wrap">
    <textarea class="dds-textarea__field" placeholder="Enter description"></textarea>
  </div>
  <div class="dds-textarea__footer">
    <span class="dds-textarea__length-limit">0/500</span>
  </div>
</div>
```


---


### 4. Select (`.dds-select`)


#### Sizes
| Size | Min Height | Font | Icon Size |
|------|------------|------|-----------|
| SM | 32px | 12px/16px | 16px |
| MD | 40px | 14px/20px | 20px |
| LG | 48px | 16px/24px | 24px |


#### Variants
- **Default** - With title label
- **External** - Compact, no title


#### CSS Classes
```html
<!-- Standard select -->
<div class="dds-select">
  <span class="dds-select__title">Country</span>
  <div class="dds-select__field">
    <span class="dds-select__placeholder">Select country</span>
    <span class="dds-select__icon dds-icon">▼</span>
  </div>
  <div class="dds-select__list">
    <div class="dds-context-menu-item">USA</div>
    <div class="dds-context-menu-item">Canada</div>
  </div>
</div>


<!-- External select -->
<div class="dds-select dds-select_external">
  <div class="dds-select__field">...</div>
</div>
```


---


### 5. Checkbox & Radio (`.dds-custom-control`)


#### Types
- `._checkbox` - Square checkbox
- `._radio` - Circular radio button


#### Themes
- Default (Dark)
- `._blue` - Blue theme
- `._green` - Green theme
- `._inverse` - White theme for dark backgrounds
- `._danger` - Red theme for errors


#### CSS Classes
```html
<!-- Checkbox -->
<label class="dds-custom-control">
  <input type="checkbox" class="dds-custom-control__field dds-custom-control__field_checkbox">
  <span class="dds-custom-control__icon dds-custom-control__icon_checkbox"></span>
  <span class="dds-custom-control__text">Accept terms</span>
</label>


<!-- Radio -->
<label class="dds-custom-control">
  <input type="radio" name="option" class="dds-custom-control__field dds-custom-control__field_radio">
  <span class="dds-custom-control__icon dds-custom-control__icon_radio"></span>
  <span class="dds-custom-control__text">Option 1</span>
</label>
```


---


### 6. Modal (`.dds-modal`)


#### Sizes
- Default: 560px max-width
- Large (`._lg`): 800px max-width
- Mobile: Full screen bottom sheet


#### Structure
```html
<div class="dds-modal dds-modal_open">
  <div class="dds-modal__header">
    <h2 class="dds-modal__title">Modal Title</h2>
    <button class="dds-modal__close dds-icon">×</button>
  </div>
  <div class="dds-modal__body">
    <!-- Content -->
  </div>
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
```


---


### 7. Data Table (`.dds-data-table`)


#### Features
- Sortable columns
- Row selection
- Expandable rows
- Fixed header/footer/columns
- Striped rows
- Row actions (appear on hover)
- Search/filter integration


#### Row States
- Default, Hover, Selected, Expanded, Summary
- Keyboard focus support


#### CSS Classes
```html
<table class="dds-data-table">
  <thead>
    <tr>
      <th class="dds-data-table__header-cell dds-data-table__header-cell_sorting">Name</th>
      <th class="dds-data-table__header-cell">Status</th>
    </tr>
  </thead>
  <tbody>
    <tr class="dds-data-table__row">
      <td class="dds-data-table__cell">John Doe</td>
      <td class="dds-data-table__cell">
        <span class="dds-status-tag dds-status-tag_green">Active</span>
      </td>
    </tr>
  </tbody>
</table>
```


---


### 8. Table Block (`.dds-table-block`)


Wrapper component for data tables with header, title, and actions.


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


---


### 9. Dropdown (`.dds-dropdown`)


Wrapper for select-like components using button as trigger.


```html
<div class="dds-dropdown">
  <button class="dds-btn dds-btn_secondary">Select Option</button>
  <div class="dds-dropdown__menu">
    <!-- Context menu items -->
  </div>
</div>
```


---


### 10. Header (`.dds-header`)


#### Variants
- Default
- `._inverse` - Dark theme
- `._mobile` - Mobile responsive
- Search active state
- Mobile navigation active state


#### Structure
```html
<header class="dds-header">
  <div class="dds-header__container">
    <div class="dds-header__main">
      <div class="dds-header__logo"><img src="logo.svg"></div>
      <a class="dds-header__project-name">Project Name</a>
    </div>
    <div class="dds-header__left-wrap">
      <nav class="dds-header__navigation">...</nav>
    </div>
    <div class="dds-header__right-wrap">
      <div class="dds-header__icons">
        <button class="dds-btn dds-btn_silent dds-btn_dark dds-header__btn-icon">...</button>
      </div>
      <div class="dds-header__profile">...</div>
    </div>
  </div>
</header>
```


---


### 11. Status Tag (`.dds-status-tag`)


```html
<span class="dds-status-tag dds-status-tag_green">Active</span>
<span class="dds-status-tag dds-status-tag_red">Inactive</span>
<span class="dds-status-tag dds-status-tag_orange">Pending</span>
<span class="dds-status-tag dds-status-tag_blue">Info</span>
<span class="dds-status-tag dds-status-tag_gray">Default</span>
```


---


### 12. Tooltip (`.dds-tooltip`)


```html
<div class="dds-tooltip">
  <div class="dds-tooltip__content">Tooltip text</div>
</div>
```


---


### 13. Tabs (`.dds-tabs`)


```html
<div class="dds-tabs">
  <div class="dds-tabs__nav">
    <button class="dds-tabs__item dds-tabs__item_active">Tab 1</button>
    <button class="dds-tabs__item">Tab 2</button>
  </div>
  <div class="dds-tabs__content">Content</div>
</div>
```


---


### 14. Pagination (`.dds-pagination`)


```html
<nav class="dds-pagination">
  <button class="dds-pagination__item">1</button>
  <button class="dds-pagination__item dds-pagination__item_active">2</button>
  <button class="dds-pagination__item">3</button>
</nav>
```


---


### 15. Progress (`.dds-progress`)


```html
<div class="dds-progress">
  <div class="dds-progress__bar" style="width: 60%"></div>
</div>
```


---


### 16. Spinner (`.dds-spinner`)


```html
<div class="dds-spinner"></div>
<div class="dds-spinner dds-spinner_sm"></div>
<div class="dds-spinner dds-spinner_lg"></div>
```


---


### 17. Breadcrumbs (`.dds-breadcrumbs`)


```html
<nav class="dds-breadcrumbs">
  <a class="dds-breadcrumbs__item">Home</a>
  <span class="dds-breadcrumbs__separator">/</span>
  <a class="dds-breadcrumbs__item">Products</a>
  <span class="dds-breadcrumbs__separator">/</span>
  <span class="dds-breadcrumbs__item dds-breadcrumbs__item_current">Details</span>
</nav>
```


---


### 18. Avatar/User Pic (`.dds-user-pic`)


```html
<div class="dds-user-pic">
  <img class="dds-user-pic__img" src="avatar.jpg" alt="User">
</div>
<div class="dds-user-pic dds-user-pic_sm">JD</div>
<div class="dds-user-pic dds-user-pic_lg">JD</div>
```


---


### 19. Toggle (`.dds-toggle`)


```html
<label class="dds-toggle">
  <input type="checkbox" class="dds-toggle__input">
  <span class="dds-toggle__track"></span>
  <span class="dds-toggle__thumb"></span>
</label>
```


---


### 20. Tags (`.dds-tags`)


```html
<div class="dds-tags">
  <span class="dds-tag">Tag 1</span>
  <span class="dds-tag dds-tag_removable">Tag 2
    <button class="dds-tag__remove">×</button>
  </span>
</div>
```


---


### 21. Tree (`.dds-tree`)


Hierarchical tree view with expand/collapse.


---


### 22. Wizard (`.dds-wizard`)


Step-by-step progress indicator.


---


### 23. Upload Area (`.dds-upload-area`)


Drag-and-drop file upload zone.


---


### 24. Datepicker (`.dds-datepicker`)


Calendar date selection component.


---


### 25. Timepicker (`.dds-timepicker`)


Time selection component.


---


### 26. Slider (`.dds-slider`)


Range slider input.


---


### 27. Rating (`.dds-rating`)


Star rating component.


---


### 28. Counter (`.dds-counter`)


Increment/decrement number input.


---


### 29. Number Input (`.dds-number-input`)


Numeric input with stepper.


---


### 30. Multi-select (`.dds-multi-select`)


Multiple selection dropdown.


---


### 31. Suggestions Tags Input (`.dds-suggestions-tags-input`)


Autocomplete with tag creation.


---


### 32. Context Menu (`.dds-context-menu`)


Right-click or dropdown menu.


---


### 33. Popover/Popup (`.dds-popup`)


Floating content container.


---


### 34. Vertical Tabs (`.dds-vertical-tabs`)


Sidebar-style tab navigation.


---


### 35. Quick Actions (`.dds-quick-actions`)


Floating action buttons.


---


### 36. Profile Block (`.dds-profile-block`)


User profile display component.


---


### 37. Link (`.dds-link`)


Styled link component.


---


### 38. List (`.dds-list`)


Styled list component.


---


### 39. Toaster (`.dds-toaster`)


Toast notification system.


---


### 40. Segmented Control (`.dds-segmented`)


Segmented button group.


---


## 🎯 Usage Patterns


### CSS Custom Properties (CSS Variables)


The system exposes all tokens as CSS custom properties under `:root`:


```css
:root {
  --accessible-green: #26890D;
  --accessible-blue: #007CB0;
  --cool-gray-2: #D0D0CE;
  --cool-gray-10: #63666A;
  --cool-gray-11: #53565A;
  --deloitte-green: #86BC25;
  --red: #DA291C;
  --black: #000000;
  --white: #FFFFFF;
  /* ... all color variants with _hover, _active, _s_hover, _s_active, _inverse suffixes */
}
```


### Theme Application


Wrap your application with the theme class:


```html
<div class="digital">
  <!-- All components go here -->
</div>
```


Or use the prefix:


```html
<div class="dds">
  <!-- All components go here -->
</div>
```


### Responsive Design


Device-specific classes:
- `.dds-desktop` - Desktop styles
- `.dds-tablet` - Tablet styles (≤768px)
- `.dds-mobile` - Mobile styles (≤576px)


Components automatically adapt via media queries in their theme files.


---


## 🔧 Integration Guide for AI Code Editors


### For New Projects


1. **Copy the theme structure**:
   ```
   styles/
   ├── themes/
   │   └── default/
   │       ├── _variables/
   │       │   ├── _colors.scss
   │       │   ├── _typography.scss
   │       │   ├── _core.scss
   │       │   ├── _common.scss
   │       │   └── _themes.scss
   │       ├── _functions.scss
   │       ├── _mixins.scss
   │       ├── _main.scss
   │       └── [component].scss
   ├── components/
   │   └── [component].scss
   └── main.scss
   ```


2. **Import order in main.scss**:
   ```scss
   @import 'themes/default/main';
   @import 'components/common';
   @import 'components/button';
   @import 'components/input';
   /* ... other components */
   ```


3. **Apply theme class** to root element:
   ```html
   <html class="digital">
   ```


### For Existing Projects


1. **Map your existing tokens** to DDS tokens
2. **Replace component classes** with DDS equivalents
3. **Update color values** to use semantic tokens
4. **Adjust spacing** to 8px base grid
5. **Migrate typography** to DDS scale


### Component Migration Checklist


- [ ] Buttons → `.dds-btn` with kind/theme modifiers
- [ ] Inputs → `.dds-input` with external variant for dense UIs
- [ ] Selects → `.dds-select`
- [ ] Checkboxes/Radios → `.dds-custom-control`
- [ ] Modals → `.dds-modal`
- [ ] Tables → `.dds-data-table` + `.dds-table-block`
- [ ] Headers → `.dds-header`
- [ ] Navigation → Tabs, Breadcrumbs, Pagination
- [ ] Feedback → Toaster, Tooltip, Progress, Spinner
- [ ] Data display → Status tags, Avatar, Tree, List


---


## ♿ Accessibility


### Focus Management
- All interactive elements have visible focus states (2px solid blue-5)
- Keyboard navigation supported
- Focus trapping in modals


### Color Contrast
- All semantic colors meet WCAG AA standards
- Accessible green/blue/teal specifically designed for contrast


### ARIA Support
- Components use proper ARIA attributes
- Screen reader compatible
- Semantic HTML structure


---


## 📱 Responsive Breakpoints


| Breakpoint | Class | Width |
|------------|-------|-------|
| XS | `.dds-mobile` | < 576px |
| SM | `.dds-tablet` | ≥ 576px |
| MD | `.dds-desktop` | ≥ 768px |
| LG | | ≥ 992px |
| XL | | ≥ 1200px |
| XXL | | ≥ 1400px |


---


## 🎨 Theming


### Creating Custom Themes


1. **Override variables** in `_variables/_themes.scss`:
   ```scss
   $digital-theme-custom_main: #YOUR_COLOR;
   $digital-theme-custom_hover: blend-transparent($digital-cover_16, $digital-theme-custom_main);
   ```


2. **Add to theme map**:
   ```scss
   $digital-theme-colors: (
     "custom": $digital-theme-custom_main,
     ...
   );
   ```


3. **Use in components**:
   ```html
   <button class="dds-btn dds-btn_primary dds-btn_custom">Custom</button>
   ```


---


## 📦 File Structure Reference


```
public/assets/styles/digital-theme/
├── main.scss                      # Entry point
├── themes/
│   └── themeProject.scss          # Theme selector
│   └── default/
│       ├── _main.scss             # Theme entry
│       ├── _variables.scss        # Variable imports
│       ├── _functions.scss        # Sass functions
│       ├── _mixins.scss           # Sass mixins
│       ├── _variables/
│       │   ├── _core.scss         # Prefix, device classes
│       │   ├── _colors.scss       # Full color palette
│       │   ├── _typography.scss   # Type scale
│       │   ├── _common.scss       # Spacing, borders, shadows
│       │   └── _themes.scss       # Semantic themes
│       └── [component].scss       # Component themes
└── components/
    ├── common.scss                # Global utilities
    ├── button.scss                # Button component
    ├── input.scss                 # Input component
    ├── textarea.scss              # Textarea component
    ├── select.scss                # Select component
    ├── controlForm.scss           # Checkbox/Radio
    ├── modal.scss                 # Modal component
    ├── data-table.scss            # Data table
    ├── table-block.scss           # Table wrapper
    ├── dropdown.scss              # Dropdown
    ├── header.scss                # Header
    ├── status-tag.scss            # Status tags
    ├── tabs.scss                  # Tabs
    ├── pagination.scss            # Pagination
    ├── progress.scss              # Progress bar
    ├── spinner.scss               # Spinner
    ├── breadcrumbs.scss           # Breadcrumbs
    ├── user-pic.scss              # Avatar
    ├── toggle.scss                # Toggle switch
    ├── tags.scss                  # Tags
    ├── tree.scss                  # Tree view
    ├── wizard.scss                # Step wizard
    ├── upload-area.scss           # File upload
    ├── datepicker.scss            # Date picker
    ├── timepicker.scss            # Time picker
    ├── slider.scss                # Slider
    ├── rating.scss                # Rating stars
    ├── counter.scss               # Counter
    ├── number-input.scss          # Number input
    ├── multi-select.scss          # Multi-select
    ├── suggestions-tags-input.scss # Tag input
    ├── context-menu.scss          # Context menu
    ├── popup.scss                 # Popover
    ├── vertical-tabs.scss         # Vertical tabs
    ├── quick-actions.scss         # Floating actions
    ├── profile.scss               # Profile block
    ├── link.scss                  # Links
    ├── list.scss                  # Lists
    ├── toaster.scss               # Toasts
    ├── segmented.scss             # Segmented control
    ├── icons.scss                 # Icon system
    ├── tooltip.scss               # Tooltips
    ├── profile-block.scss         # Profile block
    ├── logo.scss                  # Logo
    └── search.scss                # Search
```


---


## 🚀 Quick Start Template


```html
<!DOCTYPE html>
<html class="digital" lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DDS Project</title>
  <link rel="stylesheet" href="path/to/digital-theme.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
</head>
<body>
  <header class="dds-header">
    <div class="dds-header__container">
      <div class="dds-header__main">
        <div class="dds-header__logo">
          <img src="logo.svg" alt="Logo">
        </div>
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
              <td class="dds-data-table__cell" style="font: 400 14px/20px 'Open Sans', sans-serif; padding: 12px 16px;">John Doe</td>
              <td class="dds-data-table__cell">
                <span class="dds-status-tag dds-status-tag_green">Active</span>
              </td>
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


## 📝 Migration Notes


### From Bootstrap/Material/UI Libraries


| Concept | Bootstrap | Material | DDS |
|---------|-----------|----------|-----|
| Primary Button | `.btn-primary` | `<Button color="primary">` | `.dds-btn_primary .dds-btn_green` |
| Input | `.form-control` | `<TextField>` | `.dds-input__field` |
| Modal | `.modal` | `<Dialog>` | `.dds-modal` |
| Table | `.table` | `<Table>` | `.dds-data-table` |
| Card | `.card` | `<Card>` | Compose with table-block |
| Grid | `.row/.col` | `<Grid>` | CSS Grid + container |


### Key Differences
1. **No JavaScript dependencies** - Pure CSS/SCSS
2. **BEM methodology** - Block__Element--Modifier
3. **Semantic theming** - Green/Blue/Dark/White/Danger
4. **8px spacing grid** - Consistent rhythm
5. **Open Sans font** - Single font family
6. **Zero border-radius** - Sharp corners by default


---


This design system provides a complete, production-ready foundation for building consistent, accessible, and maintainable user interfaces. All tokens are systematically organized and components follow predictable patterns.
