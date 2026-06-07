import Modal from './Modal.jsx'

const S = {
  body: { fontSize: 13, color: 'var(--muted)', marginBottom: 20, lineHeight: 1.5 },
  foot: { display: 'flex', gap: 8, justifyContent: 'flex-end' },
  cancel: { fontSize: 13, padding: '7px 16px', background: 'transparent', color: 'var(--muted)', border: '1px solid var(--border)', borderRadius: 5, cursor: 'pointer' },
  confirm: (variant) => ({
    fontSize: 13, padding: '7px 16px', border: 'none', borderRadius: 5, fontWeight: 700, cursor: 'pointer',
    ...(variant === 'danger'
      ? { background: 'var(--red)', color: '#fff' }
      : { background: 'var(--accent)', color: 'var(--bg)' }),
  }),
}

/**
 * Reusable confirmation modal.
 *
 * Props:
 *   title       - header text
 *   message     - body text (can be string or JSX)
 *   confirmLabel- button text (default "Confirm")
 *   variant     - "danger" or "primary" (default "danger")
 *   onConfirm   - called on confirm click
 *   onClose     - called on cancel/close
 */
export default function ConfirmModal({ title, message, confirmLabel = 'Confirm', variant = 'danger', onConfirm, onClose }) {
  return (
    <Modal onClose={onClose} width={360} title={title}>
      <div style={S.body}>{message}</div>
      <div style={S.foot}>
        <button style={S.cancel} onClick={onClose} aria-label="Cancel">Cancel</button>
        <button style={S.confirm(variant)} onClick={() => { onConfirm(); onClose() }} aria-label={confirmLabel}>
          {confirmLabel}
        </button>
      </div>
    </Modal>
  )
}
