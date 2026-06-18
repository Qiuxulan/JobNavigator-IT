import type { ReactNode, CSSProperties } from "react";

interface CardProps {
  title?: string;
  desc?: string;
  action?: ReactNode;
  children: ReactNode;
  style?: CSSProperties;
  className?: string;
  id?: string;
}

export function Card({ title, desc, action, children, style, className, id }: CardProps) {
  return (
    <div className={"card" + (className ? " " + className : "")} style={style} id={id}>
      {(title || action) && (
        <div className="card-hd">
          <div>
            {title && <div className="card-title">{title}</div>}
            {desc && <div className="card-desc">{desc}</div>}
          </div>
          {action}
        </div>
      )}
      <div className="card-bd">{children}</div>
    </div>
  );
}

interface StatCardProps {
  icon: React.FC<React.SVGProps<SVGSVGElement>>;
  solid?: boolean;
  label: string;
  value: string | number;
  unit?: string;
  sub?: ReactNode;
}

export function StatCard({ icon: I, solid = false, label, value, unit, sub }: StatCardProps) {
  return (
    <div className="stat fade">
      <div className="stat-top">
        <div className={"stat-ic" + (solid ? " solid" : "")}><I /></div>
      </div>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}{unit && <span className="unit">{unit}</span>}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}
