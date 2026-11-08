const FORMAT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function formatCount(value: number): string {
  return FORMAT.format(Math.round(value));
}
