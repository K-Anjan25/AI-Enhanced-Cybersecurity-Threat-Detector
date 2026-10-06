/**
 * The primitive barrel — design.md §6: "All primitives live in
 * `dashboard/src/components/ui` and are the only approved building blocks (R-22,
 * R-27)".
 *
 * A screen imports from `../../components/ui`, never from a primitive's own file,
 * so the approved set is one list in one place. If a component is not exported
 * here it is not a primitive, and a screen that needs it either composes one from
 * this list or brings a proposal to design.md — it does not reach around the
 * barrel.
 *
 * Still to come, and deliberately absent rather than stubbed: the D3 visualisations
 * (`Timeline`, `TimeSeriesChart`, `EntityGraph`) arrive with T-406 and
 * `CommandPalette` with T-411. Both are §6 components; neither belongs to this
 * task's scope, and an empty file with the right name would be worse than no file.
 */
export { Badge } from './Badge';
export type { BadgeProps, BadgeTone } from './Badge';
export { Button } from './Button';
export type { ButtonProps, ButtonSize, ButtonVariant } from './Button';
export { Card, Card as Panel } from './Card';
export type { CardProps, CardState } from './Card';
export { ConnectionStatus } from './ConnectionStatus';
export type { ConnectionState } from './ConnectionStatus';
export { DataTable } from './DataTable';
export type { Column, DataTableProps } from './DataTable';
export { EmptyState } from './EmptyState';
export type { EmptyStateProps } from './EmptyState';
export { ErrorState } from './ErrorState';
export type { ErrorStateProps } from './ErrorState';
export { ConfirmDialog, Modal } from './Modal';
export type { ConfirmDialogProps, ModalProps } from './Modal';
export { ScoreMeter, scoreBand } from './ScoreMeter';
export type { ScoreBand, ScoreMeterProps } from './ScoreMeter';
export { SeverityPill } from './SeverityPill';
export type { SeverityPillProps } from './SeverityPill';
export { SEVERITIES, SEVERITY_GLYPHS, SEVERITY_LABELS, isSeverity } from './severity';
export type { Severity } from './severity';
export { Skeleton } from './Skeleton';
export type { SkeletonProps } from './Skeleton';
export { Spinner } from './Spinner';
export { DEFAULT_TOAST_MS, ToastProvider, useToast } from './Toast';
export type { ToastIntent, ToastProviderProps, ToastRecord } from './Toast';
