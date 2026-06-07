import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Modal, { ModalFooter } from '../components/ui/Modal.jsx'
import ConfirmModal from '../components/ui/ConfirmModal.jsx'
import { StatusBadge, DivBadge, DivText, Pill } from '../components/ui/Badge.jsx'
import StatCard from '../components/ui/StatCard.jsx'
import EmptyState from '../components/ui/EmptyState.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'

// ── Modal ──────────────────────────────────────────────────────────────────

describe('Modal', () => {
  it('renders with title and children', () => {
    render(
      <Modal onClose={() => {}} title="Test Modal">
        <p>Modal content</p>
      </Modal>
    )
    expect(screen.getByText('Test Modal')).toBeInTheDocument()
    expect(screen.getByText('Modal content')).toBeInTheDocument()
  })

  it('has role="dialog" and aria-modal', () => {
    render(
      <Modal onClose={() => {}} title="Dialog Test">
        <p>Content</p>
      </Modal>
    )
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('has aria-labelledby pointing to title', () => {
    render(
      <Modal onClose={() => {}} title="Labeled Modal">
        <p>Content</p>
      </Modal>
    )
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-labelledby', 'modal-title')
    expect(screen.getByText('Labeled Modal')).toHaveAttribute('id', 'modal-title')
  })

  it('calls onClose on Escape', () => {
    const onClose = vi.fn()
    render(
      <Modal onClose={onClose} title="Escape Test">
        <p>Content</p>
      </Modal>
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not call onClose on Escape when closable=false', () => {
    const onClose = vi.fn()
    render(
      <Modal onClose={onClose} title="No Close" closable={false}>
        <p>Content</p>
      </Modal>
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
  })

  it('renders subtitle when provided', () => {
    render(
      <Modal onClose={() => {}} title="Title" subtitle="Subtitle text">
        <p>Content</p>
      </Modal>
    )
    expect(screen.getByText('Subtitle text')).toBeInTheDocument()
  })
})

// ── ModalFooter ────────────────────────────────────────────────────────────

describe('ModalFooter', () => {
  it('renders cancel and submit buttons', () => {
    const onCancel = vi.fn()
    const onSubmit = vi.fn()
    render(<ModalFooter onCancel={onCancel} onSubmit={onSubmit} submitLabel="Save" />)

    expect(screen.getByText('Cancel')).toBeInTheDocument()
    expect(screen.getByText('Save')).toBeInTheDocument()
  })

  it('disables submit when disabled=true', () => {
    render(<ModalFooter onSubmit={() => {}} submitLabel="Go" disabled={true} />)
    expect(screen.getByText('Go')).toBeDisabled()
  })

  it('shows loading state', () => {
    render(<ModalFooter onSubmit={() => {}} submitLabel="Go" loading={true} />)
    expect(screen.getByText('...')).toBeInTheDocument()
  })
})

// ── ConfirmModal ───────────────────────────────────────────────────────────

describe('ConfirmModal', () => {
  it('renders title and message', () => {
    render(
      <ConfirmModal
        title="Delete Item"
        message="Are you sure?"
        confirmLabel="Delete"
        onConfirm={() => {}}
        onClose={() => {}}
      />
    )
    expect(screen.getByText('Delete Item')).toBeInTheDocument()
    expect(screen.getByText('Are you sure?')).toBeInTheDocument()
  })

  it('calls onConfirm and onClose when confirmed', async () => {
    const onConfirm = vi.fn()
    const onClose = vi.fn()
    render(
      <ConfirmModal
        title="Confirm"
        message="Sure?"
        confirmLabel="Yes"
        onConfirm={onConfirm}
        onClose={onClose}
      />
    )
    const user = userEvent.setup()
    await user.click(screen.getByText('Yes'))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when cancelled', async () => {
    const onClose = vi.fn()
    render(
      <ConfirmModal
        title="Confirm"
        message="Sure?"
        onConfirm={() => {}}
        onClose={onClose}
      />
    )
    const user = userEvent.setup()
    await user.click(screen.getByText('Cancel'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

// ── Badge components ───────────────────────────────────────────────────────

describe('StatusBadge', () => {
  it('renders status text', () => {
    render(<StatusBadge status="completed" />)
    expect(screen.getByText('completed')).toBeInTheDocument()
  })

  it('renders for all known statuses', () => {
    const { unmount } = render(<StatusBadge status="pending" />)
    expect(screen.getByText('pending')).toBeInTheDocument()
    unmount()

    render(<StatusBadge status="failed" />)
    expect(screen.getByText('failed')).toBeInTheDocument()
  })
})

describe('DivBadge', () => {
  it('renders dash for null score', () => {
    render(<DivBadge score={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders percentage for valid score', () => {
    render(<DivBadge score={0.45} />)
    expect(screen.getByText('45%')).toBeInTheDocument()
  })

  it('renders 0% for zero score', () => {
    render(<DivBadge score={0} />)
    expect(screen.getByText('0%')).toBeInTheDocument()
  })
})

describe('DivText', () => {
  it('renders dash for null', () => {
    render(<DivText score={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders with default prefix', () => {
    render(<DivText score={0.33} />)
    expect(screen.getByText(/Δ.*33%/)).toBeInTheDocument()
  })

  it('renders with custom prefix', () => {
    render(<DivText score={0.5} prefix="Score: " />)
    expect(screen.getByText(/Score:.*50%/)).toBeInTheDocument()
  })
})

describe('Pill', () => {
  it('renders children', () => {
    render(<Pill>Test Pill</Pill>)
    expect(screen.getByText('Test Pill')).toBeInTheDocument()
  })
})

// ── StatCard ───────────────────────────────────────────────────────────────

describe('StatCard', () => {
  it('renders label and value', () => {
    render(<StatCard label="Total Runs" value={42} />)
    expect(screen.getByText('Total Runs')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('shows dash for null value', () => {
    render(<StatCard label="Missing" value={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})

// ── EmptyState ─────────────────────────────────────────────────────────────

describe('EmptyState', () => {
  it('renders heading and body', () => {
    render(<EmptyState heading="No data" body="Try adding some." />)
    expect(screen.getByText('No data')).toBeInTheDocument()
    expect(screen.getByText('Try adding some.')).toBeInTheDocument()
  })

  it('renders icon when provided', () => {
    render(<EmptyState icon="🔍" heading="Search" body="Nothing found." />)
    expect(screen.getByText('🔍')).toBeInTheDocument()
  })

  it('renders action button when provided', async () => {
    const onClick = vi.fn()
    render(<EmptyState heading="Empty" body="." action={{ label: 'Create', onClick }} />)
    const user = userEvent.setup()
    await user.click(screen.getByText('Create'))
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})

// ── PageHeader ─────────────────────────────────────────────────────────────

describe('PageHeader', () => {
  it('renders title and subtitle', () => {
    render(<PageHeader title="Dashboard" subtitle="Overview of all workflows" />)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Overview of all workflows')).toBeInTheDocument()
  })

  it('renders back button when provided', async () => {
    const onBack = vi.fn()
    render(<PageHeader title="Detail" backLabel="← Back" onBack={onBack} />)
    const user = userEvent.setup()
    await user.click(screen.getByText('← Back'))
    expect(onBack).toHaveBeenCalledTimes(1)
  })

  it('renders action button when provided', () => {
    render(<PageHeader title="Keys" action={{ label: '+ New', onClick: () => {} }} />)
    expect(screen.getByText('+ New')).toBeInTheDocument()
  })

  it('does not render back button without onBack', () => {
    render(<PageHeader title="Simple" />)
    expect(screen.queryByText('← Back')).not.toBeInTheDocument()
  })
})
