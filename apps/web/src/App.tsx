import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { useProfile } from "./profile";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import Opportunities from "./pages/Opportunities";
import OpportunityDetail from "./pages/OpportunityDetail";
import Sources from "./pages/Sources";
import Analytics from "./pages/Analytics";
import Learning from "./pages/Learning";
import Jobs from "./pages/Jobs";

const NAV = [
  { to: "/", label: "Painel" },
  { to: "/oportunidades", label: "Oportunidades" },
  { to: "/fontes", label: "Fontes" },
  { to: "/jobs", label: "Jobs" },
  { to: "/analytics", label: "Analytics" },
  { to: "/learning", label: "Learning" },
];

export default function App() {
  const queryClient = useQueryClient();
  const { profile, userEmail, isPending, error, refetch } = useProfile();
  const logout = useMutation({
    mutationFn: () => api.post<{ status: string }>("/api/v1/auth/logout"),
    onSuccess: async () => {
      queryClient.clear();
      window.location.assign("/");
    },
  });
  useEffect(() => {
    if (error?.message.startsWith("401:")) {
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== "auth",
      });
    }
  }, [error, queryClient]);

  if (isPending) {
    return <main className="p-8 text-sm text-stone-500">Verificando sessão…</main>;
  }
  if (error?.message.startsWith("401:")) return <Auth />;
  if (error) {
    return (
      <main className="mx-auto mt-16 max-w-lg rounded border border-red-200 bg-white p-6">
        <p role="alert" className="text-sm text-red-800">
          Não foi possível verificar sua sessão: {error.message}
        </p>
        <button onClick={refetch} className="mt-4 text-sm text-amber-800 underline">
          Tentar novamente
        </button>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="font-serif text-xl font-bold tracking-tight">
              URDIA <span className="text-stone-400">· History Intelligence Layer</span>
            </h1>
            <p className="text-xs text-stone-500">
              Descubra muito. Afirme pouco. Prove o que afirmar.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-900">
              {profile ? `Perfil: ${profile.name}` : "perfil indisponível"}
            </div>
            <span className="text-xs text-stone-500">{userEmail}</span>
            <button
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
              className="rounded border border-stone-300 px-3 py-1 text-xs hover:bg-stone-50 disabled:opacity-50"
            >
              Sair
            </button>
          </div>
          {logout.isError && (
            <p role="alert" className="text-xs text-red-700">
              Não foi possível encerrar a sessão: {(logout.error as Error).message}
            </p>
          )}
        </div>
        <nav className="mx-auto flex max-w-6xl gap-1 px-6">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `rounded-t px-4 py-2 text-sm font-medium ${
                  isActive
                    ? "border-b-2 border-amber-600 text-amber-900"
                    : "text-stone-500 hover:text-stone-800"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/oportunidades" element={<Opportunities />} />
          <Route path="/oportunidades/:id" element={<OpportunityDetail />} />
          <Route path="/fontes" element={<Sources />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/learning" element={<Learning />} />
        </Routes>
      </main>
      <footer className="border-t border-stone-200 py-6 text-center text-xs text-stone-400">
        NUNCA considerar LLM output como fato por si só · UNKNOWN rights = NÃO PUBLICAR ·
        V1 exige aprovação humana
      </footer>
    </div>
  );
}
