import { getWorkspaceProfile, type ProjectProfile } from "../../services/sztu-runtime";

export type ProjectProfileState = {
  workspaceId: string | null;
  profile: ProjectProfile | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
};

export type WorkspaceProfileLoader = (workspaceId: string, refresh?: boolean) => Promise<ProjectProfile>;
type StateListener = (state: ProjectProfileState) => void;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function snapshot(state: ProjectProfileState): ProjectProfileState {
  return { ...state };
}

export function createProjectProfileController(loadProfile: WorkspaceProfileLoader = getWorkspaceProfile) {
  let generation = 0;
  let state: ProjectProfileState = {
    workspaceId: null,
    profile: null,
    loading: false,
    refreshing: false,
    error: null,
  };
  const listeners = new Set<StateListener>();

  function publish(next: ProjectProfileState): void {
    state = next;
    const current = snapshot(state);
    for (const listener of listeners) listener(current);
  }

  async function request(workspaceId: string, refresh: boolean): Promise<void> {
    const requestGeneration = ++generation;
    const keepExisting = state.workspaceId === workspaceId;
    publish({
      workspaceId,
      profile: keepExisting ? state.profile : null,
      loading: true,
      refreshing: refresh,
      error: null,
    });
    try {
      const profile = await loadProfile(workspaceId, refresh);
      if (requestGeneration !== generation || state.workspaceId !== workspaceId) return;
      publish({ workspaceId, profile, loading: false, refreshing: false, error: null });
    } catch (error) {
      if (requestGeneration !== generation || state.workspaceId !== workspaceId) return;
      publish({ ...state, loading: false, refreshing: false, error: errorMessage(error) });
    }
  }

  return {
    get state(): ProjectProfileState {
      return snapshot(state);
    },
    subscribe(listener: StateListener): () => void {
      listeners.add(listener);
      listener(snapshot(state));
      return () => listeners.delete(listener);
    },
    async setWorkspace(workspaceId: string | null): Promise<void> {
      if (!workspaceId) {
        generation += 1;
        publish({ workspaceId: null, profile: null, loading: false, refreshing: false, error: null });
        return;
      }
      await request(workspaceId, false);
    },
    async refresh(): Promise<void> {
      if (!state.workspaceId || state.loading) return;
      await request(state.workspaceId, true);
    },
  };
}
