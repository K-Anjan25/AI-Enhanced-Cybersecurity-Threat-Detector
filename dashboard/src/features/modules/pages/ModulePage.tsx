import { useLocation } from "react-router-dom";
import FuturePhasesPage, { type Tab as FutureTab } from "../../advanced/pages/FuturePhasesPage";
import NextPhasesPage, { type Tab as NextTab } from "../../advanced/pages/NextPhasesPage";
import AdvancedHubPage from "../../advanced/pages/AdvancedHubPage";

/**
 * Several nav entries share a tabbed hub page rather than having a page each.
 *
 * Jakob's Law: people expect a navigation item to land on the thing it names.
 * Previously every one of these routes opened its hub on the hub's *first*
 * tab — clicking "Vulnerabilities" showed ZTNA, and clicking "Forensics"
 * showed ITDR. The route now selects the matching tab, so the destination
 * always matches the label the operator clicked.
 */

const NEXT_TABS: Record<string, NextTab> = {
  "/ztna": "ztna",
  "/hunting": "hunt",
  "/vulns": "vuln",
  "/ai-agent": "agent",
};

const FUTURE_TABS: Record<string, FutureTab> = {
  "/itdr": "itdr",
  "/cspm": "cspm",
  "/sbom": "sbom",
  "/deception": "deception",
  "/forensics": "forensics",
  "/tip": "tip",
  "/compliance-continuous": "compliance",
  "/exec-risk": "exec",
};

const matchPrefix = <T,>(path: string, table: Record<string, T>): T | undefined => {
  const key = Object.keys(table).find((p) => path === p || path.startsWith(`${p}/`));
  return key ? table[key] : undefined;
};

export default function ModulePage() {
  const path = useLocation().pathname;

  const nextTab = matchPrefix(path, NEXT_TABS);
  if (nextTab) return <NextPhasesPage initialTab={nextTab} />;

  const futureTab = matchPrefix(path, FUTURE_TABS);
  if (futureTab) return <FuturePhasesPage initialTab={futureTab} />;

  if (path.startsWith("/threat-intel") || path.startsWith("/attack-navigator")) {
    return <AdvancedHubPage />;
  }

  return <div className="p-6 text-sm text-content-secondary">Module {path} — view in Advanced Hub</div>;
}
