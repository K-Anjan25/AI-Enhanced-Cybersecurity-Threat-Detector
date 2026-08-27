import React from "react";
import LandingNav from "../../../components/landing/LandingNav";
import LandingHero from "../../../components/landing/LandingHero";
import TrustBar from "../../../components/landing/TrustBar";
import FeatureGrid from "../../../components/landing/FeatureGrid";
import HowItWorks from "../../../components/landing/HowItWorks";
import FinalCTA from "../../../components/landing/FinalCTA";

/**
 * Landing — WordPress/WooCommerce-grade marketing surface, rebuilt per
 * docs/frontend-commercial-redesign.md:
 *
 *   sticky nav (hide-on-scroll) → hero with real product preview → proof
 *   strip (real test numbers) → feature bento → how-it-works timeline →
 *   trust panel + final CTA → multi-column footer.
 *
 * Every claim is true of the product today. No fabricated metrics, no stock
 * art — the product preview is built in CSS from real case language.
 */
const LandingPage: React.FC = () => (
  <div className="min-h-screen bg-app-bg text-content-primary flex flex-col font-sans">
    <LandingNav />

    <main className="flex-1">
      <LandingHero />
      <TrustBar />
      <FeatureGrid />
      <HowItWorks />
      <FinalCTA />
    </main>
  </div>
);

export default LandingPage;
