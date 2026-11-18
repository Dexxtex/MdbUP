import type {
  OperationStatus,
  RunStatus,
  SnapshotQuality,
  SnapshotStatus,
  SourceStatus,
} from "../../api/types";
import { cn } from "../../lib/cn";
import {
  OPERATION_STATUS_LABELS,
  OPERATION_STATUS_TONES,
  RUN_STATUS_LABELS,
  RUN_STATUS_TONES,
  SNAPSHOT_QUALITY_LABELS,
  SNAPSHOT_QUALITY_TONES,
  SNAPSHOT_STATUS_LABELS,
  SNAPSHOT_STATUS_TONES,
  SOURCE_STATUS_LABELS,
  SOURCE_STATUS_TONES,
  TONE_LABELS,
  type Tone,
} from "../../lib/status";
import { IconAlert, IconCheck, IconClock, IconDot, IconX } from "./icons";

const toneStyles: Record<Tone, string> = {
  neutral: "border-line bg-surface-muted text-ink-muted",
  info: "border-accent/40 bg-accent-soft text-accent",
  success: "border-success/40 bg-success-soft text-success",
  warning: "border-warning/40 bg-warning-soft text-warning",
  danger: "border-danger/40 bg-danger-soft text-danger",
};

const toneIcons: Record<Tone, typeof IconDot> = {
  neutral: IconDot,
  info: IconClock,
  success: IconCheck,
  warning: IconAlert,
  danger: IconX,
};

export function StatusPill({
  label,
  tone,
  code,
  className,
}: {
  label: string;
  tone: Tone;
  /** Valore macchina (es. `AWAITING_APPROVAL`) mostrato nel tooltip. */
  code?: string;
  className?: string;
}) {
  const Icon = toneIcons[tone];
  return (
    <span
      title={code}
      data-tone={tone}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        toneStyles[tone],
        className,
      )}
    >
      <Icon />
      <span>{label}</span>
      <span className="sr-only">{`(${TONE_LABELS[tone]}${code ? `, ${code}` : ""})`}</span>
    </span>
  );
}

export function RunStatusPill({ status }: { status: RunStatus }) {
  return (
    <StatusPill
      label={RUN_STATUS_LABELS[status]}
      tone={RUN_STATUS_TONES[status]}
      code={status}
    />
  );
}

export function OperationStatusPill({ status }: { status: OperationStatus }) {
  return (
    <StatusPill
      label={OPERATION_STATUS_LABELS[status]}
      tone={OPERATION_STATUS_TONES[status]}
      code={status}
    />
  );
}

export function SnapshotStatusPill({ status }: { status: SnapshotStatus }) {
  return (
    <StatusPill
      label={SNAPSHOT_STATUS_LABELS[status]}
      tone={SNAPSHOT_STATUS_TONES[status]}
      code={status}
    />
  );
}

export function SnapshotQualityPill({ quality }: { quality: SnapshotQuality }) {
  return (
    <StatusPill
      label={SNAPSHOT_QUALITY_LABELS[quality]}
      tone={SNAPSHOT_QUALITY_TONES[quality]}
      code={quality}
    />
  );
}

export function SourceStatusPill({ status }: { status: SourceStatus }) {
  return (
    <StatusPill
      label={SOURCE_STATUS_LABELS[status]}
      tone={SOURCE_STATUS_TONES[status]}
      code={status}
    />
  );
}
