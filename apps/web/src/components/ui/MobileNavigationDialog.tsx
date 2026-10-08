import * as Dialog from '@radix-ui/react-dialog'
import { type ReactElement, type ReactNode } from 'react'

interface MobileNavigationDialogProps {
  children: ReactNode
  contentClassName?: string
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  trigger: ReactElement
}

/**
 * Gaveta modal de navegação móvel. O Radix mantém o foco no diálogo e torna o
 * restante da página inerte enquanto ela está aberta.
 */
export function MobileNavigationDialog({
  children,
  contentClassName,
  open,
  onOpenChange,
  title,
  trigger,
}: MobileNavigationDialogProps) {
  return (
    <Dialog.Root onOpenChange={onOpenChange} open={open}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-10 bg-ink/30 md:hidden"
          data-testid="drawer-backdrop"
        />
        <Dialog.Content className={contentClassName} id="sidebar">
          <Dialog.Title className="sr-only">{title}</Dialog.Title>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
