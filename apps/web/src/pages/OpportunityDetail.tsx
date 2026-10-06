import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { api, ContentPackage, Opportunity, QcResult } from "../api";
import { useProfile } from "../profile";
import { StateBadge } from "./Opportunities";

export default function OpportunityDetail() {
  const { id } = useParams();
  const { workspaceId } = useProfile();
  const queryClient = useQueryClient();
  const [platform, setPlatform] = useState("instagram");
  const [qc, setQc] = useState<QcResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [format, setFormat] = useState("PHOTO_POST");
  const [packageId, setPackageId] = useState<string | null>(null);
  const [usedClaimIds, setUsedClaimIds] = useState<string[]>([]);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftCaption, setDraftCaption] = useState("");
  const hydratedPackageId = useRef<string | null>(null);

  useEffect(() => {
    setPackageId(null);
    setUsedClaimIds([]);
    setDraftTitle("");
    setDraftCaption("");
    setQc(null);
    hydratedPackageId.current = null;
  }, [id, workspaceId]);

  const { data: opp } = useQuery({
    queryKey: ["opportunity", id, workspaceId],
    enabled: !!workspaceId && !!id,
    queryFn: () =>
      api.get<Opportunity>(`/api/v1/opportunities/${id}?workspace_id=${workspaceId}`),
  });

  useEffect(() => {
    if (opp?.content_package_id && opp.content_package_id !== packageId) {
      setPackageId(opp.content_package_id);
    }
  }, [opp?.content_package_id, packageId]);

  const {
    data: contentPackage,
    error: contentPackageError,
  } = useQuery({
    queryKey: ["content-package", packageId, workspaceId],
    enabled: !!packageId && !!workspaceId,
    queryFn: () =>
      api.get<ContentPackage>(
        `/api/v1/content/${packageId}?workspace_id=${workspaceId}`
      ),
  });

  useEffect(() => {
    if (!contentPackage || hydratedPackageId.current === contentPackage.id) return;
    hydratedPackageId.current = contentPackage.id;
    const latestDraft = contentPackage.drafts.at(-1);
    setDraftTitle(latestDraft?.title ?? "");
    setDraftCaption(latestDraft?.caption ?? "");
    setUsedClaimIds(latestDraft?.claim_ids_used ?? []);
    setQc(
      contentPackage.latest_qc?.is_current
        ? {
            status: contentPackage.latest_qc.status,
            gates: contentPackage.latest_qc.gates,
            blocking_issues: [],
            warnings: [],
          }
        : null
    );
  }, [contentPackage]);

  const runQc = useMutation({
    mutationFn: () =>
      api.post<QcResult>(`/api/v1/opportunities/${id}/run-qc?workspace_id=${workspaceId}`),
    onSuccess: async (result) => {
      setQc(result);
      setActionError(null);
      await queryClient.invalidateQueries({
        queryKey: ["content-package", packageId, workspaceId],
      });
      await queryClient.invalidateQueries({ queryKey: ["opportunity", id] });
    },
    onError: (e) => setActionError((e as Error).message),
  });
  const approve = useMutation({
    mutationFn: () =>
      api.post<{ state: string }>(`/api/v1/opportunities/${id}/approve?workspace_id=${workspaceId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["opportunity", id] });
      setMessage("Aprovado — registrado no cartório.");
      setActionError(null);
    },
    onError: (e) => setActionError((e as Error).message),
  });
  const reject = useMutation({
    mutationFn: () =>
      api.post<{ state: string }>(`/api/v1/opportunities/${id}/reject?workspace_id=${workspaceId}`, {
        reason: "rejeitado na revisão humana",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["opportunity", id] });
      setMessage("Rejeitado — registrado no cartório.");
      setActionError(null);
    },
    onError: (e) => setActionError((e as Error).message),
  });
  const exportPackage = useMutation({
    mutationFn: async () => {
      await api.post<{ export_path: string; platform: string }>(
        `/api/v1/content/${packageId}/export?workspace_id=${workspaceId}`,
        { platform }
      );
      await api.download(
        `/api/v1/content/${packageId}/export/download?workspace_id=${workspaceId}`,
        `urdia-export-${packageId}.zip`
      );
    },
    onSuccess: () => {
      setMessage("Pacote exportado e baixado. A publicação na plataforma deve ser feita manualmente.");
      setActionError(null);
    },
    onError: (e) => setActionError((e as Error).message),
  });

  if (!opp) return <p className="text-sm text-stone-400">carregando…</p>;

  const savedDraft = contentPackage?.drafts.at(-1);
  const draftIsDirty =
    !!packageId &&
    (draftTitle !== (savedDraft?.title ?? "") ||
      draftCaption !== (savedDraft?.caption ?? "") ||
      JSON.stringify(usedClaimIds) !==
        JSON.stringify(savedDraft?.claim_ids_used ?? []));
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
          Produção (Documento 06 — editor V1)
        </h3>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            className="rounded border border-stone-300 px-3 py-2 text-sm"
          >
            <option value="PHOTO_POST">Foto comentada</option>
            <option value="CAROUSEL">Carrossel</option>
            <option value="MICROLOOP">Microloop</option>
          </select>
          <button
            onClick={() =>
              api
                .post<{ package_id: string }>(
                  `/api/v1/opportunities/${id}/create-content?workspace_id=${workspaceId}`,
                  { format }
                )
                .then((r) => {
                  setPackageId(r.package_id);
                  hydratedPackageId.current = null;
                  setUsedClaimIds([]);
                  setQc(null);
                  setActionError(null);
                  setMessage(`Pacote criado (${format}). Escreva o rascunho abaixo.`);
                  queryClient.invalidateQueries({ queryKey: ["opportunity", id] });
                })
                .catch((e) => setActionError((e as Error).message))
            }
            disabled={!!packageId || !!opp.content_package_id}
            className="rounded border border-stone-300 px-4 py-2 text-sm font-medium hover:bg-stone-50"
          >
            Criar conteúdo
          </button>
        </div>
        {packageId && (
          <div className="mt-4 space-y-2">
            {!contentPackage && !contentPackageError && (
              <p className="text-sm text-stone-500">Carregando pacote e rascunho…</p>
            )}
            {contentPackageError && (
              <p role="alert" className="text-sm text-red-700">
                Não foi possível recuperar o pacote: {contentPackageError.message}
              </p>
            )}
            <input
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              disabled={!contentPackage || !!contentPackageError}
              placeholder="título do post"
              className="w-full rounded border border-stone-300 px-3 py-2 text-sm"
            />
            <textarea
              value={draftCaption}
              onChange={(e) => setDraftCaption(e.target.value)}
              disabled={!contentPackage || !!contentPackageError}
              placeholder="legenda — a prova (claim) usada fica rastreável no sistema"
              rows={3}
              className="w-full rounded border border-stone-300 px-3 py-2 text-sm"
            />
            <button
              onClick={() =>
                api
                  .post<{ draft_id: string }>(
                    `/api/v1/content/${packageId}/generate-draft?workspace_id=${workspaceId}`,
                    {
                      title: draftTitle,
                      caption: draftCaption,
                      claim_ids_used: usedClaimIds,
                    }
                  )
                  .then(() => {
                    setQc(null);
                    setActionError(null);
                    setMessage("Rascunho salvo — rode o QC e decida.");
                    void queryClient.invalidateQueries({
                      queryKey: ["content-package", packageId, workspaceId],
                    });
                    void queryClient.invalidateQueries({ queryKey: ["opportunity", id] });
                  })
                  .catch((e) => setActionError((e as Error).message))
              }
              disabled={!contentPackage || !!contentPackageError || !draftTitle || !draftCaption}
              className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40"
            >
              Salvar rascunho
            </button>
            {opp.claims && opp.claims.length > 0 ? (
              <fieldset className="space-y-2 rounded border border-stone-200 p-3">
                <legend className="px-1 text-sm font-medium text-stone-700">
                  Claims realmente usadas no rascunho
                </legend>
                {opp.claims.map((claim) => (
                  <label key={claim.id} className="flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={usedClaimIds.includes(claim.id)}
                      onChange={(event) =>
                        setUsedClaimIds((current) =>
                          event.target.checked
                            ? [...current, claim.id]
                            : current.filter((claimId) => claimId !== claim.id)
                        )
                      }
                      className="mt-1"
                    />
                    <span>
                      {claim.text || "Claim sem descrição"}
                      <span className="ml-2 text-xs text-stone-500">{claim.status}</span>
                    </span>
                  </label>
                ))}
              </fieldset>
            ) : (
              <p className="text-sm text-amber-800">
                Nenhuma claim está vinculada. Adicione evidências antes de afirmar fatos.
              </p>
            )}
            <p className="text-xs text-stone-400">
              Selecione somente claims sustentadas que aparecem no texto; o QC bloqueará claims sem evidência.
            </p>
          </div>
        )}
        {contentPackage?.latest_qc && !contentPackage.latest_qc.is_current && (
          <p className="mt-3 text-sm text-amber-800">
            O QC salvo está desatualizado em relação ao conteúdo atual. Rode o QC novamente antes de aprovar.
          </p>
        )}
      </section>

      {packageId && <MusicCard packageId={packageId} />}

      <section className="rounded-lg border border-stone-200 bg-white p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Revisão humana (Documento 00 §22)
        </h3>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            onClick={() => approve.mutate()}
            disabled={
              approve.isPending ||
              opp.state !== "QUALITY_CONTROL" ||
              draftIsDirty ||
              !qc ||
              !["PASS", "WARNING"].includes(qc.status)
            }
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
          {packageId && (
            <button
              onClick={() => exportPackage.mutate()}
              disabled={exportPackage.isPending || opp.state !== "READY"}
              className="rounded border border-amber-700 px-4 py-2 text-sm font-medium text-amber-900 hover:bg-amber-50 disabled:opacity-50"
            >
              {exportPackage.isPending ? "Exportando…" : "Exportar pacote"}
            </button>
          )}
          <input
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            className="w-40 rounded border border-stone-300 px-3 py-2 text-sm"
            placeholder="plataforma"
          />
          <button
            onClick={() => runQc.mutate()}
            disabled={!packageId || !contentPackage || draftIsDirty || runQc.isPending}
            className="rounded border border-stone-300 px-4 py-2 text-sm font-medium hover:bg-stone-50"
          >
            {runQc.isPending ? "Verificando…" : "Rodar QC"}
          </button>
        </div>
        <p className="mt-2 text-xs text-stone-500">
          A publicação direta ainda não está conectada; a exportação gera o pacote para publicação manual.
        </p>
        {message && <p className="mt-3 text-sm text-green-700">{message}</p>}
        {draftIsDirty && (
          <p className="mt-3 text-sm text-amber-800">
            Salve as alterações do rascunho antes de executar QC ou aprovar.
          </p>
        )}
        {actionError && (
          <p role="alert" className="mt-3 text-sm text-red-700">
            {actionError}
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

interface AudioPlanView {
  id: string;
  audio_mode: string;
  layers: {
    music?: {
      track_id: string;
      title: string;
      artist?: string | null;
      mood?: string | null;
      intensity?: string | null;
      volume?: number;
      start_time?: number;
      end_time?: number;
      attribution_required?: boolean;
      license_type?: string;
    } | null;
  } | null;
  reason: string | null;
  rights_state: string | null;
  status: string;
  decision_reason: string | null;
}

function MusicCard({ packageId }: { packageId: string }) {
  const { workspaceId } = useProfile();
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");

  const plan = useQuery({
    queryKey: ["audio-plan", packageId, workspaceId],
    enabled: !!packageId && !!workspaceId,
    queryFn: () =>
      api.get<AudioPlanView | null>(
        `/api/v1/audio/packages/${packageId}/plan?workspace_id=${workspaceId}`
      ),
  });

  const suggest = useMutation({
    mutationFn: () =>
      api.post<AudioPlanView>(
        `/api/v1/audio/packages/${packageId}/suggest?workspace_id=${workspaceId}`,
        { platform: "instagram" }
      ),
    onSuccess: (d) => {
      setMessage(
        d.audio_mode === "NONE"
          ? "Nenhuma trilha segura no catálogo para este conteúdo — ele funciona sem música."
          : "Sugestão gerada. Revise abaixo e aprove se concordar."
      );
      void queryClient.invalidateQueries({ queryKey: ["audio-plan", packageId] });
    },
    onError: (e) => setMessage((e as Error).message),
  });

  const decide = useMutation({
    mutationFn: ({ decision, reason }: { decision: string; reason?: string }) =>
      api.post(
        `/api/v1/audio/plans/${plan.data?.id}/decision?workspace_id=${workspaceId}`,
        { decision, reason: reason || undefined }
      ),
    onSuccess: (_d, vars) => {
      setMessage(
        vars.decision === "APPROVED"
          ? "Plano de música aprovado — a trilha entra no pacote de exportação."
          : "Plano rejeitado — o conteúdo será publicado sem música."
      );
      setRejecting(false);
      setReason("");
      void queryClient.invalidateQueries({ queryKey: ["audio-plan", packageId] });
    },
    onError: (e) => setMessage((e as Error).message),
  });

  const music = plan.data?.layers?.music;
  const busy = suggest.isPending || decide.isPending;
  const suggested = plan.data?.status === "SUGGESTED";
  const approved = plan.data?.status === "APPROVED" && plan.data.audio_mode !== "NONE";

  return (
    <section className="rounded-lg border border-stone-200 bg-white p-5">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
        Trilha sonora (música)
      </h3>
      {!plan.data && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            onClick={() => suggest.mutate()}
            disabled={busy}
            className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40"
          >
            1. Sugerir trilha do catálogo
          </button>
          <span className="text-xs text-stone-500">
            música é opcional — o conteúdo funciona sem ela
          </span>
        </div>
      )}
      {plan.data && (
        <div className="mt-3 space-y-2 text-sm">
          <p>
            <strong>Modo:</strong> {plan.data.audio_mode === "NONE" ? "sem música" : "com música"}
            {" · "}
            <span className={plan.data.rights_state === "LICENSED" ? "text-green-800" : "text-red-700"}>
              direitos: {plan.data.rights_state ?? "—"}
            </span>
          </p>
          {music && (
            <p>
              <strong>Sugestão:</strong> {music.title}
              {music.artist ? ` — ${music.artist}` : ""} · trecho {music.start_time ?? 0}s→
              {music.end_time ?? "?"}s · volume {music.volume ?? 0.2}
              {music.attribution_required ? " · exige créditos na legenda" : ""}
            </p>
          )}
          {plan.data.reason && (
            <p className="text-xs italic text-stone-500">Por quê: {plan.data.reason}</p>
          )}
          {suggested && !rejecting && (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                onClick={() => decide.mutate({ decision: "APPROVED" })}
                disabled={busy || plan.data.audio_mode === "NONE"}
                className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white hover:bg-green-800 disabled:opacity-40"
              >
                2. Aprovar música
              </button>
              <button
                onClick={() => setRejecting(true)}
                disabled={busy}
                className="rounded border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-40"
              >
                3. Rejeitar (sem música)
              </button>
              <button
                onClick={() => suggest.mutate()}
                disabled={busy}
                className="rounded border border-stone-300 px-4 py-2 text-sm font-medium hover:bg-stone-50 disabled:opacity-40"
              >
                Sugerir outra
              </button>
            </div>
          )}
          {suggested && rejecting && (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="motivo (opcional)"
                className="w-64 rounded border border-stone-300 px-3 py-1.5 text-xs"
              />
              <button
                onClick={() => decide.mutate({ decision: "REJECTED", reason })}
                disabled={busy}
                className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40"
              >
                Confirmar sem música
              </button>
              <button
                onClick={() => setRejecting(false)}
                className="rounded border border-stone-300 px-4 py-2 text-sm font-medium hover:bg-stone-50"
              >
                Cancelar
              </button>
            </div>
          )}
          {plan.data.status === "REJECTED" && (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                onClick={() => suggest.mutate()}
                disabled={busy}
                className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40"
              >
                Sugerir trilha novamente
              </button>
            </div>
          )}
          {approved && (
            <p className="text-xs text-green-800">
              Trilha aprovada — incluída no kit de exportação (postagem manual).
              As APIs das plataformas não anexam trilha no upload; isso é
              registrado com honestidade.
            </p>
          )}
        </div>
      )}
      {message && <p className="mt-2 text-sm text-stone-700">{message}</p>}
    </section>
  );
}
