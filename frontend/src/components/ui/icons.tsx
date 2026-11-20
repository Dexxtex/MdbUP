import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function baseProps(props: IconProps): IconProps {
  return {
    width: 16,
    height: 16,
    viewBox: "0 0 20 20",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
    focusable: false,
    ...props,
  };
}

export function IconCheck(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M4 10.5 8 14.5 16 6" />
    </svg>
  );
}

export function IconX(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M5 5l10 10M15 5 5 15" />
    </svg>
  );
}

export function IconClock(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 6v4.5l3 1.8" />
    </svg>
  );
}

export function IconAlert(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M10 3.5 17.5 16h-15z" />
      <path d="M10 8v3.5M10 13.8v.2" />
    </svg>
  );
}

export function IconDot(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="10" cy="10" r="4" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconBuilding(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M4 16.5V5l6-2.5 6 2.5v11.5" />
      <path d="M7.5 8h1M11.5 8h1M7.5 11.5h1M11.5 11.5h1" />
    </svg>
  );
}

export function IconNode(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="10" cy="5" r="2.2" />
      <circle cx="5" cy="15" r="2.2" />
      <circle cx="15" cy="15" r="2.2" />
      <path d="M10 7.2 5.8 13M10 7.2 14.2 13" />
    </svg>
  );
}

export function IconFilter(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M3.5 5.5h13l-5 6v5l-3-1.5v-3.5z" />
    </svg>
  );
}

export function IconGrid(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <rect x="3.5" y="3.5" width="5.5" height="5.5" rx="1.2" />
      <rect x="11" y="3.5" width="5.5" height="5.5" rx="1.2" />
      <rect x="3.5" y="11" width="5.5" height="5.5" rx="1.2" />
      <rect x="11" y="11" width="5.5" height="5.5" rx="1.2" />
    </svg>
  );
}

export function IconLayers(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M10 3 17 7l-7 4-7-4z" />
      <path d="m3.5 10.5 6.5 3.7 6.5-3.7" />
      <path d="m3.5 14 6.5 3.7L16.5 14" />
    </svg>
  );
}

export function IconLink(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M8.5 11.5 11.5 8.5" />
      <path d="M9.5 6.5 11 5a3 3 0 0 1 4.2 4.2L13.5 11" />
      <path d="M10.5 13.5 9 15a3 3 0 0 1-4.2-4.2L6.5 9" />
    </svg>
  );
}

export function IconActivity(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M2.5 10.5h3l2-5 3.5 9 2.5-6 1.5 2h2.5" />
    </svg>
  );
}

export function IconSettings(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="10" cy="10" r="2.6" />
      <path d="M10 2.8v1.6M10 15.6v1.6M2.8 10h1.6M15.6 10h1.6M4.9 4.9l1.1 1.1M14 14l1.1 1.1M15.1 4.9 14 6M6 14l-1.1 1.1" />
    </svg>
  );
}

export function IconSun(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="10" cy="10" r="3.4" />
      <path d="M10 2.5v1.8M10 15.7v1.8M2.5 10h1.8M15.7 10h1.8M4.7 4.7l1.3 1.3M14 14l1.3 1.3M15.3 4.7 14 6M6 14l-1.3 1.3" />
    </svg>
  );
}

export function IconMoon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M16 12.2A6.5 6.5 0 0 1 7.8 4a6.8 6.8 0 1 0 8.2 8.2z" />
    </svg>
  );
}

export function IconMenu(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M3.5 6h13M3.5 10h13M3.5 14h13" />
    </svg>
  );
}

export function IconChevronLeft(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M12 4.5 6.5 10l5.5 5.5" />
    </svg>
  );
}

export function IconChevronRight(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M8 4.5 13.5 10 8 15.5" />
    </svg>
  );
}

export function IconArrowRight(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M3.5 10h13M11.5 5 16.5 10l-5 5" />
    </svg>
  );
}

export function IconSearch(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="8.8" cy="8.8" r="5.3" />
      <path d="m12.8 12.8 3.7 3.7" />
    </svg>
  );
}

export function IconServer(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <rect x="3" y="3.5" width="14" height="5" rx="1.4" />
      <rect x="3" y="11.5" width="14" height="5" rx="1.4" />
      <path d="M6 6h.2M6 14h.2M9.5 6h4.5M9.5 14h4.5" />
    </svg>
  );
}

export function IconDatabase(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <ellipse cx="10" cy="5" rx="6" ry="2.4" />
      <path d="M4 5v10c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4V5" />
      <path d="M4 10c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4" />
    </svg>
  );
}

export function IconShield(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M10 2.8 16 5v5c0 3.4-2.4 6.1-6 7.2-3.6-1.1-6-3.8-6-7.2V5z" />
      <path d="m7.5 9.8 1.8 1.8 3.4-3.6" />
    </svg>
  );
}

export function IconBell(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M5.5 8.5a4.5 4.5 0 0 1 9 0c0 3.2 1 4.3 1.5 5H4c.5-.7 1.5-1.8 1.5-5z" />
      <path d="M8.3 16.2a1.9 1.9 0 0 0 3.4 0" />
    </svg>
  );
}

export function IconDownload(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M10 3v9M6.5 8.8 10 12.3l3.5-3.5" />
      <path d="M4 15.5h12" />
    </svg>
  );
}

export function IconUpload(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M10 12.5V3.5M6.5 7 10 3.5 13.5 7" />
      <path d="M4 15.5h12" />
    </svg>
  );
}

export function IconLogout(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M8 4H4.5v12H8" />
      <path d="M12 6.5 15.5 10 12 13.5M7.5 10h8" />
    </svg>
  );
}

export function IconPlay(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M6.5 4.5 15 10l-8.5 5.5z" />
    </svg>
  );
}

export function IconPause(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M7 4.5v11M13 4.5v11" />
    </svg>
  );
}

export function IconRefresh(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M16 6.5V3.5l-2 2a6 6 0 1 0 1.4 6.2" />
      <path d="M16 3.5h-3" />
    </svg>
  );
}


export function IconSpinner(props: IconProps) {
  return (
    <svg {...baseProps(props)} className={`animate-spin ${props.className ?? ""}`}>
      <path d="M10 3.5a6.5 6.5 0 1 1-6.5 6.5" />
    </svg>
  );
}

export function IconHelp(props: IconProps) {
  return (
    <svg {...baseProps(props)} viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9a2.5 2.5 0 1 1 3.2 2.4c-.7.2-.7.8-.7 1.6" />
      <path d="M12 17h.01" />
    </svg>
  );
}
