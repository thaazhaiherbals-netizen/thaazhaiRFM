// Marketing presentation helpers. Amounts use the Meta ad-account currency, never an assumed INR.

export type Totals = {
  spend: string; impressions: number; reach_daily_sum: number; clicks: number;
  link_clicks: number; outbound_clicks: number; landing_page_views: number;
  add_to_cart: string; checkouts_initiated: string; meta_purchases: string;
  meta_purchase_value: string; leads: string; cpm: string | null; ctr: string | null;
  cpc: string | null; avg_daily_frequency: string | null; meta_roas: string | null;
  cost_per_meta_purchase: string | null;
};

export type DailyPoint = {
  day: string; spend: string; impressions: number; link_clicks: number;
  meta_purchases: string; meta_purchase_value: string; orders: number; revenue: string;
};

export function Amount({ value, currency }: { value: string | number | null; currency?: string | null }) {
  if (value === null || value === undefined) return <>-</>;
  const amount = Number(value);
  if (!currency) return <>{amount.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</>;
  return <>{new Intl.NumberFormat("en-IN", {
    style: "currency", currency, maximumFractionDigits: 2,
  }).format(amount)}</>;
}

export function count(value: string | number | null | undefined) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export function ratio(value: string | null, suffix = "") {
  return value === null ? "-" : Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 }) + suffix;
}

function compact(value: number) {
  return new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

/** Daily Meta spend (bars) against observed business revenue (line). Date-level only. */
export function SpendRevenueChart({ points }: { points: DailyPoint[] }) {
  if (!points.length) return <div className="chart-empty">No days in range.</div>;
  const width = 820, height = 280, left = 58, right = 20, top = 18, bottom = 42;
  const spend = points.map(point => Number(point.spend));
  const revenue = points.map(point => Number(point.revenue));
  const max = Math.max(...spend, ...revenue, 1);
  const chartWidth = width - left - right, chartHeight = height - top - bottom;
  const slot = chartWidth / points.length;
  const barWidth = Math.max(2, Math.min(24, slot * .6));
  const x = (index: number) => left + slot * index + slot / 2;
  const y = (value: number) => top + chartHeight - value * chartHeight / max;
  const line = revenue.map((value, index) => (index ? "L" : "M") + x(index) + " " + y(value)).join(" ");
  const step = points.length > 16 ? Math.ceil(points.length / 8) : 1;
  return <div className="chart-shell"><svg className="chart" viewBox={`0 0 ${width} ${height}`}
    role="img" aria-label="Daily Meta spend compared with business revenue">
    {[0, .25, .5, .75, 1].map(fraction => {
      const gridY = top + chartHeight * fraction;
      return <g key={fraction}><line x1={left} x2={width - right} y1={gridY} y2={gridY}
        className="chart-grid-line" /><text x={left - 10} y={gridY + 4}
        className="axis-label y-label">{compact(max * (1 - fraction))}</text></g>;
    })}
    {points.map((point, index) => <g key={point.day}>
      <rect className="spend-bar" x={x(index) - barWidth / 2} y={y(spend[index])}
        width={barWidth} height={top + chartHeight - y(spend[index])} rx="2">
        <title>{`${point.day}: spend ${count(point.spend)}, revenue ${count(point.revenue)}, ${point.orders} orders`}</title>
      </rect>
      {(index % step === 0 || index === points.length - 1) && <text x={x(index)}
        y={height - 14} textAnchor="middle" className="axis-label">{point.day.slice(5)}</text>}
    </g>)}
    <path d={line} className="revenue-line" />
  </svg>
    <div className="legend"><span><i className="legend-swatch spend" />Meta spend</span>
      <span><i className="legend-swatch revenue" />Business revenue (orders)</span></div>
  </div>;
}
