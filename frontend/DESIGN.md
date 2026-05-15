---
title: SeaLAI Frontend Design System
version: 1.0.1
product: SeaLAI
scope: frontend
status: binding
owner: SeaLAI
tokens:
  colors:
    brand:
      primary:
        value: "#041E49"
        usage: "Primary actions, active states, key highlights, timeline active step"
      primary_hover:
        value: "#082A5F"
        usage: "Hover state for primary actions"
      primary_soft:
        value: "#EAF2FF"
        usage: "Soft emphasis background for highlighted informational UI"
    surface:
      app:
        value: "#F5F5F7"
        usage: "Global app background"
      panel:
        value: "#FFFFFF"
        usage: "Primary cards, chat surface, cockpit cards"
      panel_subtle:
        value: "#FAFAFB"
        usage: "Sub-panels, secondary containers"
      panel_muted:
        value: "#F0F2F5"
        usage: "Muted grouped sections, skeleton regions"
    text:
      primary:
        value: "#111827"
        usage: "Primary text"
      secondary:
        value: "#4B5563"
        usage: "Secondary text"
      tertiary:
        value: "#6B7280"
        usage: "Helper text, inactive labels"
      inverse:
        value: "#FFFFFF"
        usage: "Text on strong brand backgrounds"
    border:
      default:
        value: "#E5E7EB"
        usage: "Default card and control borders"
      strong:
        value: "#D1D5DB"
        usage: "Table dividers, stronger boundaries"
      active:
        value: "#041E49"
        usage: "Active tabs, active outlines, focused cards"
    state:
      success:
        value: "#15803D"
        usage: "Confirmed values, positive checks, completed steps"
      success_soft:
        value: "#EAF7EE"
        usage: "Soft success background"
      warning:
        value: "#B45309"
        usage: "Important but non-critical warnings"
      warning_soft:
        value: "#FFF4E5"
        usage: "Soft warning background"
      danger:
        value: "#DC2626"
        usage: "Critical blockers, missing required values"
      danger_soft:
        value: "#FDECEC"
        usage: "Soft critical background"
      info:
        value: "#2563EB"
        usage: "Informational badges, helper accents"
      info_soft:
        value: "#EFF6FF"
        usage: "Soft info background"
    material:
      medium:
        value: "#7C3AED"
        usage: "Medium intelligence emphasis and medium labels"
      calculations:
        value: "#2563EB"
        usage: "Calculation emphasis"
      open_points:
        value: "#D97706"
        usage: "Open points and next-step emphasis"
      application:
        value: "#0F766E"
        usage: "Application/machine intelligence emphasis"
  typography:
    font_family:
      base:
        value: "Inter, ui-sans-serif, system-ui, sans-serif"
        usage: "Entire application"
    font_size:
      xs:
        value: "12px"
      sm:
        value: "14px"
      md:
        value: "16px"
      lg:
        value: "18px"
      xl:
        value: "22px"
      xxl:
        value: "30px"
    line_height:
      tight:
        value: "1.25"
      normal:
        value: "1.5"
      relaxed:
        value: "1.65"
    font_weight:
      regular:
        value: "400"
      medium:
        value: "500"
      semibold:
        value: "600"
      bold:
        value: "700"
  rounded:
    sm:
      value: "10px"
      usage: "Small buttons, pills, chips"
    md:
      value: "14px"
      usage: "Inputs, tabs, secondary cards"
    lg:
      value: "18px"
      usage: "Primary cards"
    xl:
      value: "24px"
      usage: "Hero-level surfaces or major panels"
  spacing:
    xxs:
      value: "4px"
    xs:
      value: "8px"
    sm:
      value: "12px"
    md:
      value: "16px"
    lg:
      value: "20px"
    xl:
      value: "24px"
    xxl:
      value: "32px"
    xxxl:
      value: "40px"
  elevation:
    card:
      value: "0 4px 18px rgba(15,23,42,0.06)"
      usage: "Standard panel elevation"
    hover:
      value: "0 8px 24px rgba(15,23,42,0.10)"
      usage: "Interactive hover elevation for cards/buttons"
    overlay:
      value: "0 20px 60px rgba(15,23,42,0.18)"
      usage: "Drawers and overlays"
  motion:
    fast:
      value: "150ms"
      usage: "Micro interactions"
    normal:
      value: "200ms"
      usage: "Default transitions"
    slow:
      value: "250ms"
      usage: "Mode transitions"
    easing:
      value: "cubic-bezier(0.22, 1, 0.36, 1)"
      usage: "Default UI easing"
components:
  workspace:
    layout_ratio_desktop:
      value: "62 / 38"
      usage: "Chat to cockpit split on large screens"
    layout_ratio_wide:
      value: "60 / 40"
      usage: "Fallback split on standard desktop"
  cards:
    primary_radius:
      value: "{rounded.lg}"
    border:
      value: "1px solid {colors.border.default}"
    shadow:
      value: "{elevation.card}"
  tabs:
    active_background:
      value: "{colors.brand.primary}"
    active_text:
      value: "{colors.text.inverse}"
    inactive_background:
      value: "{colors.surface.panel_subtle}"
    inactive_text:
      value: "{colors.text.secondary}"
  timeline:
    active_step:
      value: "{colors.brand.primary}"
    completed_step:
      value: "{colors.state.success}"
    inactive_step:
      value: "{colors.border.strong}"
---

# Overview

SeaLAI is not a generic dashboard and not a generic chatbot.  
SeaLAI is a **conversation-first engineering workspace**.

The UI must always feel like:

- one stable professional product surface
- one visible expert speaker
- one adaptive engineering workspace
- one continuous technical conversation

The frontend must never feel like:
- a chat app plus a second unrelated dashboard
- a dense BI tool with a chat panel attached
- a sequence of disconnected full-page modes
- a visual experiment that changes structure every turn

## Core UI Intent

SeaLAI must combine:

1. **Human conversation**
   - calm
   - professional
   - precise
   - non-robotic

2. **Engineering orientation**
   - visible technical path
   - visible current step
   - visible captured values
   - visible missing information
   - visible important computed indicators

3. **Controlled adaptivity**
   - the workspace can change its focus
   - the overall spatial frame must remain stable
   - context must not be lost when the user asks a side question

---

# Product Interaction Model

## Primary principle

**Conversation first. Workspace second. Dashboard never first.**

The left side is the primary interaction surface.  
The right side is a technical cockpit that supports the active conversation.

## Stable frame, adaptive content

SeaLAI must use a **stable frame** with **adaptive content**.

That means:

- the page structure stays stable
- the user learns where information lives
- only the content inside the cockpit slots changes
- full-page visual mode breaks are forbidden

## One visible speaker

Only the chat speaks.

The cockpit:
- summarizes
- structures
- prioritizes
- visualizes
- supports
- never replaces the conversation

Do not duplicate large blocks of chat content inside cockpit cards.

---

# Layout

## Global page structure

The main workspace has three layers:

### 1. Top header
Contains:
- SeaLAI branding
- workspace title / product title
- case or search identifier
- status badge (for example governed)
- user identity / role area

The header must be clean and quiet.  
No dense navigation bar feeling.

### 2. Top timeline / phase rail
A horizontal progress timeline sits below the header.

It shows:
- current phase
- completed phases
- future phases
- active step

The timeline provides orientation only.  
It must not dominate vertical space.

### 3. Main workspace body
Three-column logic:

- **left utility rail**
- **main chat column**
- **right cockpit column**

## Desktop ratios

Use:
- wide desktop: `62 / 38`
- standard desktop fallback: `60 / 40`

The chat must always remain visually dominant.

## Left utility rail

A thin vertical rail sits left of the chat.

Purpose:
- expand on demand
- show conversation utilities
- provide history jump points
- surface notes or related context
- support, not compete with chat

The rail is collapsed by default.

The rail must not:
- become a second dashboard
- duplicate current chat messages
- become a large permanent sidebar on standard desktop

## Main chat column

The chat column must include:
- section title
- optional lightweight chat toolbar
- scrollable message area
- fixed composer at bottom

The composer must stay visually anchored.

## Right cockpit column

The right column is the engineering workspace.

It must always feel:
- structured
- useful
- calm
- not overloaded
- technically serious

---

# Workspace Modes

SeaLAI uses one stable page shell with adaptive cockpit modes.

## Mode 1 — Case Analysis

Purpose:
- ongoing needs analysis
- parameter capture
- technical clarification
- guided qualification

Right cockpit cards:
1. Parameter & Application
2. Medium Intelligence
3. Calculations
4. Open Points & Next Step

## Mode 2 — Knowledge Compare

Purpose:
- compare materials or options
- explain tradeoffs
- help the user reason

Right cockpit cards:
1. Comparison table
2. Short conclusion
3. Important decision criteria
4. Sources / data basis

## Mode 3 — Knowledge Deep Dive

Purpose:
- deep material or topic exploration
- detailed profile and limits
- richer informational context

Right cockpit cards:
1. Material profile
2. Properties
3. Typical applications & limits
4. Deep notes / sources

## Mode transition rule

Mode transitions must be:
- smooth
- contextual
- in-place
- non-disruptive

Mode transitions must never:
- reload the page
- destroy the perceived continuity of the case
- remove all case context without replacement

## Persistent context header inside cockpit

The cockpit must contain a small persistent context header showing:
- case ID or search ID
- current path
- current application / machine
- current medium
- current phase label
- completeness signal if available

This context header stays visible across cockpit mode switches.

---

# Visual Hierarchy

## Hierarchy order

1. Current chat turn and conversation
2. Current technical phase / timeline
3. Current cockpit focus
4. Supporting details
5. Deep details / sources

## What must always be visible in case analysis

At default density, the user must be able to see:
- current path
- application / machine
- core captured parameters
- current medium classification
- key engineering calculations
- missing critical inputs
- next action

## What should be secondary or expandable

These should not dominate default view:
- raw provenance details
- trace/debug internals
- long explanatory essays
- full historical comparisons
- full calculation breakdowns
- raw routing logic

---

# Cards

## General card rules

All cockpit cards must:
- use stable borders
- use moderate elevation
- use generous inner spacing
- have clear titles
- have a visible information hierarchy
- support compact and expanded content states

Cards must not:
- feel decorative
- feel overly glossy
- rely on excessive gradients
- use large hero-like visual noise

## Card title styling

Card titles must:
- be semibold
- be concise
- use iconography only when helpful
- not rely on icon-only meaning

## Card corner radius

Use primary card radius:
- `{rounded.lg}`

## Card actions

Use quiet actions:
- overflow menu
- detail disclosure
- expand view
- “show more” affordances

Avoid loud UI chrome.

---

# Case Analysis Cards

## 1. Parameter & Application

This is the most important card in case analysis.

### Always show
- active technical path
- application / machine
- path confirmation status
- core parameter list
- per-field status

### Structure
- header
- path tabs
- application row
- parameter table/list
- optional “show all parameters” action

### Path tabs
Tabs can represent:
- Rotierend
- RWDR
- Hydraulik
- Flachdichtung
- Statisch
- other valid path families

Tabs must:
- indicate current working path
- reveal path-specific parameters
- be visually stable
- not mutate business state by UI click alone

### Field status system
Use a clear status vocabulary:
- confirmed
- inferred
- recommended
- optional
- missing

Missing required values must be visually distinct but not alarmist.

### Application / machine emphasis
Application intelligence is part of this card.  
It must be visible because application context changes parameter relevance.

Examples:
- Rührwerk
- Getriebe
- Kreiselpumpe
- Hydraulikzylinder
- Flanschverbindung

## 2. Medium Intelligence

This card is always visible in case analysis.

### Show
- recognized medium
- medium status / confidence
- classification
- relevant properties
- open medium questions

### Style
Use medium color accent sparingly.
Do not make the card look like a chemistry portal.

### Content style
Focus on selection relevance:
- chemical resistance
- thermal relevance
- viscosity or abrasivity relevance
- uncertainty points

## 3. Calculations

This card is engineering-critical.

### Show
- key selection-relevant values
- unit and status
- current/stale/blocked state
- whether inputs are sufficient

### Typical contents
- Umlaufgeschwindigkeit
- PV
- friction heat estimate
- temperature delta estimate
- other path-relevant indicators

### Calculation rule
The UI must visually imply:
- structured engineering value
- not LLM opinion

Values should feel authoritative and sober.

## 4. Open Points & Next Step

This card must always exist in case analysis.

### Show
- prioritized missing values
- criticality
- next recommended action

### Goal
The user should always know:
- what is missing
- why it matters
- what to do next

This card is the bridge between cockpit state and conversation flow.

---

# Knowledge Compare Cards

## Comparison Table

Must be the dominant card in comparison mode.

### Show
- criteria rows
- compared materials/options
- advantage summary by row where helpful

### Rules
- keep rows scannable
- avoid giant text blocks inside the table
- provide short labels, not essay cells

## Short Conclusion

Summarize the comparison in a clear, decision-oriented way.

### Good output
- where one option is stronger
- where the other option is stronger
- what decides the selection

## Important Decision Criteria

Surface the factors that matter most for choosing:
- medium
- temperature
- dynamics
- compliance
- cost
- availability

## Sources / Data Basis

Display source quality clearly:
- datasheet
- material knowledge
- norm hint
- internal knowledge basis

Sources should be compact, linkable, and secondary.

---

# Knowledge Deep Dive Cards

## Material Profile

The anchor card of deep-dive mode.

### Show
- material name
- class
- short definition
- compact facts
- badges if genuinely useful

## Properties

Use concise visual indicators:
- bars
- ratings
- bounded scales
- short labels

Do not overcomplicate with scientific plotting in default view.

## Typical Applications & Limits

This card is critical for usability because it prevents abstract material descriptions from floating without context.

### Show
- common applications
- common fit areas
- known boundaries or caution points

## Deep Notes / Sources

Longer notes and source references belong here.

---

# Timeline

## Purpose

The timeline gives the user a sense of place and progress.

## Rules

- place below the main header
- keep vertical height low
- use strong distinction for active step
- allow completed steps to feel calm, not flashy
- future steps should be visible but muted

## For case analysis
Typical steps:
- Problemverständnis
- Pfadwahl
- Parameterklärung
- Technische Einordnung
- Empfehlung
- RFQ-Reife

## For compare or deep dive
Timeline labels can adapt, but the component must remain visually consistent.

---

# Utility Rail

## Default behavior

Collapsed by default.

## Purpose

The rail may include:
- history
- notes
- bookmarks
- related documents
- jump links

## UX rule

The rail is utility, not primary content.

It may expand on demand, but must not:
- permanently steal major width on normal desktop
- become visually louder than the chat
- duplicate the main cockpit

---

# Chat

## Message tone in UI

The chat UI must feel:
- calm
- technical
- trustworthy
- enterprise-grade
- not playful

## Message cards

Assistant and user messages should be visually distinct but not gimmicky.

## Content blocks inside chat

Allow lightweight inline structured blocks where valuable, such as:
- selected path
- next key question
- short technical note

Do not turn the chat into a mini-dashboard.

## Composer

The composer must remain fixed at the bottom of the chat column.

It must support:
- normal message entry
- attachments if enabled
- calm action affordances
- no clutter

---

# Motion

## General rule

Motion exists to preserve orientation, not to impress.

## Allowed motion

Use:
- fade
- slight vertical or horizontal translate
- stable height transitions where possible

## Timing

Use:
- fast microinteraction: `{motion.fast}`
- default UI transition: `{motion.normal}`
- cockpit mode switch: `{motion.slow}`

## Forbidden motion

Do not use:
- bounce
- springy exaggerated movement
- large zoom transitions
- parallax
- attention-seeking animation loops

## Mode switching

When the right cockpit changes mode:
- preserve outer shell
- preserve context header
- swap content in place
- avoid full-column flash or collapse

---

# Responsive Behavior

## Large desktop
Use the full split layout:
- utility rail
- chat
- cockpit

## Standard desktop
Keep the same structure with slightly tighter spacing.

## Tablet / small desktop
The cockpit may compress, but the chat remains primary.

## Mobile
Do not try to preserve the full three-column experience.

Use:
- chat-first layout
- cockpit as drawer, segmented panel, or secondary workspace view
- timeline simplified or condensed

---

# Accessibility

## General

SeaLAI must be accessible by default.

### Required
- visible focus states
- keyboard navigation for rail, tabs, and expanders
- sufficient contrast
- semantic headings
- proper table semantics in comparison mode

## Motion accessibility

Respect reduced motion preferences.
If reduced motion is enabled:
- minimize transitions
- preserve structural clarity

## Status colors

Never rely on color alone.
Always pair with:
- text
- icon
- label
- position

---

# Engineering Truth Presentation

## Principle

The cockpit shows structured engineering truth, not probabilistic narrative.

## Therefore

- calculations must feel deterministic
- statuses must be explicit
- proposed/inferred/confirmed must be visually distinct
- unknown and blocked states must be honest

## Do not present as authoritative
- unconfirmed guesses
- unsourced claims
- hidden confidence assumptions

---

# Sources and Provenance

## Default view

Keep sources compact.

## Deep view

Allow deeper inspection when the user asks for it.

## Good labeling examples

- Datenblatt
- Werkstoffwissen
- Normhinweis
- interne Wissensbasis

## Do not expose by default

- raw trace ids
- model names
- prompt internals
- agent orchestration details

---

# Do’s

- Keep the chat visually dominant.
- Keep the cockpit useful and restrained.
- Preserve context during every mode switch.
- Show path, application, medium, and key calculations clearly.
- Use smooth in-place transitions.
- Keep cards scannable.
- Use progressive disclosure for detail.
- Treat the right side as a technical workspace, not a dashboard playground.
- Make engineering status honest and explicit.
- Let the user feel guided, not overwhelmed.

# Don’ts

- Do not build multiple disconnected page experiences.
- Do not replace the chat with a dashboard.
- Do not dump every backend fact into the cockpit.
- Do not duplicate long chat text inside cards.
- Do not let tabs mutate business state directly.
- Do not over-animate cockpit transitions.
- Do not hide critical missing data inside deep drawers.
- Do not make the UI playful or startup-gimmicky.
- Do not render the cockpit as if it were a BI analytics tool.
- Do not let comparison/deep-dive modes erase the active case context.

# Final Design Sentence

SeaLAI must feel like **one calm expert engineering workspace** where the chat leads, the cockpit supports, and the interface adapts intelligently without ever losing spatial or technical clarity.
