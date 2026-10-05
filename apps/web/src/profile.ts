import { useQuery } from "@tanstack/react-query";
import { api, AuthContext, Profile } from "./api";

/** Initial account experience uses its first authorized workspace/profile. */
export function useProfile(): {
  profile?: Profile;
  workspaceId?: string;
  userEmail?: string;
  isPending: boolean;
  error: Error | null;
  refetch: () => void;
} {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["auth"],
    queryFn: () => api.get<AuthContext>("/api/v1/auth/me"),
    retry: false,
    refetchInterval: 60_000,
  });
  const workspace = data?.workspaces[0];
  const profile = workspace?.profile
    ? { ...workspace.profile, workspace_id: workspace.id }
    : undefined;
  return {
    profile,
    workspaceId: workspace?.id,
    userEmail: data?.user.email,
    isPending,
    error: error as Error | null,
    refetch: () => void refetch(),
  };
}
