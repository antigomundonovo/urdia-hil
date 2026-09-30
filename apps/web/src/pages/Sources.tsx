import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, Source } from "../api";
import { useProfile } from "../profile";

const SOURCE_TYPES = [
  "rss", "atom", "sitemap", "search", "gdelt", "wikidata", "wikipedia",
  "openalex", "crossref", "wayback", "internet_archive", "wikimedia",
];

export default function Sources() {
  const { profile, workspaceId } = useProfile();
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [type, setType] = useState("rss");
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: ["sources", workspaceId, profile?.id],
    enabled: !!workspaceId && !!profile?.id,
    queryFn: () =>
      api.get<{ sources: Source[] }>(
        `/api/v1/profiles/${profile?.id}/sources?workspace_id=${workspaceId}`
      ),
  });

  const create = useMutation({
    mutationFn: () =>
      api.post(`/api/v1/profiles/${profile?.id}/sources?workspace_id=${workspaceId}`, {
        url, source_type: type, title: title || null,
      }),
    onSuccess: () => {
      setUrl("");
      setTitle("");
      setMessage("Fonte cadastrada.");
      queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
    onError: (e) => setMessage((e as Error).message),
  });

  const retrieve = useMutation({
    mutationFn: (sourceId: string) =>
      api.post<{ job_id: string; status: string }>(
        `/api/v1/sources/${sourceId}/retrieve?workspace_id=${workspaceId}`
      ),
    onSuccess: (r) => setMessage(`Radar disparado — job ${r.job_id.slice(0, 8)}… em fila (${r.status}).`),
    onError: (e) => setMessage((e as Error).message),
  });

  return (
    <div className="space-y-6">
      <h2 className="font-serif text-2xl font-bold">Fontes</h2>

      <section className="rounded-lg border border-stone-200 bg-white p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Cadastrar fonte (Documento 09 — source programs)
        </h3>
        <div className="mt-3 flex flex-wrap gap-2">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://exemplo.com/feed.xml"
            className="min-w-72 flex-1 rounded border border-stone-300 px-3 py-2 text-sm"
          />
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="nome (opcional)"
            className="w-56 rounded border border-stone-300 px-3 py-2 text-sm"
          />
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="rounded border border-stone-300 px-3 py-2 text-sm"
          >
            {SOURCE_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <button
            onClick={() => create.mutate()}
            disabled={!url || create.isPending}
            className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40"
          >
            Cadastrar
          </button>
        </div>
        {message && <p className="mt-3 text-sm text-stone-600">{message}</p>}
      </section>

      <div className="overflow-hidden rounded-lg border border-stone-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-stone-100 text-left text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-4 py-3">Fonte</th>
              <th className="px-4 py-3">Tipo</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {(data?.sources ?? []).map((s) => (
              <tr key={s.id} className="border-t border-stone-100">
                <td className="px-4 py-3">
                  <p className="font-medium text-stone-800">{s.title ?? s.url}</p>
                  <p className="text-xs text-stone-400">{s.url}</p>
                </td>
                <td className="px-4 py-3 text-stone-600">{s.source_type}</td>
                <td className="px-4 py-3 text-stone-600">{s.status}</td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => retrieve.mutate(s.id)}
                    disabled={retrieve.isPending}
                    className="rounded border border-amber-700 px-3 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-50 disabled:opacity-40"
                  >
                    Varrer agora
                  </button>
                </td>
              </tr>
            ))}
            {data?.sources.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-stone-400">
                  Nenhuma fonte ainda — comece com um RSS (ex.: Agência Brasil).
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-stone-400">
        O varredor respeita robots.txt, limita tamanho e tempo, e bloqueia endereços
        internos — Documento 08/09.
      </p>
    </div>
  );
}
