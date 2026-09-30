import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { useProfile } from "../profile";

interface LearningState {
  experiments: { id: string; hypothesis: string | null; status: string; decision: string | null }[];
  rules: { id: string; statement: string; status: string }[];
}

export default function Learning() {
  const { profile, workspaceId } = useProfile();
  const queryClient = useQueryClient();
  const [statement, setStatement] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: ["learning", workspaceId, profile?.id],
    enabled: !!workspaceId && !!profile?.id,
    queryFn: () =>
      api.get<LearningState>(
        `/api/v1/learning?workspace_id=${workspaceId}&profile_id=${profile?.id}`
      ),
  });

  const propose = useMutation({
    mutationFn: () =>
      api.post(`/api/v1/learning/rules?workspace_id=${workspaceId}&profile_id=${profile?.id}`, {
        statement,
      }),
    onSuccess: () => {
      setStatement("");
      setMessage("Regra proposta como CANDIDATE — só ativa após revisão humana.");
      queryClient.invalidateQueries({ queryKey: ["learning"] });
    },
    onError: (e) => setMessage((e as Error).message),
  });

  const review = useMutation({
    mutationFn: (ruleId: string) =>
      api.post(`/api/v1/learning/rules/${ruleId}/review?workspace_id=${workspaceId}&profile_id=${profile?.id}`, {
        notes: "revisado na interface",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["learning"] }),
  });

  const activate = useMutation({
    mutationFn: (ruleId: string) =>
      api.post(`/api/v1/learning/rules/${ruleId}/activate?workspace_id=${workspaceId}&profile_id=${profile?.id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["learning"] }),
    onError: (e) => setMessage((e as Error).message),
  });

  const card = "rounded-lg border border-stone-200 bg-white p-5";
  return (
    <div className="space-y-6">
      <h2 className="font-serif text-2xl font-bold">Learning</h2>
      <p className="text-sm text-stone-500">
        Pipeline do Documento 15: dado → experiência → hipótese → experimento →
        resultado → regra candidata → <strong>revisão humana</strong> → regra ativa.
      </p>

      <section className={card}>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Propor regra candidata
        </h3>
        <div className="mt-3 flex gap-2">
          <input
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            placeholder="ex.: carrossel com pergunta no slide 1 retém mais"
            className="flex-1 rounded border border-stone-300 px-3 py-2 text-sm"
          />
          <button
            onClick={() => propose.mutate()}
            disabled={!statement || propose.isPending}
            className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40"
          >
            Propor
          </button>
        </div>
        {message && <p className="mt-3 text-sm text-stone-600">{message}</p>}
      </section>

      <section className={card}>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Regras ({data?.rules.length ?? 0})
        </h3>
        <ul className="mt-3 space-y-3">
          {(data?.rules ?? []).map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-4 border-b border-stone-100 pb-3">
              <div>
                <p className="text-sm text-stone-800">{r.statement}</p>
                <span
                  className={`mt-1 inline-block rounded px-2 py-0.5 text-xs font-medium ${
                    r.status === "ACTIVE"
                      ? "bg-green-100 text-green-800"
                      : r.status === "REVIEWED"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-stone-100 text-stone-600"
                  }`}
                >
                  {r.status}
                </span>
              </div>
              <div className="flex gap-2">
                {r.status === "CANDIDATE" && (
                  <button
                    onClick={() => review.mutate(r.id)}
                    className="rounded border border-stone-300 px-3 py-1.5 text-xs font-medium hover:bg-stone-50"
                  >
                    Registrar revisão
                  </button>
                )}
                {r.status === "REVIEWED" && (
                  <button
                    onClick={() => activate.mutate(r.id)}
                    className="rounded bg-green-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-800"
                  >
                    Ativar
                  </button>
                )}
              </div>
            </li>
          ))}
          {data?.rules.length === 0 && (
            <li className="text-sm text-stone-400">Nenhuma regra ainda.</li>
          )}
        </ul>
      </section>
    </div>
  );
}
