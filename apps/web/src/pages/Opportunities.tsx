import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, Opportunity } from "../api";
import { useProfile } from "../profile";

export default function Opportunities() {
  const { profile, workspaceId } = useProfile();
  const { data, isLoading } = useQuery({
    queryKey: ["opportunities", workspaceId],
    enabled: !!workspaceId,
    queryFn: () =>
      api.get<{ opportunities: Opportunity[] }>(
        `/api/v1/profiles/${profile?.id}/opportunities?workspace_id=${workspaceId}`
      ),
  });

  return (
    <div className="space-y-4">
      <h2 className="font-serif text-2xl font-bold">Oportunidades</h2>
      {isLoading && <p className="text-sm text-stone-400">carregando…</p>}
      <div className="overflow-hidden rounded-lg border border-stone-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-stone-100 text-left text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-4 py-3">Título</th>
              <th className="px-4 py-3">Estado</th>
              <th className="px-4 py-3">Decisão JEV</th>
              <th className="px-4 py-3">Prioridade</th>
            </tr>
          </thead>
          <tbody>
            {(data?.opportunities ?? []).map((o) => (
              <tr key={o.id} className="border-t border-stone-100 hover:bg-amber-50/50">
                <td className="px-4 py-3">
                  <Link to={`/oportunidades/${o.id}`} className="font-medium text-stone-800 hover:text-amber-800">
                    {o.title}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <StateBadge state={o.state} />
                </td>
                <td className="px-4 py-3 text-stone-600">{o.decision ?? "—"}</td>
                <td className="px-4 py-3 text-stone-600">{o.priority ?? "—"}</td>
              </tr>
            ))}
            {data?.opportunities.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-stone-400">
                  Nenhuma oportunidade ainda — cadastre fontes e rode o radar.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function StateBadge({ state }: { state: string }) {
  const styles: Record<string, string> = {
    READY: "bg-green-100 text-green-800",
    PUBLISHED: "bg-blue-100 text-blue-800",
    REJECTED: "bg-red-100 text-red-800",
    QUARANTINED: "bg-orange-100 text-orange-800",
    NEEDS_RESEARCH: "bg-amber-100 text-amber-800",
    RIGHTS_BLOCKED: "bg-red-100 text-red-800",
  };
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${styles[state] ?? "bg-stone-100 text-stone-600"}`}>
      {state}
    </span>
  );
}
