# Aerospace Corporate Landing Page

Eine moderne, hochwertige Landingpage im Stil großer Luftfahrt-Unternehmen, gebaut mit **Next.js 16** (App Router) und **Tailwind CSS**.

## 🎯 Übersicht

Diese Landingpage wurde nach den Vorgaben eines Senior Frontend Developers erstellt und bietet:

- **Corporate High-Tech Design** inspiriert von führenden Aerospace-Unternehmen
- **Vollständige Strapi CMS-Vorbereitung** mit Mock-Daten zum Testen
- **Server Components** für optimales Data Fetching
- **Responsive Design** mit Mobile-First Ansatz
- **Moderne Animationen** und Interaktionen

## 📁 Projektstruktur

```
frontend/
├── src/
│   ├── app/
│   │   ├── aerospace/
│   │   │   └── page.tsx          # Hauptseite der Aerospace Landing Page
│   │   ├── layout.tsx             # Root Layout mit Inter Font
│   │   └── ...
│   ├── components/
│   │   ├── AerospaceNav.tsx       # Navigation mit Scroll-Effekt
│   │   ├── AerospaceHero.tsx      # Full-Screen Hero Section
│   │   ├── NewsGrid.tsx           # 3-Spalten News Grid
│   │   └── StatsSection.tsx       # Animierte Statistiken
│   └── lib/
│       └── strapi.ts              # Strapi Integration + Mock-Daten
└── tailwind.config.js             # Tailwind mit Inter Font
```

## 🚀 Komponenten

### 1. **AerospaceNav** - Globale Navigation
- Transparenter Header, der beim Scrollen weiß wird
- Smooth Transitions
- Responsive mit Mobile Menu Button
- Logo links, Navigation rechts

### 2. **AerospaceHero** - Hero Section
- Vollbild-Hintergrundbild mit Gradient-Overlay
- Eyebrow Text, Headline, Description
- Call-to-Action Button (unten links positioniert)
- Scroll-Indikator mit Animation

### 3. **NewsGrid** - Latest News
- 3-Spalten Grid Layout (responsive)
- Bild oben, Datum, Headline, Excerpt
- "Read more" Links
- Hover-Effekte auf Karten und Bildern

### 4. **StatsSection** - Unternehmensstatistiken
- 4-Spalten Grid mit großen Zahlen
- **Animierte Counter** die beim Scrollen hochzählen
- Intersection Observer für Performance
- Unterstützt Prefix/Suffix (z.B. "$2.8B")

## 🎨 Design-System

### Farbschema
- **Primärfarbe**: Deep Blue (`#0f172a` - Slate-900)
- **Akzentfarbe**: Blue-600 für CTAs und Links
- **Hintergründe**: Weiß, Gray-50, Slate-900
- **Text**: Slate-900 (dunkel), White (auf dunklem BG)

### Typografie
- **Schriftart**: Inter (Google Fonts)
- **Headings**: Bold, große Größen (4xl-7xl)
- **Body**: Regular, optimale Lesbarkeit
- **Tracking**: Tight für Headlines, Wide für Eyebrows

### Spacing & Layout
- **Max-Width**: 7xl (1280px) für Content
- **Padding**: Konsistent 6/8 (24px/32px)
- **Gaps**: 8 (32px) für Grids
- **White Space**: Großzügig für "luftiges" Gefühl

## 📊 Strapi CMS Integration

Die Datei `src/lib/strapi.ts` enthält:

### Mock-Daten Funktionen (zum Testen)
```typescript
getNavigationItems()    // Navigation Menü
getAerospaceHero()      // Hero Section Daten
getLatestNews()         // News Artikel (3 Stück)
getCompanyStats()       // Unternehmensstatistiken (4 Stück)
```

### Typen
```typescript
NavigationItem  // { id, label, href }
NewsArticle     // { id, title, excerpt, publishedDate, imageUrl, ... }
CompanyStat     // { id, label, value, prefix?, suffix? }
```

### Migration zu echtem Strapi
1. Ersetze die Mock-Return-Werte durch echte `fetch()` Calls
2. Nutze die bestehende `unwrapAttributes()` Funktion für v4/v5 Kompatibilität
3. Passe die Typen an dein Strapi Content-Type Schema an

## 🔧 Verwendung

### Aerospace Landing Page aufrufen

Die Landingpage ist unter der Route `/aerospace` verfügbar:

```bash
npm run dev
```

Dann öffne: `http://localhost:3000/aerospace`

### Daten anpassen

Bearbeite `src/lib/strapi.ts` und ändere die Mock-Daten in:
- `getAerospaceHero()` - Hero Text und Bild
- `getLatestNews()` - News Artikel
- `getCompanyStats()` - Statistiken
- `getNavigationItems()` - Menüpunkte

### Komponenten wiederverwenden

Alle Komponenten sind modular und können einzeln importiert werden:

```tsx
import AerospaceNav from "@/components/AerospaceNav";
import AerospaceHero from "@/components/AerospaceHero";
import NewsGrid from "@/components/NewsGrid";
import StatsSection from "@/components/StatsSection";
```

## 📱 Responsive Breakpoints

- **Mobile**: < 768px (1 Spalte)
- **Tablet**: 768px - 1024px (2 Spalten)
- **Desktop**: > 1024px (3-4 Spalten)

Alle Komponenten nutzen Tailwind's responsive Utilities (`md:`, `lg:`).

## ⚡ Performance Features

- **Server Components** für Data Fetching (Next.js 16)
- **Image Optimization** via Next.js Image (kann aktiviert werden)
- **Intersection Observer** für Stats Animation (lädt nur wenn sichtbar)
- **CSS Transitions** statt JavaScript Animations
- **Lazy Loading** für Bilder (Browser-nativ)

## 🎯 Nächste Schritte

1. **Strapi Backend verbinden**
   - Erstelle Content-Types in Strapi
   - Ersetze Mock-Funktionen mit echten API Calls
   - Konfiguriere `NEXT_PUBLIC_STRAPI_URL`

2. **Weitere Sektionen hinzufügen**
   - Products/Services Grid
   - Team Section
   - Contact Form
   - Footer mit Links

3. **SEO optimieren**
   - Metadata in `page.tsx` hinzufügen
   - Structured Data (JSON-LD)
   - Open Graph Images

4. **Animationen erweitern**
   - Scroll-triggered Animations (Framer Motion)
   - Parallax Effects
   - Micro-Interactions

## 📝 Rechtliche Hinweise

- ✅ Keine echten Markennamen verwendet
- ✅ "Aerospace Corp" als Platzhalter
- ✅ Eigener Tailwind Code (kein Copy-Paste)
- ✅ Placeholder-Bilder von picsum.photos

## 🛠️ Technologie-Stack

- **Framework**: Next.js 16.0.3 (App Router)
- **React**: 19.2.0
- **Styling**: Tailwind CSS 3.3.3
- **Fonts**: Inter (Google Fonts)
- **TypeScript**: 5.4.0
- **CMS**: Strapi (vorbereitet)

---

**Erstellt von**: Senior Frontend Developer  
**Datum**: 2025-11-19  
**Version**: 1.0.0
