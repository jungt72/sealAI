export function HeroMotionBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden" aria-hidden="true" data-testid="hero-motion-background">
      <div
        data-testid="hero-motion-image"
        className="sealai-hero-motion absolute inset-[-2%] bg-[url('/images/marketing/hero-background.png')] bg-cover bg-[position:center_top] will-change-transform"
      />
      <div
        data-testid="hero-motion-sheen"
        className="sealai-hero-sheen absolute inset-0 bg-[linear-gradient(112deg,transparent_0%,rgba(255,255,255,0.34)_44%,transparent_62%)]"
      />
      <div className="absolute inset-0 bg-white/35" />
    </div>
  );
}
