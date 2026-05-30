export function HeroMotionBackground() {
  return (
    <div
      className="absolute inset-0 overflow-hidden"
      aria-hidden="true"
      data-testid="hero-motion-background"
    >
      <div
        data-testid="hero-motion-image"
        className="sealai-hero-motion absolute inset-[-2%] bg-[url('/images/marketing/hero-background.png')] bg-cover bg-[position:center_center] will-change-transform"
      />
      <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.86)_0%,rgba(255,255,255,0.72)_34%,rgba(255,255,255,0.46)_63%,rgba(255,255,255,0.18)_100%)]" />
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.18)_0%,rgba(255,255,255,0.22)_46%,rgba(255,255,255,0.58)_100%)]" />
      <div
        data-testid="hero-motion-sheen"
        className="sealai-hero-sheen absolute inset-0 bg-[linear-gradient(112deg,transparent_0%,rgba(255,255,255,0.28)_44%,transparent_62%)]"
      />
    </div>
  );
}
