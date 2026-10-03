import type { NodeType } from "@/lib/types";
import { NO_CLUSTER_COLOR, TYPE_FILL } from "@/lib/style";

/** Small SVG glyph that matches the node shape used in the graph. */
export function NodeTypeIcon({
  type,
  color,
  size = 14,
  className,
}: {
  type: NodeType;
  color?: string;
  size?: number;
  className?: string;
}) {
  const fill = color ?? (type === "phenotype" ? NO_CLUSTER_COLOR : TYPE_FILL[type]);
  const hollow = type === "phenotype";
  const common = hollow
    ? { fill: "#fff", stroke: fill, strokeWidth: 1.6 }
    : { fill, stroke: "none" as const };
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" className={className}>
      {shape(type, common)}
    </svg>
  );
}

function shape(type: NodeType, p: React.SVGProps<SVGElement>) {
  const props = p as React.SVGProps<SVGPolygonElement> & React.SVGProps<SVGCircleElement> & React.SVGProps<SVGRectElement>;
  switch (type) {
    case "disease":
      return <circle cx="8" cy="8" r="6.5" {...props} />;
    case "phenotype":
      return <circle cx="8" cy="8" r="5.5" {...props} />;
    case "gene":
      return <rect x="1.5" y="3" width="13" height="10" rx="3" {...props} />;
    case "variant_group":
      return <polygon points="1.5,3 11,3 14.5,8 11,13 1.5,13" {...props} />;
    case "mechanism":
      return <polygon points="8,1 15,8 8,15 1,8" {...props} />;
    case "patient_org":
      return <polygon points="4.5,2 11.5,2 15,8 11.5,14 4.5,14 1,8" {...props} />;
    case "asset":
      return <polygon points="8,1.5 14.5,6.2 12,14 4,14 1.5,6.2" {...props} />;
    case "study":
      return <polygon points="8,1.5 15,14 1,14" {...props} />;
    case "therapy":
      return <polygon points="8,1 10,6 15,6 11,9.3 12.5,14.5 8,11.4 3.5,14.5 5,9.3 1,6 6,6" {...props} />;
    case "publication":
      return <rect x="2.5" y="2.5" width="11" height="11" {...props} />;
    case "researcher":
      return <polygon points="5,1.5 11,1.5 14.5,5 14.5,11 11,14.5 5,14.5 1.5,11 1.5,5" {...props} />;
    case "grant":
      return <polygon points="4,2 12,2 14.5,4.5 14.5,14 1.5,14 1.5,4.5" {...props} />;
    default:
      return <circle cx="8" cy="8" r="6" {...props} />;
  }
}
