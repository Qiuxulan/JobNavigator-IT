import type { ReactNode } from "react";

interface PageHeadProps {
  eyebrow: string;
  title: ReactNode;
  sub?: ReactNode;
  /** 标题行右侧的附加内容（如「最新更新」徽标） */
  extra?: ReactNode;
}

/** 统一的页面头部：eyebrow（小标签）/ title（主标题）/ sub（说明）结构。 */
export default function PageHead({ eyebrow, title, sub, extra }: PageHeadProps) {
  const main = (
    <div>
      <div className="page-title">{title}</div>
      {sub && <div className="page-sub">{sub}</div>}
    </div>
  );
  return (
    <div className="page-head">
      <div className="page-eyebrow">{eyebrow}</div>
      {extra ? <div className="spread">{main}{extra}</div> : main}
    </div>
  );
}
