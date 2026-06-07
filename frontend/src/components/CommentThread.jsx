import { useState, useEffect, useCallback } from 'react'
import { api, dispatchApiError, getReviewerId } from '../api.js'
import { btnPrimary, btnSecondary } from './ui'

const S = {
  wrap:     { marginTop: 16 },
  header:   { fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 10,
              display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  count:    { fontSize: 11, color: 'var(--muted)', fontWeight: 400 },
  list:     { display: 'flex', flexDirection: 'column', gap: 8 },
  comment:  (isReply) => ({
    background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6,
    padding: '10px 12px', marginLeft: isReply ? 24 : 0,
  }),
  cHeader:  { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 },
  author:   { fontSize: 12, fontWeight: 600, color: 'var(--accent)' },
  time:     { fontSize: 10, color: 'var(--muted)' },
  body:     { fontSize: 12, lineHeight: 1.5, color: 'var(--text)', whiteSpace: 'pre-wrap' },
  actions:  { display: 'flex', gap: 8, marginTop: 6 },
  actBtn:   { fontSize: 10, background: 'none', border: 'none', color: 'var(--muted)',
              cursor: 'pointer', padding: 0 },
  resolved: { fontSize: 10, color: 'var(--green)', fontWeight: 600 },

  // New comment form
  form:     { marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 },
  input:    { background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 5,
              color: 'var(--text)', padding: '8px 10px', fontSize: 12, resize: 'vertical',
              minHeight: 50, fontFamily: 'var(--font)', boxSizing: 'border-box', width: '100%' },
  formRow:  { display: 'flex', gap: 6, justifyContent: 'flex-end' },
}

function timeAgo(ts) {
  if (!ts) return ''
  const diff = (Date.now() - new Date(ts).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function CommentItem({ comment, onReply, onResolve, onDelete, replies }) {
  return (
    <>
      <div style={S.comment(!!comment.parent_id)}>
        <div style={S.cHeader}>
          <span style={S.author}>{comment.author_name || comment.author_id || 'Anonymous'}</span>
          <span style={S.time}>{timeAgo(comment.created_at)}</span>
          {comment.is_resolved && <span style={S.resolved}>Resolved</span>}
        </div>
        <div style={S.body}>{comment.body}</div>
        <div style={S.actions}>
          {!comment.parent_id && (
            <button style={S.actBtn} onClick={() => onReply(comment.id)} aria-label="Reply to comment">Reply</button>
          )}
          {!comment.is_resolved && !comment.parent_id && (
            <button style={S.actBtn} onClick={() => onResolve(comment.id)} aria-label="Resolve comment">Resolve</button>
          )}
          <button style={{ ...S.actBtn, color: 'var(--red)' }} onClick={() => onDelete(comment.id)} aria-label="Delete comment">
            Delete
          </button>
        </div>
      </div>
      {replies?.map(r => (
        <CommentItem key={r.id} comment={r} onReply={onReply} onResolve={onResolve}
                     onDelete={onDelete} replies={[]} />
      ))}
    </>
  )
}

export default function CommentThread({ comparisonId }) {
  const [comments, setComments] = useState([])
  const [newBody, setNewBody]   = useState('')
  const [replyTo, setReplyTo]   = useState(null)
  const [loading, setLoading]   = useState(false)

  const load = useCallback(async () => {
    if (!comparisonId) return
    try {
      const data = await api.listComments(comparisonId)
      setComments(data?.comments || data || [])
    } catch (err) {
      // Silently fail — comments are non-critical
    }
  }, [comparisonId])

  useEffect(() => { load() }, [load])

  async function submit() {
    const body = newBody.trim()
    if (!body) return
    setLoading(true)
    try {
      const reviewer = getReviewerId() || 'anonymous'
      await api.addComment(comparisonId, {
        author_id: reviewer,
        author_name: reviewer,
        body,
        ...(replyTo ? { parent_id: replyTo } : {}),
      })
      setNewBody('')
      setReplyTo(null)
      await load()
      window.dispatchEvent(new CustomEvent('fp:apisuccess', { detail: { message: 'Comment added' } }))
    } catch (err) {
      dispatchApiError(err.message || 'Failed to add comment')
    } finally {
      setLoading(false)
    }
  }

  async function handleResolve(commentId) {
    try {
      await api.updateComment(commentId, { is_resolved: true })
      await load()
    } catch (err) {
      dispatchApiError(err.message || 'Failed to resolve comment')
    }
  }

  async function handleDelete(commentId) {
    try {
      await api.deleteComment(commentId)
      await load()
    } catch (err) {
      dispatchApiError(err.message || 'Failed to delete comment')
    }
  }

  // Build threaded structure: top-level comments with their replies
  const topLevel = comments.filter(c => !c.parent_id)
  const replyMap = {}
  for (const c of comments) {
    if (c.parent_id) {
      if (!replyMap[c.parent_id]) replyMap[c.parent_id] = []
      replyMap[c.parent_id].push(c)
    }
  }

  return (
    <div style={S.wrap}>
      <div style={S.header}>
        <span>Comments</span>
        <span style={S.count}>{comments.length}</span>
      </div>

      {topLevel.length > 0 && (
        <div style={S.list}>
          {topLevel.map(c => (
            <CommentItem key={c.id} comment={c} replies={replyMap[c.id] || []}
                         onReply={(id) => setReplyTo(id)}
                         onResolve={handleResolve} onDelete={handleDelete} />
          ))}
        </div>
      )}

      <div style={S.form}>
        {replyTo && (
          <div style={{ fontSize: 11, color: 'var(--accent)', marginBottom: 2 }}>
            Replying to comment
            <button style={{ ...S.actBtn, marginLeft: 6, color: 'var(--muted)' }}
                    onClick={() => setReplyTo(null)}>Cancel</button>
          </div>
        )}
        <textarea style={S.input} value={newBody} onChange={e => setNewBody(e.target.value)}
                  placeholder="Add a comment..." aria-label="Write a comment" />
        <div style={S.formRow}>
          {newBody.trim() && (
            <button style={{ ...btnSecondary, fontSize:11, padding:'5px 12px' }} onClick={() => { setNewBody(''); setReplyTo(null) }}>
              Cancel
            </button>
          )}
          <button style={{ ...btnPrimary, fontSize:11, padding:'5px 14px' }} disabled={!newBody.trim() || loading} onClick={submit}
                  aria-busy={loading}>
            {loading ? 'Posting...' : replyTo ? 'Reply' : 'Comment'}
          </button>
        </div>
      </div>
    </div>
  )
}
