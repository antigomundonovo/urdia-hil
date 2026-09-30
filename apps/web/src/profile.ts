import { useQuery } from "@tanstack/react-query";
import { api, Profile } from "./api";

/** V1: single-workspace, first profile (ANM seeded). Profile switching
 * arrives with profile management. */
export function useProfile(): { profile?: Profile; workspaceId?: string } {
  const { data } = useQuery({
    queryKey: ["profiles"],
    queryFn: () => api.get<{ profiles: Profile[] }>("/api/v1/profiles"),
  });
  const profile = data?.profiles[0];
  return { profile, workspaceId: profile?.workspace_id };
}
