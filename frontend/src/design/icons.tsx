import type { SVGProps } from "react";

function Icon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 20 20"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    />
  );
}

export const IngestIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M10 4v12M4 10h12" /></Icon>
);
export const JobsIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M4 6h12M4 10h12M4 14h7" /></Icon>
);
export const NotesIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M5.5 3.5h6l3 3v10h-9z" /><path d="M11.5 3.5v3h3" /></Icon>
);
export const SettingsIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M4 6h5M13 6h3M4 14h2M10 14h6" /><circle cx="11" cy="6" r="1.8" /><circle cx="8" cy="14" r="1.8" /></Icon>
);
export const CheckIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="m4.5 10.5 3.5 3.5 7.5-8" /></Icon>
);
export const CloseIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="m5 5 10 10M15 5 5 15" /></Icon>
);
export const ChevronIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="m7.5 5 5 5-5 5" /></Icon>
);
