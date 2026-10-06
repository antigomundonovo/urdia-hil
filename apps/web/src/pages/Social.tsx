import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, API_URL } from "../api";
import { useProfile } from "../profile";

interface InboxItem {
  id: string;
  comment_id: string | null;
  item_type: string;
  status: string;
  assigned_to: string | null;
  suggested_reply: string | null;
  created_at: string;
  updated_at: string;
}

interface Challenge {
  id: string;
  comment_id: string;
  statement: string;
  claim_id: string | null;
  status: string;
  verdict: string | null;
  verdict_reason: string | null;
  researched_at: string | null;
  reviewed_at: string | null;
  created_at: string;
}

interface AudienceDemand {
  id: string;
  summary: string;
  unique_people_count: number;
  growth: string | null;
  confidence: string | null;
}

interface AudiencePulse {
  id: string;
  sentiment_score: number | null;
  topic_clusters: unknown;
}

const INBOX_STATUSES = ["UNREAD", "OPEN", "RESOLVED", "IGNORED"] as const;
const CHALLENGE_STATUSES = ["PROPOSED", "RESOLVED", "DISMISSED"] as const;
const VERDICTS = ["CONFIRMED", "DISPUTED", "UNSUPPORTED", "UNKNOWN"] as const;

const statusBadge = (status: string) => {
  const tone =
    status === "RESOLVED" || status === "CONFIRMED"
      ? "bg-green-100 text-green-800"
      : status === "PROPOSED" || status === "OPEN" || status === "UNREAD"
        ? "bg-amber-100 text-amber-800"
        : status === "DISMISSED" || status === "IGNORED"
          ? "bg-stone-100 text-stone-500"
          : status === "DISPUTED" || status === "UNSUPPORTED"
            ? "bg-red-100 text-red-800"
            : "bg-stone-100 text-stone-600";
  return `inline-block rounded px-2 py-0.5 text-xs font-medium ${tone}`;
};

export default function Social() {
  const { profile, workspaceId } = useProfile();
  const queryClient = useQueryClient();
  const [inboxFilter, setInboxFilter] = useState<string>("UNREAD");
  const [challengeFilter, setChallengeFilter] = useState<string>("PROPOSED");
  const [message, setMessage] = useState<string | null>(null);

  const base = workspaceId && profile?.id ? `workspace_id=${workspaceId}&profile_id=${profile.id}` : null;

  const inbox = useQuery({
    queryKey: ["social-inbox", workspaceId, profile?.id, inboxFilter],
    enabled: !!base,
    queryFn: () =>
      api.get<InboxItem[]>(
        `/api/v1/social/inbox?${base}${inboxFilter ? `&status=${inboxFilter}` : ""}`
      ),
  });

  const challenges = useQuery({
    queryKey: ["social-challenges", workspaceId, profile?.id, challengeFilter],
    enabled: !!base,
    queryFn: () =>
      api.get<Challenge[]>(
        `/api/v1/social/challenges?${base}${challengeFilter ? `&status=${challengeFilter}` : ""}`
      ),
  });

  const demand = useQuery({
    queryKey: ["social-demand", workspaceId, profile?.id],
    enabled: !!base,
    queryFn: () => api.get<AudienceDemand[]>(`/api/v1/social/audience/demand?${base}`),
  });

  const pulse = useQuery({
    queryKey: ["social-pulse", workspaceId, profile?.id],
    enabled: !!base,
    retry: false,
    queryFn: () => api.get<AudiencePulse>(`/api/v1/social/audience/pulse?${base}`),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["social-inbox"] });
    queryClient.invalidateQueries({ queryKey: ["social-challenges"] });
  };

  const setInboxStatus = useMutation({
    mutationFn: ({ itemId, status }: { itemId: string; status: string }) =>
      api.post(`/api/v1/social/inbox/${itemId}/status?workspace_id=${workspaceId}`, {
        profile_id: profile?.id,
        status,
      }),
    onSuccess: () => {
      setMessage(null);
      invalidate();
    },
    onError: (e) => setMessage((e as Error).message),
  });

  const researchChallenge = useMutation({
    mutationFn: (challengeId: string) =>
      api.post(
        `/api/v1/social/challenges/${challengeId}/research?workspace_id=${workspaceId}&profile_id=${profile?.id}`
      ),
    onSuccess: () => {
      setMessage("Juiz determinístico aplicado — confirme ou ajuste na revisão humana.");
      invalidate();
    },
    onError: (e) => setMessage((e as Error).message),
  });

  const reviewChallenge = useMutation({
    mutationFn: ({ challengeId, verdict, reason }: { challengeId: string; verdict: string; reason?: string }) =>
      api.post(
        `/api/v1/social/challenges/${challengeId}/review?workspace_id=${workspaceId}&profile_id=${profile?.id}`,
        { verdict, reason: reason || undefined }
      ),
    onSuccess: () => {
      setMessage("Veredito humano registrado — esta é a resolução oficial do desafio.");
      invalidate();
    },
    onError: (e) => setMessage((e as Error).message),
  });

  const dismissChallenge = useMutation({
    mutationFn: ({ challengeId, reason }: { challengeId: string; reason: string }) =>
      api.post(
        `/api/v1/social/challenges/${challengeId}/dismiss?workspace_id=${workspaceId}&profile_id=${profile?.id}`,
        { reason }
      ),
    onSuccess: () => {
      setMessage(null);
      invalidate();
    },
    onError: (e) => setMessage((e as Error).message),
  });

  const card = "rounded-lg border border-stone-200 bg-white p-5";
  const filterRow =
    "flex flex-wrap gap-1 text-xs";

  return (
    <div className="space-y-6">
      <h2 className="font-serif text-2xl font-bold">Social</h2>
      <p className="text-sm text-stone-500">
        Camadas de audiência (Doc 15/16): caixa de entrada, desafios de fatos da
        audiência — <strong>veredito sai do juiz determinístico e passa por
        revisão humana</strong> — e demanda/pulso da audiência.
      </p>
      {message && <p className="text-sm text-stone-600">{message}</p>}

      <TikTokCard card={card} />

      <BridgeCard card={card} />

      <section className={card}>
        <div className="flex items-center justify-between gap-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
            Caixa de entrada ({inbox.data?.length ?? 0})
          </h3>
          <div className={filterRow}>
            {["", ...INBOX_STATUSES].map((s) => (
              <button
                key={s || "todos"}
                onClick={() => setInboxFilter(s)}
                className={`rounded px-2 py-1 ${
                  inboxFilter === s
                    ? "bg-stone-900 text-white"
                    : "border border-stone-300 hover:bg-stone-50"
                }`}
              >
                {s || "TODOS"}
              </button>
            ))}
          </div>
        </div>
        <ul className="mt-3 space-y-3">
          {(inbox.data ?? []).map((item) => (
            <li
              key={item.id}
              className="flex items-center justify-between gap-4 border-b border-stone-100 pb-3"
            >
              <div>
                <p className="text-sm text-stone-800">
                  {item.item_type} · {item.comment_id ? `comentário ${item.comment_id.slice(0, 8)}…` : "sem comentário vinculado"}
                </p>
                <div className="mt-1 flex items-center gap-2">
                  <span className={statusBadge(item.status)}>{item.status}</span>
                  {item.assigned_to && (
                    <span className="text-xs text-stone-400">
                      atribuído a {item.assigned_to.slice(0, 8)}…
                    </span>
                  )}
                </div>
                {item.suggested_reply && (
                  <p className="mt-1 text-xs italic text-stone-500">
                    Sugestão: {item.suggested_reply}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {item.status === "UNREAD" && (
                  <button
                    onClick={() => setInboxStatus.mutate({ itemId: item.id, status: "OPEN" })}
                    className="rounded border border-stone-300 px-3 py-1.5 text-xs font-medium hover:bg-stone-50"
                  >
                    Abrir
                  </button>
                )}
                {item.status !== "RESOLVED" && (
                  <button
                    onClick={() => setInboxStatus.mutate({ itemId: item.id, status: "RESOLVED" })}
                    className="rounded bg-green-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-800"
                  >
                    Resolver
                  </button>
                )}
                {item.status !== "IGNORED" && item.status !== "RESOLVED" && (
                  <button
                    onClick={() => setInboxStatus.mutate({ itemId: item.id, status: "IGNORED" })}
                    className="rounded border border-stone-300 px-3 py-1.5 text-xs font-medium hover:bg-stone-50"
                  >
                    Ignorar
                  </button>
                )}
              </div>
            </li>
          ))}
          {inbox.data?.length === 0 && (
            <li className="text-sm text-stone-400">Nada aqui ainda.</li>
          )}
        </ul>
      </section>

      <section className={card}>
        <div className="flex items-center justify-between gap-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
            Desafios de fatos ({challenges.data?.length ?? 0})
          </h3>
          <div className={filterRow}>
            {["", ...CHALLENGE_STATUSES].map((s) => (
              <button
                key={s || "todos"}
                onClick={() => setChallengeFilter(s)}
                className={`rounded px-2 py-1 ${
                  challengeFilter === s
                    ? "bg-stone-900 text-white"
                    : "border border-stone-300 hover:bg-stone-50"
                }`}
              >
                {s || "TODOS"}
              </button>
            ))}
          </div>
        </div>
        <ul className="mt-3 space-y-4">
          {(challenges.data ?? []).map((challenge) => (
            <ChallengeRow
              key={challenge.id}
              challenge={challenge}
              onResearch={() => researchChallenge.mutate(challenge.id)}
              onReview={(verdict, reason) =>
                reviewChallenge.mutate({ challengeId: challenge.id, verdict, reason })
              }
              onDismiss={(reason) => dismissChallenge.mutate({ challengeId: challenge.id, reason })}
              busy={
                researchChallenge.isPending ||
                reviewChallenge.isPending ||
                dismissChallenge.isPending
              }
            />
          ))}
          {challenges.data?.length === 0 && (
            <li className="text-sm text-stone-400">Nenhum desafio ainda.</li>
          )}
        </ul>
      </section>

      <section className={card}>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Demanda da audiência
        </h3>
        <ul className="mt-3 space-y-3">
          {(demand.data ?? []).map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-4 border-b border-stone-100 pb-3">
              <div>
                <p className="text-sm text-stone-800">{d.summary}</p>
                <span className="text-xs text-stone-400">
                  {d.unique_people_count} pessoa(s) · confiança {d.confidence ?? "—"}
                  {d.growth ? ` · tendência ${d.growth}` : ""}
                </span>
              </div>
            </li>
          ))}
          {demand.data?.length === 0 && (
            <li className="text-sm text-stone-400">Sem demanda mapeada ainda.</li>
          )}
        </ul>
        <div className="mt-4 border-t border-stone-100 pt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-stone-500">
            Pulso (última leitura)
          </h4>
          {pulse.data ? (
            <p className="mt-2 text-sm text-stone-700">
              Sentimento: <strong>{pulse.data.sentiment_score ?? "—"}</strong>
              {" · "}Clusters:{" "}
              <code className="text-xs">{JSON.stringify(pulse.data.topic_clusters)}</code>
            </p>
          ) : (
            <p className="mt-2 text-sm text-stone-400">
              Sem dados de pulso ainda (sincronize analytics/comentários primeiro).
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

function ChallengeRow({
  challenge,
  onResearch,
  onReview,
  onDismiss,
  busy,
}: {
  challenge: Challenge;
  onResearch: () => void;
  onReview: (verdict: string, reason?: string) => void;
  onDismiss: (reason: string) => void;
  busy: boolean;
}) {
  const [verdict, setVerdict] = useState<string>("CONFIRMED");
  const [reason, setReason] = useState("");
  const [dismissing, setDismissing] = useState(false);

  return (
    <li className="border-b border-stone-100 pb-4">
      <p className="text-sm text-stone-800">{challenge.statement}</p>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <span className={statusBadge(challenge.status)}>{challenge.status}</span>
        {challenge.verdict && (
          <span className={statusBadge(challenge.verdict)}>veredito: {challenge.verdict}</span>
        )}
        {challenge.claim_id && (
          <span className="text-xs text-stone-400">
            claim {challenge.claim_id.slice(0, 8)}…
          </span>
        )}
      </div>
      {challenge.verdict_reason && (
        <p className="mt-1 text-xs italic text-stone-500">{challenge.verdict_reason}</p>
      )}

      {challenge.status === "PROPOSED" && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            onClick={onResearch}
            disabled={busy}
            className="rounded border border-stone-300 px-3 py-1.5 text-xs font-medium hover:bg-stone-50 disabled:opacity-40"
          >
            Rodar juiz determinístico
          </button>
          <span className="text-xs text-stone-400">— depois, revise e confirme abaixo</span>
        </div>
      )}

      {challenge.status !== "DISMISSED" && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <select
            value={verdict}
            onChange={(e) => setVerdict(e.target.value)}
            className="rounded border border-stone-300 px-2 py-1.5 text-xs"
          >
            {VERDICTS.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="motivo (opcional)"
            className="w-56 rounded border border-stone-300 px-3 py-1.5 text-xs"
          />
          <button
            onClick={() => onReview(verdict, reason || undefined)}
            disabled={busy}
            className="rounded bg-green-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-800 disabled:opacity-40"
          >
            Registrar veredito humano
          </button>
          {!dismissing ? (
            <button
              onClick={() => setDismissing(true)}
              disabled={busy}
              className="rounded border border-stone-300 px-3 py-1.5 text-xs font-medium hover:bg-stone-50 disabled:opacity-40"
            >
              Arquivar…
            </button>
          ) : (
            <>
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="motivo do arquivamento (obrigatório)"
                className="w-64 rounded border border-stone-300 px-3 py-1.5 text-xs"
              />
              <button
                onClick={() => {
                  if (reason.trim().length >= 3) {
                    onDismiss(reason);
                    setDismissing(false);
                    setReason("");
                  }
                }}
                disabled={busy || reason.trim().length < 3}
                className="rounded bg-stone-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-stone-700 disabled:opacity-40"
              >
                Confirmar arquivamento
              </button>
            </>
          )}
        </div>
      )}
    </li>
  );
}

interface TikTokConnection {
  connected: boolean;
}

const TIKTOK_DEMO_PUBLICATION = "e7931f28-1fc6-411b-94e4-9f2daa914426";
const TIKTOK_DEMO_VIDEO = "assets/sandbox-test.mp4";

function TikTokCard({ card }: { card: string }) {
  const { profile, workspaceId } = useProfile();
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [tiktokMessage, setTiktokMessage] = useState<string | null>(null);

  const connection = useQuery({
    queryKey: ["tiktok-connection"],
    queryFn: () => api.get<TikTokConnection>("/api/v1/social/tiktok/connection"),
  });

  const authorize = useMutation({
    mutationFn: () =>
      api.get<{ authorize_url: string }>("/api/v1/social/tiktok/authorize"),
    onSuccess: (d) => {
      window.open(d.authorize_url, "_blank", "noopener");
      setTiktokMessage(
        "1/3: autorize na janela que abriu, copie a URL que aparecer e cole no campo abaixo."
      );
    },
    onError: (e) => setTiktokMessage((e as Error).message),
  });

  const connect = useMutation({
    mutationFn: () => {
      const raw = code.trim();
      const match = raw.match(/[?&]code=([^&\s]+)/);
      const extracted = match ? decodeURIComponent(match[1]) : raw;
      return api.post("/api/v1/social/tiktok/exchange", { code: extracted });
    },
    onSuccess: () => {
      setCode("");
      setTiktokMessage("2/3: TikTok conectado! Agora publique o vídeo de teste.");
      queryClient.invalidateQueries({ queryKey: ["tiktok-connection"] });
    },
    onError: (e) => setTiktokMessage((e as Error).message),
  });

  const publish = useMutation({
    mutationFn: () =>
      api.post(
        `/api/v1/publications/${TIKTOK_DEMO_PUBLICATION}/publish?workspace_id=${workspaceId}`,
        {
          profile_id: profile?.id,
          privacy_level: "SELF_ONLY",
          local_video_path: TIKTOK_DEMO_VIDEO,
        }
      ),
    onSuccess: () => {
      setTiktokMessage(
        "Publicação enviada! Clique em \"Verificar status\" em alguns segundos."
      );
    },
    onError: (e) => setTiktokMessage((e as Error).message),
  });

  const status = useMutation({
    mutationFn: () =>
      api.post<{ status: string; platform_status?: string }>(
        `/api/v1/publications/${TIKTOK_DEMO_PUBLICATION}/status?workspace_id=${workspaceId}`
      ),
    onSuccess: (d) => {
      if (d.status === "PUBLISHED") {
        setTiktokMessage("✅ PUBLISHED — o vídeo está no TikTok (visível só para você).");
      } else {
        setTiktokMessage(`Status: ${d.status}${d.platform_status ? ` (${d.platform_status})` : ""} — espere alguns segundos e verifique de novo.`);
      }
    },
    onError: (e) => setTiktokMessage((e as Error).message),
  });

  const busy = authorize.isPending || connect.isPending || publish.isPending || status.isPending;

  return (
    <section className={`${card} border-amber-300 bg-amber-50`}>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-amber-900">
        TikTok · conexão e publicação de teste
      </h3>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs text-stone-600">
        <li>Clique em <strong>Conectar TikTok</strong>, autorize na janela que abrir.</li>
        <li>Copie a URL da tela final e cole no campo abaixo; clique em <strong>Conectar</strong>.</li>
        <li>Clique em <strong>Publicar vídeo de teste</strong> e depois em <strong>Verificar status</strong>.</li>
      </ol>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-stone-500">
          {connection.data?.connected ? "Conectado ✅" : "Não conectado"}
        </span>
        <button
          onClick={() => authorize.mutate()}
          disabled={busy}
          className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40"
        >
          1. Conectar TikTok
        </button>
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="cole aqui a URL (ou só o código) do TikTok"
          className="w-72 rounded border border-stone-300 px-3 py-2 text-sm"
        />
        <button
          onClick={() => connect.mutate()}
          disabled={busy || !code.trim()}
          className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40"
        >
          2. Conectar
        </button>
        <button
          onClick={() => publish.mutate()}
          disabled={busy}
          className="rounded bg-pink-600 px-4 py-2 text-sm font-medium text-white hover:bg-pink-700 disabled:opacity-40"
        >
          3. Publicar vídeo de teste (só eu)
        </button>
        <button
          onClick={() => status.mutate()}
          disabled={busy}
          className="rounded border border-stone-400 px-4 py-2 text-sm font-medium hover:bg-white disabled:opacity-40"
        >
          4. Verificar status
        </button>
      </div>
      {tiktokMessage && <p className="mt-3 text-sm text-stone-700">{tiktokMessage}</p>}
    </section>
  );
}

interface BridgeClient {
  id: string;
  name: string;
  revoked: boolean;
  last_used_at: string | null;
  created_at: string | null;
}

function CopyRow({ label, value, emphasis }: { label: string; value: string; emphasis?: boolean }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      // clipboard can be blocked (older browser/permission) — select fallback
      const ta = document.createElement("textarea");
      ta.value = value;
      document.body.append(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="flex items-center gap-2">
      <span className="w-40 shrink-0 text-stone-500">{label}:</span>
      <code className={`break-all ${emphasis ? "font-semibold text-amber-900" : "text-stone-800"}`}>{value}</code>
      <button
        onClick={copy}
        title={`Copiar ${label.toLowerCase()}`}
        className="shrink-0 rounded border border-stone-300 bg-white px-2 py-0.5 text-[11px] font-medium text-stone-700 hover:bg-stone-100"
      >
        {copied ? "copiado ✓" : "copiar"}
      </button>
    </div>
  );
}

function BridgeCard({ card }: { card: string }) {
  const { workspaceId } = useProfile();
  const queryClient = useQueryClient();
  const [newKey, setNewKey] = useState<string | null>(null);
  const [bridgeMessage, setBridgeMessage] = useState<string | null>(null);

  const clients = useQuery({
    queryKey: ["bridge-clients"],
    queryFn: () =>
      api.get<BridgeClient[]>(
        `/api/v1/bridge/clients?workspace_id=${workspaceId}`
      ),
    enabled: !!workspaceId,
  });

  const create = useMutation({
    mutationFn: (name: string) =>
      api.post<{ api_key: string }>("/api/v1/bridge/clients", {
        workspace_id: workspaceId,
        name,
      }),
    onSuccess: (d) => {
      setNewKey(d.api_key);
      setBridgeMessage(
        "Chave criada! Copie agora — ela NUNCA mais será exibida."
      );
      queryClient.invalidateQueries({ queryKey: ["bridge-clients"] });
    },
    onError: (e) => setBridgeMessage((e as Error).message),
  });

  const revoke = useMutation({
    mutationFn: (id: string) =>
      api.del(
        `/api/v1/bridge/clients/${id}?workspace_id=${workspaceId}`
      ),
    onSuccess: () => {
      setBridgeMessage("Chave revogada — o Studio perde o acesso na hora.");
      queryClient.invalidateQueries({ queryKey: ["bridge-clients"] });
    },
    onError: (e) => setBridgeMessage((e as Error).message),
  });

  const active = clients.data?.filter((c) => !c.revoked) ?? [];

  return (
    <section className={card}>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
        Ponte Studio · chaves de acesso de máquina
      </h3>
      <p className="mt-2 text-xs text-stone-600">
        Permite ao URDIA Studio <strong>somente ler</strong> a demanda da
        audiência (nada publica, nada apaga). Crie uma chave, entregue ao
        Studio, e revogue se desconfiar de qualquer coisa.
      </p>
      {workspaceId && (
        <div className="mt-3 rounded border border-stone-200 bg-stone-50 p-3">
          <p className="text-xs font-medium text-stone-700">
            Dados de conexão (copie para a tela “Conectar ao HIL” do Studio):
          </p>
          <div className="mt-2 space-y-1 text-xs">
            <CopyRow label="URL da API do HIL" value={API_URL} />
            <CopyRow label="Workspace ID do HIL" value={workspaceId} />
          </div>
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          onClick={() => create.mutate("URDIA Studio")}
          disabled={create.isPending || !workspaceId}
          className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40"
        >
          1. Criar chave de acesso
        </button>
      </div>
      {newKey && (
        <div className="mt-3 rounded border border-amber-300 bg-amber-50 p-3">
          <p className="text-xs font-medium text-amber-900">
            Copie a chave agora (não será mostrada de novo):
          </p>
          <CopyRow label="Chave de acesso" value={newKey} emphasis />

        </div>
      )}
      <div className="mt-4 space-y-2">
        {active.length === 0 && (
          <p className="text-xs text-stone-500">Nenhuma chave ativa.</p>
        )}
        {active.map((c) => (
          <div
            key={c.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded border border-stone-200 px-3 py-2"
          >
            <div className="text-xs">
              <span className="font-medium">{c.name}</span>
              <span className="ml-2 text-stone-500">
                {c.last_used_at
                  ? `usada em ${new Date(c.last_used_at).toLocaleString("pt-BR")}`
                  : "nunca usada"}
              </span>
            </div>
            <button
              onClick={() => revoke.mutate(c.id)}
              disabled={revoke.isPending}
              className="rounded border border-red-300 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-40"
            >
              Revogar
            </button>
          </div>
        ))}
      </div>
      {bridgeMessage && (
        <p className="mt-3 text-sm text-stone-700">{bridgeMessage}</p>
      )}
    </section>
  );
}
