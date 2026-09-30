import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { useState } from "react";
import { api, Opportunity, QcResult } from "../api";
import { useProfile } from "../profile";
import { StateBadge } from "./Opportunities";

export default function OpportunityDetail() {
  const { id } = useParams();
  const { workspaceId } = useProfile();
  const queryClient = useQueryClient();
  const [platform, setPlatform] = useState("instagram");
  const [qc, setQc] = useState<QcResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const { data: opp } = useQuery({
    queryKey: ["opportunity", id, workspaceId],
    enabled: !!workspaceId && !!id,
    queryFn: () =>
      api.get<Opportunity>(`/api/v1/opportunities/${id}?workspace_id=${workspaceId}`),
  });

  const runQc = useMutation({
    mutationFn: () =>
      api.post<QcResult>(`/api/v1/opportunities/${id}/run-qc?workspace_id=${workspaceId}`),
  });
  const approve = useMutation({
    mutationFn: () =>
      api.post<{ state: string }>(`/api/v1/opportunities/${id}/approve?workspace_id=${workspaceId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["opportunity", id] });
      setMessage("Aprovado — registrado no cartório.");
    },
  });
  const reject = useMutation({
    mutationFn: () =>
      api.post<{ state: string }>(`/api/v1/opportunities/${id}/reject?workspace_id=${workspaceId}`, {
        reason: "rejeitado na revisão humana",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["opportunity", id] });
      setMessage("Rejeitado — registrado no cartório.");
    },
  });

  if (!opp) return <p className="text-sm text-stone-400">carregando…</p>;

  const row = "flex items-start justify-between gap-4 border-b border-stone-100 py-3";

  return (
    <div className="space-y-6">
      <Link to="/oportunidades" className="text-sm text-stone-500 hover:text-amber-800">
        ← Oportunidades
      </Link>
      <div className="flex items-center gap-3">
        <h2 className="font-serif text-2xl font-bold">{opp.title}</h2>
        <StateBadge state={opp.state} />
      </div>

      <section className="rounded-lg border border-stone-200 bg-white p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Why Panel (Documento 06)
        </h3>
        <div className="mt-3">
          <div className={row}>
            <span className="text-sm font-medium text-stone-500">Por que agora?</span>
            <span className="text-right text-sm">{opp.why_now ?? "—"}</span>
          </div>
          <div className={row}>
            <span className="text-sm font-medium text-stone-500">Por que o ANM?</span>
            <span className="text-right text-sm">{opp.why_profile ?? "—"}</span>
          </div>
          <div className={row}>
            <span className="text-sm font-medium text-stone-500">Decisão do JEV</span>
            <span className="text-right text-sm">
              {opp.decision ?? "—"} {opp.decision_reason ? `· ${opp.decision_reason}` : ""}
            </span>
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-stone-200 bg-white p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Revisão humana (Documento 00 §22)
        </h3>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            onClick={() => approve.mutate()}
            disabled={approve.isPending}
            className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white hover:bg-green-800 disabled:opacity-50"
          >
            APROVAR
          </button>
          <button
            onClick={() => reject.mutate()}
            disabled={reject.isPending}
            className="rounded bg-red-700 px-4 py-2 text-sm font-medium text-white hover:bg-red-800 disabled:opacity-50"
          >
            REJEITAR
          </button>
          <input
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            className="w-40 rounded border border-stone-300 px-3 py-2 text-sm"
            placeholder="plataforma"
          />
          <button
            onClick={() => runQc.mutate()}
            className="rounded border border-stone-300 px-4 py-2 text-sm font-medium hover:bg-stone-50"
          >
            Rodar QC
          </button>
        </div>
        {message && <p className="mt-3 text-sm text-green-700">{message}</p>}
        {runQc.isError && (
          <p className="mt-3 text-sm text-red-700">
            QC indisponível para esta oportunidade: {(runQc.error as Error).message.slice(0, 140)}
          </p>
        )}
        {qc && (
          <div className="mt-4 grid gap-1 text-sm" data-testid="qc-gates">
            {Object.entries(qc.gates).map(([gate, result]) => (
              <div key={gate} className="flex justify-between border-b border-stone-50 py-1">
                <span className="text-stone-600">{gate}</span>
                <span
                  className={
                    result === "PASS"
                      ? "font-medium text-green-700"
                      : result === "FAIL"
                        ? "font-medium text-red-700"
                        : "font-medium text-amber-700"
                  }
                >
                  {result}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
