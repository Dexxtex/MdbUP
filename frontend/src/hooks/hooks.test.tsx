// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "../api/client";
import * as queries from "./queries";
import * as mutations from "./mutations";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, apiFetch: vi.fn() };
});

const apiMock = vi.mocked(apiFetch);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function setup(value: unknown = { items: [] }) {
  apiMock.mockReset();
  apiMock.mockResolvedValue(value as never);
}

describe("query hooks", () => {
  beforeEach(() => setup());

  const cases: [string, () => unknown][] = [
    ["useSession", () => queries.useSession()],
    ["useDashboard", () => queries.useDashboard()],
    ["useCatalogChanges", () => queries.useCatalogChanges({ window: "24h" })],
    ["useProviders", () => queries.useProviders("IT")],
    ["useSources", () => queries.useSources()],
    ["useCollections", () => queries.useCollections({ mediaType: "MOVIE", isActive: "true" })],
    ["useGenres", () => queries.useGenres("MOVIE")],
    ["useCollection", () => queries.useCollection("c1")],
    ["useCollectionSnapshots", () => queries.useCollectionSnapshots("c1")],
    ["useCollectionEpisodeEvents", () => queries.useCollectionEpisodeEvents("c1", 10)],
    ["useSnapshotItems", () => queries.useSnapshotItems("s1", 10, "search")],
    ["useTargets", () => queries.useTargets("MOVIE")],
    ["useBindings", () => queries.useBindings()],
    ["useBinding", () => queries.useBinding("b1")],
    ["useRuns", () => queries.useRuns({ status: "FAILED", providerId: "p1", mediaType: "SHOW" })],
    ["usePreview", () => queries.usePreview("p1")],
    ["useRun", () => queries.useRun("r1")],
    ["useRunOperations", () => queries.useRunOperations("r1", true)],
    ["useSettings", () => queries.useSettings()],
    ["useNotificationChannels", () => queries.useNotificationChannels()],
    ["useSystemStatus", () => queries.useSystemStatus()],
    ["useCredentials", () => queries.useCredentials()],
  ];

  it.each(cases)("%s esegue la query", async (_name, call) => {
    const { result } = renderHook(() => call(), { wrapper });
    await waitFor(() => expect((result.current as { isFetched: boolean }).isFetched).toBe(true));
    expect(apiMock).toHaveBeenCalled();
  });

  it("useSystemStatus rilancia gli errori non 404", async () => {
    apiMock.mockRejectedValueOnce(
      new ApiError({ status: 500, code: "INTERNAL", category: "INTERNAL", message: "no", retryable: true }),
    );
    const { result } = renderHook(() => queries.useSystemStatus(), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("useSystemStatus tratta il 404 come assenza di stato", async () => {
    apiMock.mockRejectedValueOnce(
      new ApiError({ status: 404, code: "NOT_FOUND", category: "VALIDATION", message: "no", retryable: false }),
    );
    const { result } = renderHook(() => queries.useSystemStatus(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeNull());
  });

  it("disabilita le query senza id", () => {
    const { result } = renderHook(() => queries.useCollection(undefined), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("mutation hooks", () => {
  beforeEach(() => setup({ items: [] }));

  const cases: [string, () => unknown, unknown][] = [
    ["useLogin", () => mutations.useLogin(), { email: "a@b.c", password: "secret" }],
    ["useLogout", () => mutations.useLogout(), undefined],
    ["useBootstrap", () => mutations.useBootstrap(), { token: "t", email: "a@b.c", password: "secret" }],
    ["useAcquireCollection", () => mutations.useAcquireCollection("c1"), undefined],
    ["useCreateTarget", () => mutations.useCreateTarget(), { name: "List", private: false, media_type: "MOVIE" }],
    ["useCreateCollection", () => mutations.useCreateCollection(), { name: "Coll", slug: "coll" }],
    ["useUpdateCollection", () => mutations.useUpdateCollection("c1"), { name: "Coll" }],
    ["useHealthcheckSource", () => mutations.useHealthcheckSource("s1"), undefined],
    ["useCreatePreview", () => mutations.useCreatePreview(), { collection_id: "c1" }],
    ["useCreateBinding", () => mutations.useCreateBinding(), { collection_id: "c1", target_id: "t1" }],
    ["useUpdateBinding", () => mutations.useUpdateBinding("b1"), { enabled: true }],
    ["useApproveRun", () => mutations.useApproveRun("r1"), { plan_hash: "x" }],
    ["useCancelRun", () => mutations.useCancelRun("r1"), undefined],
    ["useStartRun", () => mutations.useStartRun(), { bindingId: "b1", dryRun: true }],
    ["useUpdateSettings", () => mutations.useUpdateSettings(), { defaultSource: "justwatch" }],
    ["useCreateNotificationChannel", () => mutations.useCreateNotificationChannel(), { name: "n", kind: "WEBHOOK" }],
    ["useUpdateNotificationChannel", () => mutations.useUpdateNotificationChannel("n1"), { name: "n" }],
    ["useDeleteNotificationChannel", () => mutations.useDeleteNotificationChannel(), "n1"],
    ["useTestNotificationChannel", () => mutations.useTestNotificationChannel(), "n1"],
    ["useSaveCredential", () => mutations.useSaveCredential("TMDB"), "secret"],
    ["useDeleteCredential", () => mutations.useDeleteCredential("TMDB"), undefined],
    ["useVerifyCredential", () => mutations.useVerifyCredential("TMDB"), undefined],
  ];

  it.each(cases)("%s invalida le query", async (_name, hook, payload) => {
    const { result } = renderHook(() => hook(), { wrapper });
    await act(async () => {
      await (result.current as unknown as { mutateAsync: (arg?: unknown) => Promise<unknown> })
        .mutateAsync(payload);
    });
    expect(apiMock).toHaveBeenCalled();
  });
});
