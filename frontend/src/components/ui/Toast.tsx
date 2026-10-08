import { useEffect, useState } from 'react'

export type ToastTone = 'info' | 'success' | 'error' | 'loading'

interface ToastProps {
  message: string
  tone?: ToastTone
  /** Auto-hide after ms (0 = stay until cleared). Loading defaults to 0. */
  duration?: number
  onClose?: () => void
}

export function Toast({ message, tone = 'info', duration, onClose }: ToastProps) {
  const hideAfter = duration ?? (tone === 'loading' ? 0 : 3200)

  useEffect(() => {
    if (!message || !hideAfter || !onClose) return
    const timer = window.setTimeout(onClose, hideAfter)
    return () => window.clearTimeout(timer)
  }, [hideAfter, message, onClose])

  if (!message) return null

  return (
    <div className={`toast toast-${tone}`} role="status" aria-live="polite">
      {tone === 'loading' ? <span className="toast-spinner" aria-hidden="true" /> : null}
      <span>{message}</span>
    </div>
  )
}

/** Local toast state helper for pages. */
export function useToast() {
  const [toast, setToast] = useState<{ message: string; tone: ToastTone }>({ message: '', tone: 'info' })

  const show = (message: string, tone: ToastTone = 'info') => {
    setToast({ message, tone })
  }

  const clear = () => setToast({ message: '', tone: 'info' })

  return {
    toast,
    show,
    clear,
    showLoading: (message = 'Loading...') => show(message, 'loading'),
    showSuccess: (message: string) => show(message, 'success'),
    showError: (message: string) => show(message, 'error'),
  }
}
