---
phase: 20-desktop-workstation
type: frontend
viewport: desktop (1280px+)
framework: HTMX + Alpine.js + Tailwind v4 CDN
---

# UI Design Contract: Desktop Workstation

## 1. Layout Structure

### 3-Column Grid
```
┌──────────┬────────────────────────┬─────────────┐
│  QUEUE   │      MEDIA PREVIEW     │   DECISION   │
│  (25%)   │       (45%)            │   (30%)      │
│          │                        │              │
│ Filter   │  ┌──────────────────┐  │ Context      │
│ Controls │  │  Video Player    │  │ - Scene      │
│ ──────── │  │  (16:9 aspect)   │  │ - Shot #     │
│          │  └──────────────────┘  │ - Emotion    │
│ Shot 1 ● │                        │ - Tags       │
│ Shot 2   │  ┌─┐ ┌─┐ ┌─┐         │              │
│ Shot 3   │  │T│ │T│ │T│ Cands   │ Prompts      │
│ Shot 4   │  └─┘ └─┘ └─┘         │ - Positive   │
│ Shot 5   │                        │ - Negative   │
│ ...      │  Frame: First | Last   │              │
│          │                        │ Node Status  │
│ ▼ Load   │                        │ - Render ✓   │
│ more     │                        │ - Compose ◌  │
│          │                        │              │
│          │                        │ [Y] Approve  │
│          │                        │ [N] Reject   │
│          │                        │ [B] Batch    │
└──────────┴────────────────────────┴─────────────┘
```

### Collapsed States
- Left collapsed: icon-only sidebar (shot count badge, filter icon)
- Right collapsed: icon-only sidebar (approve/reject icons)
- Collapse via toggle button on panel edge

### Comparison Mode (Center Panel)
```
┌──────────────┬──────────────┐
│  First Frame │  Last Frame  │
│              │              │
│              │              │
├──────────────┴──────────────┤
│ Mode: [First/Last] [vs History] [vs Ref] │
└─────────────────────────────┘
```

## 2. Color & Typography

### Palette (Tailwind classes)
- **Background:** `bg-gray-900` (dark theme — review focused, reduces eye strain)
- **Panels:** `bg-gray-800` with `border-r border-gray-700`
- **Active shot:** `ring-2 ring-blue-500 bg-gray-750`
- **Selected (batch):** `ring-2 ring-yellow-500`
- **Approve:** `text-green-400` / `bg-green-600`
- **Reject:** `text-red-400` / `bg-red-600`
- **Risk badges:** HIGH=`bg-red-900 text-red-300`, MEDIUM=`bg-yellow-900 text-yellow-300`, LOW=`bg-green-900 text-green-300`

### Typography
- Shot card title: `text-sm font-medium text-gray-200`
- Context info: `text-xs text-gray-400`
- Decision buttons: `text-sm font-semibold uppercase`
- Keyboard hint: `text-xs text-gray-500 font-mono` (e.g., "Y" badge on approve button)

## 3. Key Components

### Shot Queue Card (Left Panel)
```html
<div class="p-2 hover:bg-gray-750 cursor-pointer flex items-center gap-2"
     x-bind:class="{'ring-2 ring-blue-500': activeShot === shot.id,
                     'ring-2 ring-yellow-500': selectedItems.includes(shot.id)}">
  <img class="w-16 h-9 object-cover rounded" :src="shot.thumbnail" />
  <div class="flex-1 min-w-0">
    <div class="text-sm text-gray-200 truncate">Shot {{ shot.shot_number }}</div>
    <div class="text-xs text-gray-400">Scene {{ shot.scene }}</div>
  </div>
  <span class="text-xs px-1.5 py-0.5 rounded" :class="riskClass(shot.risk)">{{ shot.risk }}</span>
</div>
```

### Video Player (Center Panel)
```html
<div class="relative bg-black rounded-lg overflow-hidden aspect-video">
  <video id="shot-video" class="w-full h-full"
         :src="activeShot?.video_url" preload="metadata">
  </video>
  <!-- Timeline scrubber -->
  <input type="range" min="0" max="100" value="0"
         class="absolute bottom-0 w-full h-1 bg-gray-600 accent-blue-500" />
</div>
```

### Candidate Grid (Center Panel, below video)
```html
<div class="grid grid-cols-3 gap-2 mt-2">
  <template x-for="(cand, idx) in activeShot?.candidates" :key="idx">
    <button class="relative rounded overflow-hidden border-2"
            :class="selectedCandidate === idx ? 'border-blue-500' : 'border-transparent'"
            @click="selectedCandidate = idx">
      <img class="w-full h-12 object-cover" :src="cand.thumbnail" />
      <span class="absolute bottom-0 right-0 text-xs bg-black/60 px-1" x-text="idx + 1"></span>
    </button>
  </template>
</div>
```

### Decision Panel (Right Panel)
```html
<div class="space-y-4">
  <!-- Narrative Context -->
  <div class="space-y-2">
    <h3 class="text-xs font-semibold uppercase text-gray-500">Context</h3>
    <div class="text-sm text-gray-300" x-text="activeShot?.narrative_context?.scene"></div>
    <div class="text-sm text-gray-400" x-text="activeShot?.narrative_context?.emotion_curve"></div>
  </div>

  <!-- Prompts -->
  <div class="space-y-2">
    <h3 class="text-xs font-semibold uppercase text-gray-500">Prompts</h3>
    <p class="text-xs text-gray-400 line-clamp-3" x-text="activeShot?.visual_bundle?.prompt"></p>
  </div>

  <!-- Decision Buttons -->
  <div class="space-y-2 pt-4">
    <button @click="approve()" class="w-full py-2 bg-green-600 hover:bg-green-500 text-white rounded font-semibold">
      Approve <kbd class="ml-2 text-xs bg-green-800 px-1 rounded">Y</kbd>
    </button>
    <button @click="reject()" class="w-full py-2 bg-red-600 hover:bg-red-500 text-white rounded font-semibold">
      Reject <kbd class="ml-2 text-xs bg-red-800 px-1 rounded">N</kbd>
    </button>
  </div>
</div>
```

## 4. Interaction States

### Keyboard Navigation
| Key | Action | Visual Feedback |
|-----|--------|-----------------|
| Space | Play/Pause video | Play/pause icon overlay 1s |
| Y | Approve active shot | Green flash on card, slide-out animation |
| N | Reject active shot | Red flash, reject dialog if reason required |
| J | Next shot | Scroll queue, highlight next |
| K | Previous shot | Scroll queue, highlight previous |
| D | Toggle diff/comparison | Center panel splits to 2-column |
| B | Enter/exit batch mode | Batch toolbar appears, shift+click enabled |
| G | Toggle policy panel | Right-side drawer slides in |
| L | Toggle log panel | Overlay with audit entries |
| Esc | Exit comparison/batch/policy | Return to single-shot view |

### Batch Mode
- Press B → batch toolbar appears at top of queue panel
- Ctrl+click shots to add to selection (yellow ring)
- Shift+click for range select
- Toolbar: "Approve N", "Reject N", "Cancel"

### SSE Real-time Updates
- New shot cards appear in queue with highlight animation (`animate-pulse` 2s)
- Status changes update card styling without full reload
- Event types: `shot_card_created`, `shot_card_updated`, `shot_card_routed`

## 5. Responsive Behavior

- **1280px+:** Full 3-column layout
- **1024-1279px:** Left panel auto-collapsed to icons, center + right visible
- **< 1024px:** Redirect to mobile PWA (Phase 21) — desktop workstation not usable

## 6. Accessibility

- All keyboard shortcuts have button equivalents visible on screen
- `aria-label` on all interactive elements
- Focus management: after action (approve/reject), focus moves to next shot
- High contrast mode: `bg-gray-950` + `text-gray-100` for panels
