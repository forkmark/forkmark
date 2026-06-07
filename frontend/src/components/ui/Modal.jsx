import { useEffect, useCallback, useRef } from 'react'
import { modalStyles as S, btnPrimary, btnSecondary } from './styles.js'

/**
 * Shared modal overlay with:
 *   - Escape-to-close
 *   - Click-outside-to-close
 *   - Focus trapping (Tab / Shift+Tab cycle within modal)
 *   - Auto-focus first focusable element
 *   - Restores focus to trigger element on close
 *   - Proper ARIA: role="dialog", aria-modal, aria-labelledby
 */
export default function Modal({ onClose, width = 440, title, subtitle, closable = true, children }) {
  const boxRef = useRef(null)
  const prevFocusRef = useRef(null)

  // Save the element that had focus before modal opened
  useEffect(() => {
    prevFocusRef.current = document.activeElement
    return () => {
      // Restore focus on unmount
      if (prevFocusRef.current && prevFocusRef.current.focus) {
        prevFocusRef.current.focus()
      }
    }
  }, [])

  // Auto-focus first focusable element inside the modal
  useEffect(() => {
    if (!boxRef.current) return
    const focusable = boxRef.current.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
    if (focusable.length > 0) {
      focusable[0].focus()
    } else {
      boxRef.current.focus()
    }
  }, [])

  const handleKey = useCallback(e => {
    if (e.key === 'Escape' && closable) {
      onClose()
      return
    }

    // Focus trap: cycle Tab within modal
    if (e.key === 'Tab' && boxRef.current) {
      const focusable = boxRef.current.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      if (focusable.length === 0) return

      const first = focusable[0]
      const last  = focusable[focusable.length - 1]

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault()
          last.focus()
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
  }, [onClose, closable])

  useEffect(() => {
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [handleKey])

  const titleId = title ? 'modal-title' : undefined

  return (
    <div
      style={S.overlay}
      onClick={closable ? onClose : undefined}
      role="presentation"
    >
      <div
        ref={boxRef}
        style={S.box(width)}
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        {title && <div id={titleId} style={S.title}>{title}</div>}
        {subtitle && <div style={S.subtitle}>{subtitle}</div>}
        {children}
      </div>
    </div>
  )
}

/** Standard modal footer with Cancel + primary action */
export function ModalFooter({ onCancel, onSubmit, submitLabel = 'Save', loading = false, disabled = false }) {
  return (
    <div style={S.footer}>
      {onCancel && (
        <button type="button" style={btnSecondary} onClick={onCancel} aria-label="Cancel">
          Cancel
        </button>
      )}
      {onSubmit && (
        <button
          type="submit"
          style={{ ...btnPrimary, fontSize: 13, padding: '8px 16px', opacity: disabled ? 0.5 : 1 }}
          onClick={onSubmit}
          disabled={loading || disabled}
          aria-busy={loading}
        >
          {loading ? '...' : submitLabel}
        </button>
      )}
    </div>
  )
}
