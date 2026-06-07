# Forkmark v0.1.1 — UX Improvement Tasks

Based on non-technical user review feedback. All tasks are UI/copy changes — none require removing features, weakening auth, or adding backend complexity.

---

## P1 — High Impact, Do First

These fix the biggest blockers for non-technical users landing on the platform.

### 1. Rename sidebar items and add hover tooltips
**Effort:** ~2 hrs | **Scope:** Sidebar.jsx only

The sidebar uses developer jargon that assumes familiarity with the data model. Proposed renames:

| Current | Proposed | Why |
|---------|----------|-----|
| Workflow Runner | Run Comparison | Describes the action, not the architecture |
| Eval Runs | Comparison Batches *or* Results | "Eval Run" is internal terminology |
| Decision History | Past Verdicts | Plainer language |
| Test Sets | Test Inputs *or* Test Cases | Less abstract |

Add a one-sentence hover tooltip to every sidebar item (e.g., *"Run a side-by-side comparison of two model configurations"*). The collapsed-sidebar tooltip already exists — extend the pattern to expanded mode with slightly longer descriptions.

---

### 2. Add "Recommended" badge and progressive disclosure to Settings
**Effort:** ~3 hrs | **Scope:** Settings components only

The Divergence Scorer section exposes raw technical options ("TF-IDF cosine + SequenceMatcher") with no guidance. Changes:

- Add a **Recommended** badge to the "Auto" option
- Replace technical descriptions with a plain-language comparison table:
  - *Fast & Free* → Auto
  - *Most Accurate* → LLM Judge (~$0.001 per comparison)
- Collapse technical details (`pip install` notes, model names, scorer internals) behind an expandable **Advanced** section
- Apply the same pattern to other settings that expose technical internals

---

### 3. Split QuickStart into No-code and Developer tracks
**Effort:** ~4 hrs | **Scope:** QuickStart.jsx

The current QuickStart jumps straight to "Generate API Key" and "Install the SDK." Non-technical users don't need either of those. Redesign with two tabs:

**No-code track (default):**
1. Try a Demo → loads demo data
2. Run a Comparison → opens Workflow Runner
3. Review the Results → comparison view
4. See Your Dashboard → populated dashboard

**Developer track:**
1. Generate API Key
2. Install SDK
3. Instrument Workflow
4. View Results

---

### 4. Fix Review Queue to default to all pending comparisons
**Effort:** ~3 hrs | **Scope:** ReviewQueue.jsx + minor backend query param

The current "enter your Reviewer ID" pattern shows a blank screen until you type an exact string match. Changes:

- Default to showing ALL pending/undecided comparisons
- Add an optional "Filter by reviewer" input that narrows the list
- Auto-populate reviewer name from localStorage-persisted display name (already in Settings)
- If no name is set, show a friendly inline "What's your name?" prompt (not a blocking modal)

---

## P2 — Polish, Do Next

These improve the experience for users who've gotten past the initial hurdles.

### 5. Add info-icon tooltips to forms and technical fields
**Effort:** ~4 hrs | **Scope:** New InfoTip component + multiple forms

Build a reusable `<InfoTip text="..." />` component (small (i) icon with hover/click tooltip). Apply to:

- **Eval Run creation:** "Branch A (Baseline)" → *"Your current model. This is what you're comparing against."* / "Temperature" → *"Controls randomness. Lower = more consistent, Higher = more creative. 0.3 is a safe default."*
- **Workflow Runner:** System Prompt vs User Prompt distinction
- **Settings:** Divergence scorer options, storage engine, background workers

One-line additions that make a large difference for non-technical users.

---

### 6. Make error messages actionable with navigation links
**Effort:** ~3 hrs | **Scope:** Multiple components

Current error messages are plain strings with no guidance. Changes:

| Current | Proposed |
|---------|----------|
| "No OpenAI API key configured" | "No API key configured. [Go to Settings →] to add your OpenAI or OpenRouter key." |
| "Eval run not found" | "This comparison batch wasn't found. It may have been deleted. [← Back to Results]" |
| Generic HTTP errors | "Something went wrong. [Try again] or [report this issue]." |

Build a small `<ActionError message="..." action="..." link="..." />` helper component and apply across the runner, settings, comparison loading, and API key validation flows.

---

### 7. Add guided first-run onboarding flow
**Effort:** ~6 hrs | **Scope:** New OnboardingFlow component + App.jsx

Detect first-run state (no workflows, no eval runs) and present a guided path:

1. **Try a Demo** → loads demo data
2. **Run Your First Comparison** → opens Workflow Runner with pre-filled example
3. **Review the Results** → navigates to the comparison view
4. **See Your Dashboard** → shows the populated dashboard

Show a subtle progress stepper in the sidebar or top bar that persists until dismissed. Store completion state in localStorage.

---

## Summary

| # | Task | Priority | Effort | Backend changes? |
|---|------|----------|--------|-----------------|
| 1 | Rename sidebar + tooltips | P1 | 2 hrs | No |
| 2 | Settings progressive disclosure | P1 | 3 hrs | No |
| 3 | Split QuickStart tracks | P1 | 4 hrs | No |
| 4 | Review Queue default view | P1 | 3 hrs | 1 query param |
| 5 | Info-icon tooltips on forms | P2 | 4 hrs | No |
| 6 | Actionable error messages | P2 | 3 hrs | No |
| 7 | First-run onboarding flow | P2 | 6 hrs | No |
| | **Total** | | **25 hrs** | |

All changes are frontend-only (except one minor backend query param change for the Review Queue). No features removed, no security changes, no performance impact.
