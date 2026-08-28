import React from "react";
import LandingNav from "../../../components/landing/LandingNav";
import LandingHero from "../../../components/landing/LandingHero";
import TrustBar from "../../../components/landing/TrustBar";
import FeatureGrid from "../../../components/landing/FeatureGrid";
import ConsoleDemo from "../../../components/landing/ConsoleDemo";
import FinalCTA from "../../../components/landing/FinalCTA";

/**
 * Landing — the NOCTRA Signal marketing surface, ported from newfile.html
 * (the Canva export of noctradesign.my.canva.site):
 *
 *   blur header (signal-dot brand) → hero with HUD-bracketed topology →
 *   coverage stats band → interactive console demo (metrics + prioritized
 *   events + scan radar) → intelligence features → access panel → footer.
 *
 * The page is the ink canvas by design (night + noctra-canvas): the grid
 * texture, glows and signal green are the brand, not a theme choice.
 */
const LandingPage: React.FC = () => (
  <div className="night noctra-canvas flex min-h-screen flex-col font-sans text-content-primary">
    <LandingNav />

    <main className="flex-1">
      <LandingHero />
      <TrustBar />
      <ConsoleDemo />
      <FeatureGrid />
      <FinalCTA />
    </main>
  </div>
);

export default LandingPage;
