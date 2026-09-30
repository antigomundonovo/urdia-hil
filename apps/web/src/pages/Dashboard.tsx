import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, Opportunity } from "../api";
import { useProfile } from "../profile";

const ATTENTION = new Set([
  "NEEDS_RESEARCH", "QUARANTINED", "BLOCKED", "RIGHTS_BLOCKED",
  "FACT_CHECK_FAILED", "REJECTED", "DUPLICATE",
]);

export default function Dashboard() {
  const { profile, workspaceId } = useProfile();
  const { data } = useQuery({
    queryKey: ["dashboard", workspaceId],
    enabled: !!workspaceId,
    queryFn: () =>
      api.get<{ opportunities: Opportunity[] }>(
        `/api/v1/profiles/${profile?.id}/opportunities?workspace_id=${workspaceId}`
      ),
  });

  const opportunities = data?.opportunities ?? [];
  const needsAttention = opportunities.filter((o) => ATTENTION.has(o.state));
  const inFlight = opportunities.filter(
    (o) => !ATTENTION.has(o.state) && o.state !== "READY" && o.state !== "PUBLISHED"
  );
  const ready = opportunities.filter((o) => o.state === "READY");
  const published = opportunities.filter((o) => o.state === "PUBLISHED" || o.state === "LEARNING");

  const card = "rounded-lg border border-stone-200 bg-white p-5";
  return (
    <div className="space-y-6">
      <section>
        <h2 className="font-serif text-2xl font-bold">O que está acontecendo?</h2>
        <p className="mt-1 text-sm text-stone-500">
          As sete perguntas do Documento 06 — respondidas com o estado real do sistema.
        </p>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <div className={card}>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-red-700">
            O que precisa de atenção? ({needsAttention.length})
          </h3>
          <OpportunityLines items={needsAttention} empty="Nada parado — bom sinal." />
        </div>
        <div className={card}>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-amber-700">
            Em andamento ({inFlight.length})
          </h3>
          <OpportunityLines items={inFlight} empty="Nenhuma investigação aberta." />
        </div>
        <div className={card}>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-green-700">
            Pronto para revisão humana ({ready.length})
          </h3>
          <OpportunityLines items={ready} empty="Nada aguardando sua decisão." />
        </div>
        <div className={card}>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-600">
            Publicados / medindo ({published.length})
          </h3>
          <OpportunityLines items={published} empty="Nada publicado ainda." />
        </div>
      </div>

      <section className={card}>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-600">
          Como o sistema está?
        </h3>
        <Health />
      </section>
    </div>
  );
}

function OpportunityLines({ items, empty }: { items: Opportunity[]; empty: string }) {
  if (items.length === 0) return <p className="mt-3 text-sm text-stone-400">{empty}</p>;
  return (
    <ul className="mt-3 space-y-2">
      {items.slice(0, 5).map((o) => (
        <li key={o.id}>
          <Link to={`/oportunidades/${o.id}`} className="text-sm text-stone-800 hover:text-amber-800">
            {o.title}
          </Link>
          <span className="ml-2 rounded bg-stone-100 px-2 py-0.5 text-xs text-stone-500">{o.state}</span>
        </li>
      ))}
    </ul>
  );
}

function Health() {
  const { data } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<{ status: string; app_env: string }>("/api/v1/health"),
  });
  if (!data) return <p className="mt-2 text-sm text-stone-400">verificando…</p>;
  return (
    <p className="mt-2 text-sm">
      Servidor:{" "}
      <span
        className={`font-semibold ${
          data.status === "HEALTHY" ? "text-green-700" : "text-amber-700"
        }`}
      >
        {data.status}
      </span>{" "}
      · ambiente {data.app_env}
    </p>
  );
}
