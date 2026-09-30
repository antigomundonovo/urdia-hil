import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { api, AuthContext } from "../api";

export default function Auth() {
  const queryClient = useQueryClient();
  const fragmentParams = new URLSearchParams(window.location.hash.slice(1));
  const verificationToken = fragmentParams.get("verify");
  const resetToken = fragmentParams.get("reset");
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [verificationSent, setVerificationSent] = useState(false);
  const [passwordResetRequested, setPasswordResetRequested] = useState(false);

  const auth = useMutation({
    mutationFn: () =>
      api.post<{ message: string } | AuthContext>(
        `/api/v1/auth/${registering ? "register" : "login"}`,
        {
          email,
          password,
          ...(registering && name ? { name } : {}),
        }
      ),
    onSuccess: async () => {
      setPassword("");
      if (registering) {
        setVerificationSent(true);
        setMessage("Se a conta puder ser criada, enviaremos instruções para confirmar o e-mail.");
      } else {
        setMessage(null);
        await queryClient.invalidateQueries({ queryKey: ["auth"] });
      }
    },
  });
  const accountAction = useMutation({
    mutationFn: (input: { path: string; body: Record<string, string> }) =>
      api.post<{ message: string }>(input.path, input.body),
    onSuccess: async (result) => {
      setMessage(result.message);
      if (verificationToken) {
        window.history.replaceState(null, "", window.location.pathname);
      }
      if (resetToken) {
        window.history.replaceState(null, "", window.location.pathname);
      }
      if (!verificationToken && !resetToken && !verificationSent) {
        setPasswordResetRequested(true);
      }
      await queryClient.invalidateQueries({ queryKey: ["auth"] });
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    auth.mutate();
  }

  function submitAccountAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (verificationToken) {
      accountAction.mutate({
        path: "/api/v1/auth/verification/confirm",
        body: { token: verificationToken },
      });
    } else if (resetToken) {
      accountAction.mutate({
        path: "/api/v1/auth/password-reset/confirm",
        body: { token: resetToken, new_password: password },
      });
    } else if (verificationSent) {
      accountAction.mutate({
        path: "/api/v1/auth/verification/request",
        body: { email },
      });
      setMessage("Se a conta exigir confirmação, enviaremos instruções.");
    } else if (passwordResetRequested) {
      accountAction.mutate({
        path: "/api/v1/auth/password-reset/request",
        body: { email },
      });
    }
  }

  const actionMode = !!verificationToken || !!resetToken;
  const actionTitle = verificationToken
    ? "Confirmar e-mail"
    : resetToken
      ? "Criar nova senha"
      : verificationSent
        ? "Reenviar confirmação"
        : "Recuperar senha";

  return (
    <main className="mx-auto mt-16 max-w-md rounded-lg border border-stone-200 bg-white p-6 shadow-sm">
      <h1 className="font-serif text-2xl font-bold">URDIA</h1>
      <p className="mt-2 text-sm text-stone-500">
        {actionMode
          ? actionTitle
          : registering
            ? "Crie sua conta para acessar seu workspace."
            : "Entre para continuar."}
      </p>

      {actionMode || verificationSent || passwordResetRequested ? (
        <form className="mt-6 space-y-4" onSubmit={submitAccountAction}>
          {(!verificationToken) && (
            <label className="block text-sm font-medium text-stone-700">
              E-mail
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                maxLength={320}
                className="mt-1 block w-full rounded border border-stone-300 px-3 py-2"
              />
            </label>
          )}
          {resetToken && (
            <label className="block text-sm font-medium text-stone-700">
              Nova senha
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={1024}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-1 block w-full rounded border border-stone-300 px-3 py-2"
              />
            </label>
          )}
          {accountAction.isError && (
            <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-800">
              {(accountAction.error as Error).message}
            </p>
          )}
          {message && <p role="status" className="text-sm text-stone-600">{message}</p>}
          <button
            type="submit"
            disabled={accountAction.isPending}
            className="w-full rounded bg-stone-900 px-4 py-2 font-medium text-white hover:bg-stone-700 disabled:opacity-50"
          >
            {accountAction.isPending
              ? "Aguarde…"
              : verificationToken
                ? "Confirmar e-mail"
                : resetToken
                  ? "Redefinir senha"
                  : verificationSent
                    ? "Reenviar"
                    : "Enviar instruções"}
          </button>
        </form>
      ) : (
        <form className="mt-6 space-y-4" onSubmit={submit}>
          {registering && (
            <label className="block text-sm font-medium text-stone-700">
              Nome
              <input
                autoComplete="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={255}
                className="mt-1 block w-full rounded border border-stone-300 px-3 py-2"
              />
            </label>
          )}
          <label className="block text-sm font-medium text-stone-700">
            E-mail
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              maxLength={320}
              className="mt-1 block w-full rounded border border-stone-300 px-3 py-2"
            />
          </label>
          <label className="block text-sm font-medium text-stone-700">
            Senha
            <input
              type="password"
              autoComplete={registering ? "new-password" : "current-password"}
              required
              minLength={registering ? 12 : 1}
              maxLength={1024}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1 block w-full rounded border border-stone-300 px-3 py-2"
            />
            {registering && (
              <span className="mt-1 block text-xs font-normal text-stone-400">
                Use pelo menos 12 caracteres.
              </span>
            )}
          </label>
          {auth.isError && (
            <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-800">
              {(auth.error as Error).message}
            </p>
          )}
          {message && <p role="status" className="text-sm text-stone-600">{message}</p>}
          <button
            type="submit"
            disabled={auth.isPending}
            className="w-full rounded bg-stone-900 px-4 py-2 font-medium text-white hover:bg-stone-700 disabled:opacity-50"
          >
            {auth.isPending ? "Aguarde…" : registering ? "Criar conta" : "Entrar"}
          </button>
        </form>
      )}

      {!actionMode && !verificationSent && !passwordResetRequested && (
        <>
          {!registering && (
            <button
              type="button"
              onClick={() => {
                setPasswordResetRequested(true);
                setMessage(null);
                auth.reset();
              }}
              className="mt-4 w-full text-sm text-amber-800 underline"
            >
              Esqueci minha senha
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              setRegistering((value) => !value);
              auth.reset();
              setMessage(null);
            }}
            className="mt-3 w-full text-sm text-amber-800 underline"
          >
            {registering ? "Já tem conta? Entrar" : "Criar uma conta"}
          </button>
        </>
      )}
      {(actionMode || verificationSent || passwordResetRequested) && (
        <button
          type="button"
          onClick={() => {
            window.history.replaceState(null, "", window.location.pathname);
            setVerificationSent(false);
            setPasswordResetRequested(false);
            setMessage(null);
            accountAction.reset();
          }}
          className="mt-4 w-full text-sm text-amber-800 underline"
        >
          Voltar ao login
        </button>
      )}
    </main>
  );
}
