"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ClipboardCheck, ListChecks, ShieldCheck, Target } from "lucide-react";

const EXAMPLES = [
  "SEO-Daten aus GSC und DataForSEO auswerten und die nächsten Content-Prioritäten ableiten.",
  "Einen Dichtungsfall strukturiert klären: Medium, Temperatur, Druck, Bewegung und offene Angaben.",
  "Die Website so prüfen, dass technische SEO, Conversion und Markenwirkung zusammenpassen.",
];

function composeGoal({
  goal,
  context,
  output,
  constraints,
}: {
  goal: string;
  context: string;
  output: string;
  constraints: string;
}) {
  const parts = [
    `Goal: ${goal.trim()}`,
    context.trim() ? `Kontext: ${context.trim()}` : null,
    output.trim() ? `Gewünschtes Ergebnis: ${output.trim()}` : null,
    constraints.trim() ? `Grenzen / Leitplanken: ${constraints.trim()}` : null,
    "Bitte gehe präzise vor, prüfe Annahmen und setze das Ziel end-to-end um.",
  ];

  return parts.filter(Boolean).join("\n\n");
}

export default function GoalForm() {
  const router = useRouter();
  const [goal, setGoal] = useState("");
  const [context, setContext] = useState("");
  const [output, setOutput] = useState("");
  const [constraints, setConstraints] = useState("");

  const prompt = useMemo(
    () => composeGoal({ goal, context, output, constraints }),
    [constraints, context, goal, output],
  );
  const canSubmit = Boolean(goal.trim());

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[#F7F9FC]">
      <div className="border-b border-[#E7ECF3] bg-white px-6 py-5">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-[14px] bg-[#EEF4FF] text-[#0B5BD3]">
            <Target size={20} />
          </span>
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-[#111827]">Goal setzen</h1>
            <p className="mt-1 text-sm text-[#6B7280]">
              Formuliere den Auftrag einmal sauber, dann übernehme ich ihn strukturiert in den Chat.
            </p>
          </div>
        </div>
      </div>

      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto p-5">
        <div className="mx-auto grid max-w-6xl gap-5 xl:grid-cols-[minmax(0,1fr),360px]">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (!canSubmit) return;
              router.push(`/dashboard/new?goal=${encodeURIComponent(prompt)}`);
            }}
            className="space-y-4 rounded-[20px] border border-[#E7ECF3] bg-white p-5 shadow-sm"
          >
            <Field
              icon={Target}
              label="Goal"
              required
              value={goal}
              placeholder="Was soll konkret erreicht werden?"
              onChange={setGoal}
            />
            <Field
              icon={ClipboardCheck}
              label="Kontext"
              value={context}
              placeholder="Welche Dateien, Domains, Datenquellen, Entscheidungen oder Randbedingungen sind wichtig?"
              onChange={setContext}
            />
            <Field
              icon={ListChecks}
              label="Gewünschtes Ergebnis"
              value={output}
              placeholder="Zum Beispiel: Deploy, Audit, Liste mit Prioritäten, Code-Änderung, Report oder Entscheidungsvorlage."
              onChange={setOutput}
            />
            <Field
              icon={ShieldCheck}
              label="Grenzen / Leitplanken"
              value={constraints}
              placeholder="Was soll nicht passieren? Welche Risiken, Tonalität, Budgets oder Freigaben soll ich beachten?"
              onChange={setConstraints}
            />

            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
              <p className="text-xs text-[#6B7280]">
                Der Text wird nicht automatisch gesendet. Du kannst ihn im Chat noch anpassen.
              </p>
              <button
                type="submit"
                disabled={!canSubmit}
                className="inline-flex items-center gap-2 rounded-full bg-[#0B5BD3] px-5 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[#0A4FB9] disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
              >
                Goal in Chat übernehmen
                <ArrowRight size={17} />
              </button>
            </div>
          </form>

          <aside className="space-y-4">
            <div className="rounded-[20px] border border-[#E7ECF3] bg-white p-5 shadow-sm">
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                Vorschau
              </div>
              <pre className="mt-3 max-h-[360px] whitespace-pre-wrap rounded-[14px] bg-[#F8FAFD] p-4 text-xs leading-5 text-[#374151]">
                {prompt}
              </pre>
            </div>

            <div className="rounded-[20px] border border-[#E7ECF3] bg-white p-5 shadow-sm">
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                Beispiele
              </div>
              <div className="mt-3 space-y-2">
                {EXAMPLES.map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => setGoal(example)}
                    className="w-full rounded-[14px] border border-[#E7ECF3] bg-white px-3 py-2.5 text-left text-sm leading-5 text-[#374151] transition-colors hover:border-[#CFE0FF] hover:bg-[#F8FBFF]"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function Field({
  icon: Icon,
  label,
  onChange,
  placeholder,
  required,
  value,
}: {
  icon: typeof Target;
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  required?: boolean;
  value: string;
}) {
  return (
    <label className="block">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#111827]">
        <Icon size={16} className="text-[#0B5BD3]" />
        {label}
        {required && <span className="text-[#0B5BD3]">*</span>}
      </div>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        rows={label === "Goal" ? 3 : 4}
        className="min-h-[96px] w-full resize-y rounded-[14px] border border-[#DDE5F0] bg-white px-4 py-3 text-sm leading-6 text-[#111827] outline-none transition-colors placeholder:text-[#9CA3AF] focus:border-[#0B5BD3] focus:ring-4 focus:ring-[#0B5BD3]/10"
      />
    </label>
  );
}
