"use client";

interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  className?: string;
}

export default function GlassCard({ children, className = "", ...rest }: GlassCardProps) {
  return <div className={`glass p-6 ${className}`} {...rest}>{children}</div>;
}
