import { Icon, IconName, Money } from "./components";

export type PeriodPoint = {
  period: string; label: string; revenue: string | number; orders: number; new_customers: number;
};
export type ProductSeries = {
  product_name: string; revenue: string | number; quantity: number; values: (string | number)[];
};

const colors = ["#176b4d", "#d29a2e", "#446e9b", "#b85e48", "#7a5aa6"];

function compact(value: number) {
  return new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function labelIndexes(length: number) {
  const step = length > 16 ? 5 : length > 8 ? 2 : 1;
  return new Set(Array.from({ length }, (_, index) => index).filter(index =>
    index === 0 || index === length - 1 || index % step === 0
  ));
}

export function MetricCard({ label, value, icon, change, detail, tone = "green" }: {
  label: string; value: React.ReactNode; icon: IconName; change?: number | null;
  detail: string; tone?: "green" | "gold" | "blue" | "plum";
}) {
  return <article className={"metric executive-metric " + tone}>
    <div className="metric-top"><span className="metric-icon"><Icon name={icon} /></span>
      {change !== undefined && <span className={"delta " + (change === null || change >= 0 ? "up" : "down")}>
        {change === null ? "New" : (change >= 0 ? "+" : "") + change + "%"}
      </span>}</div>
    <span className="metric-label">{label}</span><strong>{value}</strong><small>{detail}</small>
  </article>;
}

export function RevenueChart({ points }: { points: PeriodPoint[] }) {
  const width = 820, height = 280, left = 58, right = 20, top = 18, bottom = 42;
  const values = points.map(point => Number(point.revenue));
  const max = Math.max(...values, 1);
  const chartWidth = width - left - right, chartHeight = height - top - bottom;
  const x = (index: number) => left + (points.length === 1 ? 0 : index * chartWidth / (points.length - 1));
  const y = (value: number) => top + chartHeight - value * chartHeight / max;
  const line = values.map((value, index) => (index ? "L" : "M") + x(index) + " " + y(value)).join(" ");
  const area = line + " L" + x(values.length - 1) + " " + (top + chartHeight) +
    " L" + x(0) + " " + (top + chartHeight) + " Z";
  const labels = labelIndexes(points.length);
  return <div className="chart-shell"><svg className="chart" viewBox={"0 0 " + width + " " + height}
    role="img" aria-label="Revenue trend">
    <defs><linearGradient id="revenue-fill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="#23805e" stopOpacity=".3" />
      <stop offset="100%" stopColor="#23805e" stopOpacity=".02" />
    </linearGradient></defs>
    {[0, .25, .5, .75, 1].map(ratio => {
      const gridY = top + chartHeight * ratio;
      const value = max * (1 - ratio);
      return <g key={ratio}><line x1={left} x2={width - right} y1={gridY} y2={gridY}
        className="chart-grid-line" /><text x={left - 10} y={gridY + 4}
        className="axis-label y-label"><tspan>&#8377;</tspan>{compact(value)}</text></g>;
    })}
    <path d={area} fill="url(#revenue-fill)" /><path d={line} className="revenue-line" />
    {points.map((point, index) => {
      const pointX = x(index), pointY = y(values[index]);
      const tooltipX = Math.max(left, Math.min(width - right - 150, pointX - 75));
      const tooltipY = Math.max(5, pointY - 68);
      return <g key={point.period} className="chart-hover">
        <circle cx={pointX} cy={pointY} r="5" className="chart-point" />
        <g className="svg-tooltip" transform={"translate(" + tooltipX + " " + tooltipY + ")"}>
          <rect width="150" height="56" rx="8" className="tooltip-bg" />
          <text x="12" y="20" className="tooltip-title">{point.label}</text>
          <text x="12" y="41" className="tooltip-value"><tspan>&#8377;</tspan>
            {values[index].toLocaleString("en-IN", { maximumFractionDigits: 0 })}</text>
        </g>
        {labels.has(index) && <text x={pointX} y={height - 12} className="axis-label"
          textAnchor="middle">{point.label}</text>}
      </g>;
    })}
  </svg></div>;
}

export function CustomerChart({ points }: { points: PeriodPoint[] }) {
  const width = 820, height = 280, left = 44, right = 18, top = 20, bottom = 42;
  const values = points.map(point => Number(point.new_customers));
  const max = Math.max(...values, 1);
  const chartWidth = width - left - right, chartHeight = height - top - bottom;
  const slot = chartWidth / Math.max(points.length, 1);
  const barWidth = Math.max(5, Math.min(34, slot * .58));
  const labels = labelIndexes(points.length);
  return <div className="chart-shell"><svg className="chart" viewBox={"0 0 " + width + " " + height}
    role="img" aria-label="New customer trend">
    {[0, .25, .5, .75, 1].map(ratio => {
      const gridY = top + chartHeight * ratio;
      const value = Math.round(max * (1 - ratio));
      return <g key={ratio}><line x1={left} x2={width - right} y1={gridY} y2={gridY}
        className="chart-grid-line" /><text x={left - 10} y={gridY + 4}
        className="axis-label y-label">{value}</text></g>;
    })}
    {points.map((point, index) => {
      const barHeight = values[index] * chartHeight / max;
      const barX = left + index * slot + (slot - barWidth) / 2;
      const barY = top + chartHeight - barHeight;
      const tooltipX = Math.max(left, Math.min(width - right - 150, barX + barWidth / 2 - 75));
      const tooltipY = Math.max(5, barY - 68);
      return <g key={point.period} className="chart-hover">
        <rect x={barX} y={barY} width={barWidth} height={Math.max(barHeight, 2)}
          rx="4" className="customer-bar" />
        <g className="svg-tooltip" transform={"translate(" + tooltipX + " " + tooltipY + ")"}>
          <rect width="150" height="56" rx="8" className="tooltip-bg" />
          <text x="12" y="20" className="tooltip-title">{point.label}</text>
          <text x="12" y="41" className="tooltip-value">
            {values[index].toLocaleString("en-IN") + " new customers"}</text>
        </g>
        {labels.has(index) && <text x={barX + barWidth / 2} y={height - 12}
          className="axis-label" textAnchor="middle">{point.label}</text>}
      </g>;
    })}
  </svg></div>;
}

export function ProductSalesChart({ points, products }: {
  points: PeriodPoint[]; products: ProductSeries[];
}) {
  if (!products.length) return <div className="chart-empty">No product sales in this period.</div>;
  const width = 860, height = 310, left = 34, right = 18, top = 20, bottom = 46;
  const totals = points.map((_, index) => products.reduce(
    (sum, product) => sum + Number(product.values[index] || 0), 0
  ));
  const max = Math.max(...totals, 1);
  const chartWidth = width - left - right, chartHeight = height - top - bottom;
  const slot = chartWidth / Math.max(points.length, 1);
  const barWidth = Math.max(5, Math.min(42, slot * .66));
  const labels = labelIndexes(points.length);
  return <div className="product-visual">
    <div className="chart-shell product-chart"><svg className="chart"
      viewBox={"0 0 " + width + " " + height} role="img" aria-label="Product sales by period">
      {[0, .25, .5, .75, 1].map(ratio => {
        const gridY = top + chartHeight * ratio;
        return <g key={ratio}><line x1={left} x2={width - right}
          y1={gridY} y2={gridY} className="chart-grid-line" />
          <text x={left - 7} y={gridY + 4} className="axis-label y-label">
            <tspan>&#8377;</tspan>{compact(max * (1 - ratio))}</text></g>;
      })}
      {points.map((point, index) => {
        let cursor = top + chartHeight;
        const segments = products.map((product, productIndex) => {
          const value = Number(product.values[index] || 0);
          const segmentHeight = value * chartHeight / max;
          cursor -= segmentHeight;
          const barX = left + index * slot + (slot - barWidth) / 2;
          const tooltipX = Math.max(left, Math.min(width - right - 190, barX + barWidth / 2 - 95));
          const tooltipY = Math.max(5, cursor - 68);
          return <g key={product.product_name} className="chart-hover">
            <rect x={barX} y={cursor} width={barWidth} height={segmentHeight}
              fill={colors[productIndex]} rx="2" />
            <g className="svg-tooltip" transform={"translate(" + tooltipX + " " + tooltipY + ")"}>
              <rect width="190" height="58" rx="8" className="tooltip-bg" />
              <text x="12" y="20" className="tooltip-title">
                {(product.product_name.length > 25
                  ? product.product_name.slice(0, 24) + "..." : product.product_name)}</text>
              <text x="12" y="42" className="tooltip-value">{point.label + "  "}
                <tspan>&#8377;</tspan>{value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</text>
            </g>
          </g>;
        });
        return <g key={point.period}>{segments}{labels.has(index) &&
          <text x={left + index * slot + slot / 2} y={height - 15}
            className="axis-label" textAnchor="middle">{point.label}</text>}</g>;
      })}
    </svg></div>
    <div className="product-ranking"><div className="legend">
      {products.map((product, index) => <span key={product.product_name}>
        <i style={{ background: colors[index] }} />{product.product_name}</span>)}</div>
      <div className="rank-list">{products.map((product, index) => {
        const share = Number(product.revenue) * 100 / Math.max(
          products.reduce((sum, item) => sum + Number(item.revenue), 0), 1
        );
        return <div className="rank-item" key={product.product_name}><div>
          <span className="rank-number">{String(index + 1).padStart(2, "0")}</span>
          <span><strong>{product.product_name}</strong><small>{product.quantity.toLocaleString()} units</small></span>
          <b><Money value={product.revenue} compact /></b></div>
          <div className="rank-track"><i style={{ width: share + "%", background: colors[index] }} /></div>
        </div>;
      })}</div>
    </div>
  </div>;
}
