import {
  Callout,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  useEffect,
  useHostTheme,
  useRef,
  useState,
} from "cursor/canvas";

type Value = number | string | null;
type Rec = Record<string, Value>;
type Coef = { term: string; coef: number; t: number; p: number };
type Dashboard = {
  generated_at: string;
  start: string;
  symbols: string[];
  series: Record<string, string>;
  series_kind?: Record<string, string>;
  units: Record<string, string>;
  rolling_window: number;
  coverage: { column: string; first: string | null; as_of: string | null }[];
  snapshot: Rec[];
  levels: Rec[];
  rolling_corr: Record<string, Rec[]>;
  regressions: Record<string, { nobs: number; r2: number; coefficients: Coef[] }>;
  sentiment_daily?: {
    symbol: string;
    session: string;
    sentiment: number | null;
    articles: number | null;
    close?: number | null;
  }[];
};

const DATA: Dashboard = __DASHBOARD_DATA__;

const isNum = (v: Value | undefined): v is number => typeof v === "number" && Number.isFinite(v);

function fmt(v: Value | undefined, digits = 2, suffix = ""): string {
  if (!isNum(v)) return "-";
  return `${v > 0 && suffix === "%" ? "+" : ""}${v.toFixed(digits)}${suffix}`;
}

function daysBetween(a: string, b: string): number {
  return (Date.parse(b) - Date.parse(a)) / 86_400_000;
}

// ---------------------------------------------------------------------------
// Guide chart: SVG line/bar chart with major + minor gridlines, baselines,
// latest-value labels and a hover guide.
// ---------------------------------------------------------------------------

type ChartSeries = { name: string; data: (number | null)[] };

function niceStep(range: number, target: number): number {
  const raw = range / Math.max(target, 1);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const s of [1, 2, 2.5, 5, 10]) if (s * mag >= raw - 1e-12) return s * mag;
  return 10 * mag;
}

function decimals(step: number): number {
  return (String(+step.toFixed(6)).split(".")[1] ?? "").length;
}

function niceDomain(values: number[], extra: number[], target: number) {
  let vMin = Math.min(...values, ...extra);
  let vMax = Math.max(...values, ...extra);
  if (vMin === vMax) [vMin, vMax] = [vMin - 1, vMax + 1];
  const step = niceStep(vMax - vMin, target);
  return { lo: Math.floor(vMin / step) * step, hi: Math.ceil(vMax / step) * step, step };
}

function ticksOf(lo: number, hi: number, step: number): number[] {
  const out: number[] = [];
  for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setWidth(Math.max(320, Math.floor(w)));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

function GuideChart({
  categories,
  series,
  height = 360,
  kind = "line",
  baselines = [],
  symmetricFloor,
  yLabel,
  digits = 2,
  overlay,
}: {
  categories: string[];
  series: ChartSeries[];
  height?: number;
  kind?: "line" | "bar";
  baselines?: number[];
  /** Zoom a bounded score around 0 (|limit| >= floor, <= 1) instead of auto-fitting. */
  symmetricFloor?: number;
  yLabel?: string;
  digits?: number;
  /** A line drawn against its own right-hand axis (e.g. close price over sentiment bars). */
  overlay?: ChartSeries & { label: string; digits?: number };
}) {
  const theme = useHostTheme();
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const colors = [
    theme.category.blue,
    theme.category.orange,
    theme.category.green,
    theme.category.purple,
    theme.category.cyan,
    theme.category.pink,
    theme.category.red,
    theme.category.yellow,
  ];

  const values = series.flatMap((s) => s.data).filter(isNum);
  if (categories.length === 0 || values.length === 0) return null;

  const margin = { left: 58, right: 70, top: 10, bottom: 26 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const n = categories.length;

  let lo: number;
  let hi: number;
  let step: number;
  if (symmetricFloor !== undefined) {
    const peak = Math.max(...values.map(Math.abs));
    const limit = Math.min(1, Math.max(symmetricFloor, Math.ceil((peak * 1.15) / 0.25) * 0.25));
    [lo, hi] = [-limit, limit];
    step = niceStep(hi - lo, 8);
  } else {
    ({ lo, hi, step } = niceDomain(values, baselines, 7));
  }
  const dec = decimals(step);
  const majors = ticksOf(lo, hi, step);
  const minors = majors.slice(0, -1).map((v) => v + step / 2);

  const y = (v: number) => margin.top + ((hi - v) / (hi - lo)) * plotH;
  const slot = plotW / Math.max(n, 1);
  const x = (i: number) =>
    kind === "bar" ? margin.left + (i + 0.5) * slot : margin.left + (n <= 1 ? plotW / 2 : (i * plotW) / (n - 1));

  const overlayValues = overlay ? overlay.data.filter(isNum) : [];
  const right = overlayValues.length ? niceDomain(overlayValues, [], 6) : null;
  const yR = (v: number) => (right ? margin.top + ((right.hi - v) / (right.hi - right.lo)) * plotH : 0);
  const overlayPath =
    overlay && right
      ? overlay.data.reduce<{ d: string; pen: boolean }>(
          (acc, v, i) =>
            isNum(v)
              ? { d: `${acc.d}${acc.pen ? "L" : "M"}${x(i).toFixed(1)},${yR(v).toFixed(1)}`, pen: true }
              : { d: acc.d, pen: false },
          { d: "", pen: false },
        ).d
      : "";

  const tickCount = Math.min(8, n);
  const xTicks =
    tickCount <= 1 ? [0] : Array.from({ length: tickCount }, (_, i) => Math.round((i * (n - 1)) / (tickCount - 1)));

  const paths = series.map((s) => {
    let d = "";
    let pen = false;
    s.data.forEach((v, i) => {
      if (isNum(v)) {
        d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
        pen = true;
      } else pen = false;
    });
    return d;
  });

  const lastLabels = series
    .map((s, si) => {
      const idx = s.data.map((v, i) => (isNum(v) ? i : -1)).filter((i) => i >= 0).at(-1);
      return idx === undefined ? null : { si, value: s.data[idx] as number, y: y(s.data[idx] as number) };
    })
    .filter((l): l is { si: number; value: number; y: number } => l !== null)
    .sort((a, b) => a.y - b.y);
  for (let i = 1; i < lastLabels.length; i++) {
    if (lastLabels[i].y - lastLabels[i - 1].y < 13) lastLabels[i].y = lastLabels[i - 1].y + 13;
  }

  const tip = hover === null ? null : { i: hover, x: x(hover) };
  const tipLines =
    tip === null
      ? []
      : [
          ...series.map((s, si) => ({
            text: `${s.name}: ${fmt(s.data[tip.i], digits)}`,
            color: colors[si % colors.length],
          })),
          ...(overlay
            ? [{ text: `${overlay.name}: ${fmt(overlay.data[tip.i], overlay.digits ?? 2)}`, color: theme.text.primary }]
            : []),
        ];
  const tipW = 16 + 7 * Math.max(categories[tip?.i ?? 0].length, ...tipLines.map((l) => l.text.length));
  const tipX = tip === null ? 0 : tip.x + tipW + 12 > width - margin.right ? tip.x - tipW - 8 : tip.x + 8;

  return (
    <div ref={ref} style={{ width: "100%" }}>
      {(series.length > 1 || overlay) && (
        <Row gap={14} wrap>
          {series.map((s, si) => (
            <span key={s.name} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              {kind === "bar" ? (
                <>
                  <span style={{ width: 8, height: 10, background: theme.category.green, display: "inline-block" }} />
                  <span style={{ width: 8, height: 10, background: theme.category.red, display: "inline-block" }} />
                </>
              ) : (
                <span style={{ width: 12, height: 3, background: colors[si % colors.length], display: "inline-block" }} />
              )}
              <Text size="small" tone="secondary" as="span">
                {kind === "bar" ? `${s.name} (bars, left axis)` : s.name}
              </Text>
            </span>
          ))}
          {overlay && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 12, height: 2, background: theme.text.primary, display: "inline-block" }} />
              <Text size="small" tone="secondary" as="span">
                {`${overlay.name} (line, right axis)`}
              </Text>
            </span>
          )}
        </Row>
      )}
      <svg width={width} height={height} style={{ display: "block" }}>
        {minors.map((v) => (
          <line
            key={`m${v}`}
            x1={margin.left}
            x2={margin.left + plotW}
            y1={y(v)}
            y2={y(v)}
            stroke={theme.stroke.tertiary}
            strokeDasharray="2 3"
          />
        ))}
        {majors.map((v) => (
          <g key={`M${v}`}>
            <line x1={margin.left} x2={margin.left + plotW} y1={y(v)} y2={y(v)} stroke={theme.stroke.secondary} />
            <text x={margin.left - 6} y={y(v) + 4} textAnchor="end" fontSize={11} fill={theme.text.tertiary}>
              {v.toFixed(dec)}
            </text>
          </g>
        ))}
        {xTicks.map((i) => (
          <g key={`x${i}`}>
            <line x1={x(i)} x2={x(i)} y1={margin.top} y2={margin.top + plotH} stroke={theme.stroke.tertiary} />
            <text x={x(i)} y={height - 8} textAnchor="middle" fontSize={11} fill={theme.text.tertiary}>
              {categories[i]}
            </text>
          </g>
        ))}
        {baselines.map((b) => (
          <line
            key={`b${b}`}
            x1={margin.left}
            x2={margin.left + plotW}
            y1={y(b)}
            y2={y(b)}
            stroke={theme.text.tertiary}
            strokeDasharray="6 4"
          />
        ))}
        {yLabel && (
          <text
            transform={`translate(12, ${margin.top + plotH / 2}) rotate(-90)`}
            textAnchor="middle"
            fontSize={11}
            fill={theme.text.secondary}
          >
            {yLabel}
          </text>
        )}

        {kind === "bar"
          ? series[0].data.map((v, i) =>
              isNum(v) ? (
                <rect
                  key={i}
                  x={x(i) - slot * 0.35}
                  width={slot * 0.7}
                  y={Math.min(y(v), y(0))}
                  height={Math.max(1, Math.abs(y(v) - y(0)))}
                  fill={v >= 0 ? theme.category.green : theme.category.red}
                />
              ) : null,
            )
          : paths.map((d, si) => (
              <path key={si} d={d} fill="none" stroke={colors[si % colors.length]} strokeWidth={1.6} />
            ))}

        {overlay && right && (
          <g>
            {ticksOf(right.lo, right.hi, right.step).map((v) => (
              <text
                key={`r${v}`}
                x={margin.left + plotW + 6}
                y={yR(v) + 4}
                fontSize={11}
                fill={theme.text.tertiary}
              >
                {v.toFixed(decimals(right.step))}
              </text>
            ))}
            <path d={overlayPath} fill="none" stroke={theme.text.primary} strokeWidth={1.4} />
            <text
              transform={`translate(${width - 10}, ${margin.top + plotH / 2}) rotate(90)`}
              textAnchor="middle"
              fontSize={11}
              fill={theme.text.secondary}
            >
              {overlay.label}
            </text>
          </g>
        )}

        {kind === "line" &&
          lastLabels.map((l) => (
            <text key={`l${l.si}`} x={margin.left + plotW + 6} y={l.y + 4} fontSize={11} fill={colors[l.si % colors.length]}>
              {l.value.toFixed(digits)}
            </text>
          ))}

        {tip && (
          <g pointerEvents="none">
            <line x1={tip.x} x2={tip.x} y1={margin.top} y2={margin.top + plotH} stroke={theme.text.tertiary} />
            <rect
              x={tipX}
              y={margin.top + 4}
              width={tipW}
              height={22 + 16 * tipLines.length}
              rx={4}
              fill={theme.bg.elevated}
              stroke={theme.stroke.secondary}
            />
            <text x={tipX + 8} y={margin.top + 20} fontSize={11} fill={theme.text.secondary}>
              {categories[tip.i]}
            </text>
            {tipLines.map((l, li) => (
              <text key={li} x={tipX + 8} y={margin.top + 36 + 16 * li} fontSize={11} fill={l.color}>
                {l.text}
              </text>
            ))}
          </g>
        )}
        <rect
          x={margin.left}
          y={margin.top}
          width={plotW}
          height={plotH}
          fill="transparent"
          onMouseMove={(e: { currentTarget: Element; clientX: number }) => {
            const box = e.currentTarget.getBoundingClientRect();
            const px = ((e.clientX - box.left) / box.width) * plotW;
            const i = kind === "bar" ? Math.floor(px / slot) : Math.round((px / plotW) * (n - 1));
            setHover(Math.min(n - 1, Math.max(0, i)));
          }}
          onMouseLeave={() => setHover(null)}
        />
      </svg>
    </div>
  );
}

function rows(recs: Rec[], keys: string[]) {
  return {
    categories: recs.map((r) => String(r.date)),
    series: keys.map((k) => ({ name: k, data: recs.map((r) => (isNum(r[k]) ? (r[k] as number) : null)) })),
  };
}

function Caption({ children }: { children: string }) {
  return (
    <Text size="small" tone="tertiary">
      {children}
    </Text>
  );
}

export default function MarketDashboard() {
  const [selected, setSelected] = useState(DATA.symbols[0]);
  const seriesIds = Object.keys(DATA.series);
  const range = `${DATA.start} .. ${DATA.generated_at.slice(0, 10)}`;

  const latest = DATA.coverage.map((c) => c.as_of).filter((d): d is string => d !== null).sort().at(-1) ?? "";
  const lagging = DATA.coverage.filter((c) => c.as_of && daysBetween(c.as_of, latest) > 2);

  const prices = rows(DATA.levels, DATA.symbols);
  const rollingRecs = DATA.rolling_corr[selected] ?? [];
  const rolling = rows(
    rollingRecs,
    Object.keys(rollingRecs[0] ?? {}).filter((k) => k !== "date"),
  );
  const reg = DATA.regressions[selected];
  const snap = DATA.snapshot.find((r) => r.symbol === selected);
  const sentiment = (DATA.sentiment_daily ?? []).filter((r) => r.symbol === selected);

  return (
    <Stack gap={20}>
      <Stack gap={4}>
        <H1>{DATA.symbols.join(", ")}: price, rates and USD/JPY</H1>
        <Caption>
          {`Source: Alpaca (adjusted daily bars), FRED · ${range} · generated ${DATA.generated_at} · not investment advice`}
        </Caption>
      </Stack>

      {lagging.length > 0 && (
        <Callout tone="warning" title="Lagging series">
          {lagging.map((c) => `${c.column} as of ${c.as_of}`).join(", ")} (latest data: {latest}). Lines for these
          series end earlier than the others.
        </Callout>
      )}

      <Stack gap={8}>
        <H2>Snapshot</H2>
        <Table
          headers={["Symbol", "As of", "Close", "1D", "5D", "1M", "3M", "YTD", "From 52w high", "Vol / 20d avg"]}
          columnAlign={["left", "left", "right", "right", "right", "right", "right", "right", "right", "right"]}
          rows={DATA.snapshot.map((r) => [
            String(r.symbol),
            String(r.as_of),
            fmt(r.close),
            fmt(r["1d_%"], 2, "%"),
            fmt(r["5d_%"], 2, "%"),
            fmt(r["1m_%"], 1, "%"),
            fmt(r["3m_%"], 1, "%"),
            fmt(r["ytd_%"], 1, "%"),
            fmt(r["from_52w_high_%"], 1, "%"),
            fmt(r.vol_vs_20d, 2, "x"),
          ])}
        />
      </Stack>

      <Stack gap={8}>
        <H2>Adjusted close, rebased to 100</H2>
        <GuideChart
          categories={prices.categories}
          series={prices.series}
          baselines={[100]}
          height={420}
          yLabel="index (start = 100)"
          digits={1}
        />
        <Caption>{`Y: index (first date = 100, dashed line) · X: date · ${range} · hover for values`}</Caption>
      </Stack>

      <Grid columns={seriesIds.length > 1 ? 2 : 1} gap={20}>
        {seriesIds.map((id) => {
          const d = rows(DATA.levels, [id]);
          const unit = DATA.series_kind?.[id] === "yield" ? "%" : "level";
          return (
            <div key={id}>
              <Stack gap={6}>
                <H3>{`${id}: ${DATA.series[id]}`}</H3>
                <GuideChart categories={d.categories} series={d.series} height={300} yLabel={unit} />
                <Caption>{`Y: ${unit} · X: date · Source: FRED`}</Caption>
              </Stack>
            </div>
          );
        })}
      </Grid>

      <Divider />

      <Stack gap={12}>
        <Row gap={8} align="center">
          <H2>Macro sensitivity</H2>
          {DATA.symbols.map((s) => (
            <span key={s}>
              <Pill active={s === selected} onClick={() => setSelected(s)}>
                {s}
              </Pill>
            </span>
          ))}
        </Row>

        {snap && (
          <Row gap={24}>
            <Stat value={fmt(snap["1m_%"], 1, "%")} label={`${selected} 1M return`} />
            {reg && <Stat value={reg.r2.toFixed(3)} label={`R² (n=${reg.nobs})`} />}
          </Row>
        )}

        <Stack gap={6}>
          <H3>{`Rolling ${DATA.rolling_window}-day correlation of ${selected} daily return`}</H3>
          <GuideChart
            categories={rolling.categories}
            series={rolling.series}
            baselines={[0]}
            symmetricFloor={0.5}
            height={340}
            yLabel="correlation"
          />
          <Caption>{`Y: correlation (weekly samples, axis zoomed around 0) · yields as bp change, FX as % change`}</Caption>
        </Stack>

        {reg && (
          <Stack gap={6}>
            <H3>{`OLS: ${selected} daily % return on factors`}</H3>
            <Table
              headers={["Term", "Coef", "t", "p"]}
              columnAlign={["left", "right", "right", "right"]}
              rows={reg.coefficients.map((c) => [c.term, c.coef.toFixed(4), c.t.toFixed(2), c.p.toFixed(3)])}
              rowTone={reg.coefficients.map((c) => (c.term !== "const" && Math.abs(c.t) >= 2 ? "info" : undefined))}
            />
            <Caption>{`HAC standard errors · marked rows: |t| >= 2 · coef units: % per bp or % per %`}</Caption>
          </Stack>
        )}
      </Stack>

      {sentiment.length > 0 && (
        <Stack gap={6}>
          <H2>{`${selected}: daily news sentiment vs close`}</H2>
          <GuideChart
            categories={sentiment.map((r) => r.session)}
            series={[{ name: "sentiment", data: sentiment.map((r) => r.sentiment) }]}
            kind="bar"
            baselines={[0]}
            symmetricFloor={0.25}
            height={340}
            yLabel="sentiment"
            overlay={
              sentiment.some((r) => isNum(r.close))
                ? { name: `${selected} close`, label: "close (USD)", data: sentiment.map((r) => r.close ?? null) }
                : undefined
            }
          />
          <Caption>{`Left Y: confidence-weighted sentiment (-1..+1, zoomed around 0; no bar = no scored news) · Right Y: adjusted close (USD) · X: ET trading session · Source: Alpaca News (Benzinga) scored by agent, Alpaca daily bars`}</Caption>
        </Stack>
      )}
    </Stack>
  );
}
