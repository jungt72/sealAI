/**
 * Website Guide classifier — deterministic, NO LLM.
 *
 * The guide only answers questions ABOUT sealingAI (the platform). It must never
 * perform seal design, recommend materials/manufacturers, or evaluate a concrete
 * application. Any question that looks like a concrete technical sealing question
 * is deflected to the free analysis via a fixed guardrail answer.
 */

export interface GuideFaq {
  question: string;
  answer: string;
}

export interface GuideResolution {
  isGuardrail: boolean;
  answer: string;
  /** Index into the FAQ list when a platform FAQ matched, else null. */
  matchedFaqIndex: number | null;
}

// Signals of a concrete technical sealing question (→ deflect to analysis).
const TECHNICAL_PATTERNS: RegExp[] = [
  /welche[rs]?\s+(dichtung|werkstoff|material|o-?ring|rwdr|dichtungen)/i,
  /\bempfehl/i,
  /\bempfiehlst\b/i,
  /\bgeeignet\b/i,
  /\bauslegen\b|\bauslegung\b/i,
  /\d+\s*(°|grad)\s*c/i,
  /\d+\s*bar\b/i,
  /\d+\s*u\/?min|\d+\s*rpm/i,
  /\b(ptfe|fkm|viton|epdm|nbr|hnbr|ffkm|silikon|vmq)\b/i,
  /hydrauliköl|kraftstoff|kühlmittel|kältemittel|bremsflüssigkeit/i,
  /welches\s+material/i,
  /soll ich .*(nehmen|verwenden|einsetzen|wählen)/i,
];

// Platform-question keywords → best-effort FAQ routing (order = priority).
const FAQ_KEYWORDS: { index: number; keywords: RegExp }[] = [
  { index: 2, keywords: /neutral|käuflich|unabhängig|kaufen/i },
  { index: 1, keywords: /login|anmeld|konto|danach|nach dem/i },
  { index: 3, keywords: /hersteller.*(hilf|nutzen|vorteil)|für hersteller|rfq|anfrage.*hersteller/i },
  { index: 4, keywords: /partner werden|herstellerpartner|partnerprogramm/i },
  { index: 0, keywords: /warum|nutzen|vorteil|wozu|was bringt|unterschied|katalog/i },
];

export function isTechnicalSealQuestion(query: string): boolean {
  const q = query.trim();
  if (q.length === 0) return false;
  return TECHNICAL_PATTERNS.some((re) => re.test(q));
}

export function resolveGuideAnswer(
  query: string,
  faq: GuideFaq[],
  guardrailAnswer: string,
): GuideResolution {
  if (isTechnicalSealQuestion(query)) {
    return { isGuardrail: true, answer: guardrailAnswer, matchedFaqIndex: null };
  }
  for (const { index, keywords } of FAQ_KEYWORDS) {
    if (index < faq.length && keywords.test(query)) {
      return { isGuardrail: false, answer: faq[index].answer, matchedFaqIndex: index };
    }
  }
  // Default: explain the platform via the primary "why" answer.
  return { isGuardrail: false, answer: faq[0]?.answer ?? guardrailAnswer, matchedFaqIndex: faq.length ? 0 : null };
}
