"use client";

const borderColors = {
  blue: "border-l-primary",
  amber: "border-l-accent-amber",
  green: "border-l-accent-green",
  purple: "border-l-accent-purple",
  red: "border-l-accent-red",
} as const;

interface StatCardProps {
  label: string;
  value: string | number;
  color: "blue" | "amber" | "green" | "purple" | "red";
}

export default function StatCard({ label, value, color }: StatCardProps) {
  return (
    <div className={`glass p-6 border-l-4 ${borderColors[color]}`}>
      <p className="text-2xl font-bold text-text-primary">{value}</p>
      <p className="text-sm text-text-muted mt-1">{label}</p>
    </div>
  );
}
