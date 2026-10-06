/**
 * The overview's name for the shared chart palette reader.
 *
 * The reader itself lives in `src/components/charts/palette.ts`: the traffic
 * explorer needs it too (T-406), and a feature may not import another feature, so
 * the shared half moved down a layer. This re-export keeps the overview's own
 * modules — and its tests — reading it from where they always have.
 */
export {
  CHART_VARIABLES,
  SEVERITY_VARIABLES,
  readPalette,
  useChartPalette,
  useThemeRevision,
} from '../../components/charts/palette';
export type { ChartPalette } from '../../components/charts/palette';
