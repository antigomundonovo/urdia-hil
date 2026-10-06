import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { useProfile } from "../profile";

interface MusicTrack {
  id: string;
  title: string;
  artist: string | null;
  duration_seconds: number | null;
  mood: string | null;
  intensity: string | null;
  is_instrumental: boolean | null;
  music_language_code: string | null;
  license_type: string;
  license_notes: string | null;
  attribution_required: boolean | null;
  allowed_platforms: string[] | null;
  storage_path: string | null;
  rights_state: string;
}

const RIGHTS_TONE: Record<string, string> = {
  ORIGINAL: "bg-green-100 text-green-800",
  LICENSED: "bg-green-100 text-green-800",
  PLATFORM_LIMITED: "bg-amber-100 text-amber-800",
  UNKNOWN: "bg-red-100 text-red-800",
  BLOCKED: "bg-red-100 text-red-800",
};

const RIGHTS_LEIGO: Record<string, string> = {
  ORIGINAL: "própria/original — direitos registrados",
  LICENSED: "licenciada — uso liberado",
  PLATFORM_LIMITED: "só em plataformas específicas",
  UNKNOWN: "direitos DESCONHECIDOS — nunca usar",
  BLOCKED: "BLOQUEADA — uso proibido",
};

const card = "rounded-lg border border-stone-200 bg-white p-5";

export default function Audio() {
  const { workspaceId } = useProfile();
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState({
    title: "",
    artist: "",
    duration_seconds: "",
    mood: "",
    intensity: "low",
    is_instrumental: true,
    music_language_code: "",
    license_type: "ROYALTY_FREE",
    license_notes: "",
    attribution_required: false,
    allowed_platforms: "",
  });

  const tracks = useQuery({
    queryKey: ["audio-tracks", workspaceId],
    enabled: !!workspaceId,
    queryFn: () =>
      api.get<MusicTrack[]>(`/api/v1/audio/tracks?workspace_id=${workspaceId}`),
  });

  const trends = useMutation({
    mutationFn: (platform: string) =>
      api.post<{ status: string; detail?: string; ingested: number }>(
        `/api/v1/audio/trends/ingest?workspace_id=${workspaceId}`,
        { platform }
      ),
    onSuccess: (d) => {
      if (d.status === "TREND_SOURCE_UNAVAILABLE") {
        setMessage(
          `Tendências de ${d.platform}: fonte oficial ainda não conectada — ` +
            "o sistema NÃO inventa sinais. Conectar a fonte é decisão humana."
        );
      } else {
        setMessage(`${d.ingested} sinal(is) de tendência registrado(s).`);
      }
    },
    onError: (e) => setMessage((e as Error).message),
  });

  const register = useMutation({
    mutationFn: () =>
      api.post<MusicTrack>(`/api/v1/audio/tracks?workspace_id=${workspaceId}`, {
        title: form.title,
        artist: form.artist || null,
        duration_seconds: form.duration_seconds ? Number(form.duration_seconds) : null,
        mood: form.mood || null,
        intensity: form.intensity,
        is_instrumental: form.is_instrumental,
        music_language_code:
          !form.is_instrumental && form.music_language_code
            ? form.music_language_code
            : null,
        license_type: form.license_type,
        license_notes: form.license_notes || null,
        attribution_required: form.attribution_required,
        allowed_platforms: form.allowed_platforms
          ? form.allowed_platforms.split(",").map((s) => s.trim()).filter(Boolean)
          : null,
      }),
    onSuccess: (d) => {
      setMessage(
        `Música "${d.title}" registrada com direitos: ${RIGHTS_LEIGO[d.rights_state] ?? d.rights_state}.`
      );
      setForm({ ...form, title: "", artist: "", duration_seconds: "", license_notes: "" });
      void queryClient.invalidateQueries({ queryKey: ["audio-tracks"] });
    },
    onError: (e) => setMessage((e as Error).message),
  });

  const setStatus = useMutation({
    mutationFn: ({ id, rights_state }: { id: string; rights_state: string }) =>
      api.post(`/api/v1/audio/tracks/${id}/status?workspace_id=${workspaceId}`, {
        rights_state,
      }),
    onSuccess: () => {
      setMessage("Estado de direitos atualizado.");
      void queryClient.invalidateQueries({ queryKey: ["audio-tracks"] });
    },
    onError: (e) => setMessage((e as Error).message),
  });

  const uploadFile = useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => {
      const body = new FormData();
      body.append("file", file);
      return api.post<{ storage_path: string }>(
        `/api/v1/audio/tracks/${id}/file?workspace_id=${workspaceId}`,
        body
      );
    },
    onSuccess: () => {
      setMessage("Áudio anexado — ele entra no kit de exportação.");
      void queryClient.invalidateQueries({ queryKey: ["audio-tracks"] });
    },
    onError: (e) => setMessage((e as Error).message),
  });

  const canRegister = form.title.trim().length > 0;

  return (
    <div className="space-y-6">
      <h2 className="font-serif text-2xl font-bold">Som &amp; Música</h2>
      <p className="text-sm text-stone-500">
        Catálogo de trilhas com <strong>registro de direitos obrigatório</strong> —
        licença desconhecida nunca é usada. O sistema sugere, você decide
        (Emenda 014).
      </p>
      {message && <p className="text-sm text-stone-700">{message}</p>}

      <section className={card}>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          1. Adicionar música ao catálogo
        </h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <input
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="título da trilha (obrigatório)"
            className="rounded border border-stone-300 px-3 py-2 text-sm"
          />
          <input
            value={form.artist}
            onChange={(e) => setForm({ ...form, artist: e.target.value })}
            placeholder="artista / origem"
            className="rounded border border-stone-300 px-3 py-2 text-sm"
          />
          <input
            value={form.duration_seconds}
            onChange={(e) => setForm({ ...form, duration_seconds: e.target.value })}
            placeholder="duração em segundos"
            inputMode="numeric"
            className="rounded border border-stone-300 px-3 py-2 text-sm"
          />
          <input
            value={form.mood}
            onChange={(e) => setForm({ ...form, mood: e.target.value })}
            placeholder="clima (ex.: cinematic, dark_ambient, celebratory)"
            className="rounded border border-stone-300 px-3 py-2 text-sm"
          />
          <select
            value={form.license_type}
            onChange={(e) => setForm({ ...form, license_type: e.target.value })}
            className="rounded border border-stone-300 px-3 py-2 text-sm"
          >
            <option value="ROYALTY_FREE">licença royalty-free</option>
            <option value="CREATIVE_COMMONS">Creative Commons</option>
            <option value="PUBLIC_DOMAIN">domínio público</option>
            <option value="COMMERCIAL">licença comercial</option>
            <option value="PLATFORM_SPECIFIC">só uma plataforma</option>
            <option value="LICENSE_UNKNOWN">não sei a licença</option>
          </select>
          <select
            value={form.intensity}
            onChange={(e) => setForm({ ...form, intensity: e.target.value })}
            className="rounded border border-stone-300 px-3 py-2 text-sm"
          >
            <option value="low">intensidade baixa</option>
            <option value="medium">intensidade média</option>
            <option value="high">intensidade alta</option>
          </select>
          <input
            value={form.license_notes}
            onChange={(e) => setForm({ ...form, license_notes: e.target.value })}
            placeholder="onde/como obteve a licença (prova)"
            className="rounded border border-stone-300 px-3 py-2 text-sm sm:col-span-2"
          />
          <input
            value={form.allowed_platforms}
            onChange={(e) => setForm({ ...form, allowed_platforms: e.target.value })}
            placeholder="plataformas permitidas, separadas por vírgula (vazio = todas declaradas)"
            className="rounded border border-stone-300 px-3 py-2 text-sm sm:col-span-2"
          />
          <label className="flex items-center gap-2 text-sm text-stone-700">
            <input
              type="checkbox"
              checked={form.is_instrumental}
              onChange={(e) => setForm({ ...form, is_instrumental: e.target.checked })}
            />
            instrumental (sem letra)
          </label>
          {!form.is_instrumental && (
            <input
              value={form.music_language_code}
              onChange={(e) => setForm({ ...form, music_language_code: e.target.value })}
              placeholder="idioma da letra (ex.: pt, en)"
              className="rounded border border-stone-300 px-3 py-2 text-sm"
            />
          )}
          <label className="flex items-center gap-2 text-sm text-stone-700">
            <input
              type="checkbox"
              checked={form.attribution_required}
              onChange={(e) => setForm({ ...form, attribution_required: e.target.checked })}
            />
            exige créditos na legenda
          </label>
        </div>
        <button
          onClick={() => register.mutate()}
          disabled={register.isPending || !canRegister}
          className="mt-3 rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40"
        >
          Registrar no catálogo
        </button>
        <p className="mt-2 text-xs text-stone-500">
          Sem prova da licença, a música entra como “direitos desconhecidos” e
          nunca é usada — o sistema prefere publicar sem música a arriscar direito alheio.
        </p>
      </section>

      <section className={card}>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Catálogo ({tracks.data?.length ?? 0})
        </h3>
        <ul className="mt-3 space-y-2">
          {(tracks.data ?? []).map((t) => (
            <li
              key={t.id}
              className="flex flex-wrap items-center justify-between gap-2 border-b border-stone-100 pb-2"
            >
              <div>
                <p className="text-sm font-medium text-stone-800">
                  {t.title}
                  {t.artist ? ` — ${t.artist}` : ""}
                </p>
                <p className="text-xs text-stone-500">
                  {t.duration_seconds ?? "?"}s · clima {t.mood ?? "—"} ·{" "}
                  {t.is_instrumental ? "instrumental" : `letra em ${t.music_language_code ?? "?"}`}
                  {t.allowed_platforms?.length ? ` · só ${t.allowed_platforms.join(", ")}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {t.storage_path ? (
                  <span className="rounded bg-stone-100 px-2 py-0.5 text-xs text-stone-600">
                    áudio anexado ✓
                  </span>
                ) : (
                  <label className="cursor-pointer rounded border border-stone-300 px-2 py-1 text-xs font-medium text-stone-700 hover:bg-stone-50">
                    {uploadFile.isPending ? "anexando…" : "anexar áudio"}
                    <input
                      type="file"
                      accept=".mp3,.wav,.m4a,.ogg,.flac"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) uploadFile.mutate({ id: t.id, file: f });
                        e.target.value = "";
                      }}
                    />
                  </label>
                )}
                <span
                  className={`rounded px-2 py-0.5 text-xs font-medium ${
                    RIGHTS_TONE[t.rights_state] ?? "bg-stone-100 text-stone-600"
                  }`}
                  title={RIGHTS_LEIGO[t.rights_state]}
                >
                  {RIGHTS_LEIGO[t.rights_state] ?? t.rights_state}
                </span>
                {t.rights_state !== "BLOCKED" && (
                  <button
                    onClick={() => setStatus.mutate({ id: t.id, rights_state: "BLOCKED" })}
                    disabled={setStatus.isPending}
                    className="rounded border border-red-300 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                  >
                    Bloquear
                  </button>
                )}
                {t.rights_state === "BLOCKED" && (
                  <button
                    onClick={() => setStatus.mutate({ id: t.id, rights_state: "UNKNOWN" })}
                    disabled={setStatus.isPending}
                    className="rounded border border-stone-300 px-2 py-1 text-xs font-medium hover:bg-stone-50"
                  >
                    Desbloquear (volta p/ desconhecido)
                  </button>
                )}
              </div>
            </li>
          ))}
          {tracks.data?.length === 0 && (
            <li className="text-sm text-stone-400">Nenhuma música no catálogo ainda.</li>
          )}
        </ul>
      </section>

      <section className={card}>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Tendências musicais (experimental)
        </h3>
        <p className="mt-2 text-xs text-stone-600">
          Sinais de "o que está viral" NÃO são autorização de uso — toda
          tendência passa pela checagem de direitos igual às outras músicas.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {["tiktok", "instagram", "youtube", "kwai", "facebook"].map((p, i) => (
            <button
              key={p}
              onClick={() => trends.mutate(p)}
              disabled={trends.isPending}
              className="rounded border border-stone-300 px-3 py-1.5 text-xs font-medium hover:bg-stone-50 disabled:opacity-40"
            >
              {i + 1}. Buscar tendências no {p}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
