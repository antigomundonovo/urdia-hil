import { useQuery } from "@tanstack/react-query";
import { api, Job } from "../api";
import { useProfile } from "../profile";

const ACTIVE_STATUSES = new Set(["PENDING", "RUNNING"]);

function duration(job: Job): string {
  if (!job.started_at) return "—";
  const start = Date.parse(job.started_at);
  const end = job.finished_at ? Date.parse(job.finished_at) : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "—";
  const seconds = Math.floor((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function timestamp(value: string | null): string {
  if (!value) return "—";
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(parsed).toLocaleString() : "—";
}

function statusStyle(status: string): string {
  if (status === "SUCCEEDED") return "bg-green-100 text-green-800";
  if (status === "FAILED") return "bg-red-100 text-red-800";
  if (status === "RUNNING") return "bg-amber-100 text-amber-900";
  if (status === "CANCELLED") return "bg-stone-200 text-stone-700";
  return "bg-blue-100 text-blue-800";
}

export default function Jobs() {
  const { profile, workspaceId } = useProfile();
  const { data, error, isPending, isError } = useQuery({
    queryKey: ["jobs", workspaceId, profile?.id],
    enabled: !!workspaceId && !!profile?.id,
    queryFn: () =>
      api.get<{ jobs: Job[] }>(
        `/api/v1/jobs?workspace_id=${workspaceId}&profile_id=${profile?.id}`
      ),
    refetchInterval: (query) =>
      query.state.data?.jobs.some((job) => ACTIVE_STATUSES.has(job.status)) ? 2000 : 15000,
  });

  const jobs = data?.jobs ?? [];
  const card = "rounded-lg border border-stone-200 bg-white";

  return (
    <div className="space-y-6">
      <section>
        <h2 className="font-serif text-2xl font-bold">Jobs</h2>
        <p className="mt-1 text-sm text-stone-500">
          Execuções do perfil, checkpoints e falhas. Atualiza a cada 2 segundos enquanto
          houver jobs em fila ou execução.
        </p>
      </section>

      {isError && (
        <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          Não foi possível carregar os jobs: {(error as Error).message}
        </p>
      )}

      <section className={`${card} overflow-hidden`} aria-label="Lista de jobs">
        <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
            Execuções recentes
          </h3>
          <span className="text-xs text-stone-400">{jobs.length} jobs</span>
        </div>

        {isPending ? (
          <p className="p-5 text-sm text-stone-400">Carregando jobs…</p>
        ) : jobs.length === 0 ? (
          <p className="p-5 text-sm text-stone-400">Nenhum job registrado para este perfil.</p>
        ) : (
          <ul className="divide-y divide-stone-100">
            {jobs.map((job) => {
              const completed = job.checkpoint?.completed_steps ?? [];
              return (
                <li key={job.id} className="space-y-3 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="font-medium text-stone-800">{job.job_type}</p>
                      <p className="font-mono text-xs text-stone-400">{job.id}</p>
                    </div>
                    <span className={`rounded px-2 py-1 text-xs font-semibold ${statusStyle(job.status)}`}>
                      {job.status}
                    </span>
                  </div>

                  <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
                    <div>
                      <dt className="text-xs text-stone-400">Progresso</dt>
                      <dd className="text-stone-700">
                        {completed.length ? completed.join(" → ") : "Aguardando início"}
                        {job.checkpoint?.next_step && (
                          <span> → <strong>{job.checkpoint.next_step}</strong></span>
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-stone-400">Tentativa</dt>
                      <dd className="text-stone-700">
                        {job.attempt ?? 0} / {job.max_attempts ?? "padrão"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-stone-400">Duração</dt>
                      <dd className="text-stone-700">{duration(job)}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-stone-400">Criado</dt>
                      <dd className="text-stone-700">{timestamp(job.created_at)}</dd>
                    </div>
                  </dl>

                  {job.error && (
                    <p className="break-words rounded bg-red-50 px-3 py-2 text-sm text-red-800">
                      <strong>Erro:</strong> {job.error.slice(0, 500)}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
