// ── UI Primitives Library ───────────────────────────────────────────────────
// Central barrel export. Import shared components and utilities from here:
//   import { Modal, DataTable, StatCard, DivBadge } from './ui'

// Components
export { default as Modal, ModalFooter } from './Modal.jsx'
export { default as ConfirmModal } from './ConfirmModal.jsx'
export { StatusBadge, DivBadge, DivText, Pill } from './Badge.jsx'
export { default as StatCard } from './StatCard.jsx'
export { default as DataTable } from './DataTable.jsx'
export { default as EmptyState } from './EmptyState.jsx'
export { default as PageHeader } from './PageHeader.jsx'
export { SkeletonLine, SkeletonCard, SkeletonTable, SkeletonStatCards } from './Skeleton.jsx'
export { default as InfoTip } from './InfoTip.jsx'
export { default as Breadcrumb } from './Breadcrumb.jsx'
export { default as DivergenceDotPlot } from './DivergenceDotPlot.jsx'

// Style utilities
export {
  pageStyle, pageHeader, toolbar, panel, accentPanel, panelHeader,
  statCard, tableStyles, btnPrimary, btnSecondary, btnDanger,
  modalStyles, formStyles, emptyState,
  statusBadge, divBadgeStyle, filterChip,
  branchColors, branchChip, accentRow,
  hoverHandlers, hoverBorderHandlers,
} from './styles.js'

// Constants & helpers
export {
  MODEL_PRICING, MODELS, modelCostPer1M, branchCost,
  divColor, divBg, choiceColor, choiceBg, CHOICE_COLORS,
  STATUS_MAP, fmtDate, fmtDateLong, fmtDateTime, formatNum,
} from './constants.js'
