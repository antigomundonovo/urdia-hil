import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { api, AuthContext } from "../api";

export default function Auth() {
  const queryClient = useQueryClient();
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");

  const auth = useMutation({
    mutationFn: () =>
      api.post<AuthContext>(`/api/v1/auth/${registering ? "register" : "login"}`, {
        email,
        password,
        ...(registering && name ? { name } : {}),
      }),
    onSuccess: async () => {
      setPassword("");
      await queryClient.invalidateQueries({ queryKey: ["auth"] });
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    auth.mutate();
  }

  return (
    <main className="mx-auto mt-16 max-w-md rounded-lg border border-stone-200 bg-white p-6 shadow-sm">
      <h1 className="font-serif text-2xl font-bold">URDIA</h1>
      <p className="mt-2 text-sm text-stone-500">
        {registering ? "Crie sua conta para acessar seu workspace." : "Entre para continuar."}
      </p>

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
        <button
          type="submit"
          disabled={auth.isPending}
          className="w-full rounded bg-stone-900 px-4 py-2 font-medium text-white hover:bg-stone-700 disabled:opacity-50"
        >
          {auth.isPending ? "Aguarde…" : registering ? "Criar conta" : "Entrar"}
        </button>
      </form>

      <button
        type="button"
        onClick={() => {
          setRegistering((value) => !value);
          auth.reset();
        }}
        className="mt-4 w-full text-sm text-amber-800 underline"
      >
        {registering ? "Já tem conta? Entrar" : "Criar uma conta"}
      </button>
    </main>
  );
}
