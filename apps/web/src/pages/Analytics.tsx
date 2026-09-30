import { useQuery } from "@tanstack/react-query";
import { api, CommentItem } from "../api";
import { useProfile } from "../profile";

export default function Analytics() {
  const { profile, workspaceId } = useProfile();
  const { data: overview } = useQuery({
    queryKey: ["overview", workspaceId, profile?.id],
    enabled: !!workspaceId && !!profile?.id,
    queryFn: () =>
      api.get<{ publications: number; by_status: Record<string, number>; totals: Record<string, number> }>(
        `/api/v1/analytics/overview?workspace_id=${workspaceId}&profile_id=${profile?.id}`
      ),
  });
  const { data: comments } = useQuery({
    queryKey: ["comments", workspaceId, profile?.id],
    enabled: !!workspaceId && !!profile?.id,
    queryFn: () =>
      api.get<{ comments: CommentItem[] }>(
        `/api/v1/analytics/comments?workspace_id=${workspaceId}&profile_id=${profile?.id}`
      ),
  });

  const card = "rounded-lg border border-stone-200 bg-white p-5";
  return (
    <div className="space-y-6">
      <h2 className="font-serif text-2xl font-bold">Analytics</h2>

      <div className="grid gap-4 md:grid-cols-2">
        <div className={card}>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
            Visão geral (última coleta por post — histórico intacto)
          </h3>
          {overview && Object.keys(overview.totals).length > 0 ? (
            <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
              {Object.entries(overview.totals).map(([metric, value]) => (
                <div key={metric} className="rounded bg-stone-50 px-3 py-2">
                  <p className="text-xs text-stone-400">{metric}</p>
                  <p className="font-semibold">{value}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-stone-400">
              {overview
                ? "Sem métricas ainda — publique e colete métricas."
                : "carregando…"}
            </p>
          )}
        </div>

        <div className={card}>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
            Sinais qualificados da audiência (Doc 15)
          </h3>
          <ul className="mt-3 space-y-2 text-sm">
            {(comments?.comments ?? [])
              .filter((c) => c.qualified_signal)
              .slice(0, 8)
              .map((c) => (
                <li key={c.id} className="rounded bg-amber-50 px-3 py-2">
                  <span className="mr-2 rounded bg-amber-200 px-2 py-0.5 text-xs font-medium text-amber-900">
                    {c.qualified_signal}
                  </span>
                  <span className="text-stone-700">{c.text}</span>
                </li>
              ))}
            {comments && comments.comments.filter((c) => c.qualified_signal).length === 0 && (
              <li className="text-stone-400">Nenhum sinal qualificado ainda.</li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
