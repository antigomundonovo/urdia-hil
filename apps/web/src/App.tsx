import { NavLink, Route, Routes } from "react-router-dom";
import { api, Profile } from "./api";
import { useProfile } from "./profile";
import Dashboard from "./pages/Dashboard";
import Opportunities from "./pages/Opportunities";
import OpportunityDetail from "./pages/OpportunityDetail";
import Sources from "./pages/Sources";
import Analytics from "./pages/Analytics";
import Learning from "./pages/Learning";

const NAV = [
  { to: "/", label: "Painel" },
  { to: "/oportunidades", label: "Oportunidades" },
  { to: "/fontes", label: "Fontes" },
  { to: "/analytics", label: "Analytics" },
  { to: "/learning", label: "Learning" },
];

export default function App() {
  const { profile } = useProfile();
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
          <div className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-900">
            {profile ? `Perfil: ${profile.name}` : "carregando perfil…"}
          </div>
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
